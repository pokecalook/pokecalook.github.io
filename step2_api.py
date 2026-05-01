"""
Step 2 (API版): sales-chart API から全取引履歴を高速取得
使い方: python step2_api.py [--limit 0] [--top 50]

Seleniumを使わず、スニダンの内部APIを直接叩いて
状態A・PSA10の全取引履歴を取得。圧倒的に高速。

API: GET /v1/apparels/{id}/sales-chart/used?range=all&salesChartOptionId={cid}
  - 認証不要
  - points: [[timestamp_ms, price], ...] 形式で全履歴を返す
  - salesChartOptionId: 18=A, 22=PSA10

出力CSV列:
  抽出順, 商品ID, 商品名, A中央値, PSA10中央値, 差額, 倍率,
  A取引数, PSA10取引数, A最新日, PSA10最新日,
  A_1w中央値, PSA10_1w中央値, 1w倍率, 週トレンド,
  URL
"""

import csv
import json
import os
import re
import sys
import time
import argparse
import statistics
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


INPUT_FILE = "product_links.json"
OUTPUT_CSV = "psa10_vs_a_comparison.csv"
PRICE_CACHE_FILE = "price_data_api.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://snkrdunk.com/",
}

# 状態ID
CONDITION_A = 18
CONDITION_PSA10 = 22

# 英語パック名 → 発売年マッピング（英語名の括弧内から抽出したパック名で検索）
PACK_YEAR = {
    "VSTAR Universe": "2022", "MEGA Dream ex": "2025", "Pokemon Card 151": "2023",
    "Terastal Fest ex": "2024", "VMAX Climax": "2021", "Shiny Treasure ex": "2023",
    "Shiny Star V": "2020", "Tag All Stars": "2019", "GX Ultra Shiny": "2018",
    "GX Battle Boost": "2017", "Best of XY": "2017",
    "25th Anniversary Collection": "2021", "Mega Brave": "2025", "Inferno X": "2025",
    "Munekis Zero": "2025", "Super Electric Breaker": "2024", "Team Rocket": "2025",
    "Battle Partners": "2025", "Black Bolt": "2025", "White Flare": "2025",
    "Ninja Spinner": "2025", "Mega Symphonia": "2025", "Blue Sky Stream": "2021",
    "Tag Bolt": "2018", "Fusion Arts": "2021", "Miracle Twin": "2019",
    "Ruler of the Black Flame": "2023", "Stellar Miracle": "2024",
    "Star Birth": "2022", "Lost Abyss": "2022", "Silver Lance": "2021",
    "Clay Burst": "2023", "Double Blaze": "2019", "Single Strike Master": "2021",
    "Eevee Heroes": "2021", "Pokemon GO": "2022", "Dark Phantasma": "2022",
    "Incandescent Arcana": "2022", "Paradigm Trigger": "2022",
    "Night Wanderer": "2024", "Paradise Dragona": "2024",
    "Shining Legends": "2017", "Thunderclap Spark": "2018",
    "VMAX Rising": "2020", "Night Unison": "2019",
    "Scarlet ex": "2023", "Violet ex": "2023", "Triplet Beat": "2023",
    "Battle Collection": "2024", "Bandit Ring": "2025",
    "McDonalds": "2025", "Pokemon Classic": "2023",
    "Starter Deck Generations": "2024",
}


def extract_release_year(en_name):
    """英語名からパック名を抽出し、発売年を返す"""
    if not en_name:
        return ""
    m = re.search(r'\(([^)]+)\)\s*$', en_name)
    if not m:
        return ""
    pack_text = m.group(1)
    for pack_key, year in PACK_YEAR.items():
        if pack_key.lower() in pack_text.lower():
            return year
    return ""

NUM_WORKERS = 30  # 高速化: 10→30並列
REQUEST_DELAY = 0.1  # 高速化: 0.3→0.1秒

CACHE_MAX_AGE_DAYS = 7  # キャッシュ有効期限（日）

cache_lock = threading.Lock()
progress_lock = threading.Lock()
progress_count = 0


def is_cache_stale(entry):
    """キャッシュエントリが古い or エラーかどうか判定"""
    if not entry:
        return True
    # スキップ（非シングルカード）はリトライしない
    if entry.get("skipped"):
        return False
    # エラーで取得失敗したデータはリトライ
    if entry.get("error"):
        return True
    # 取得日時チェック
    fetched = entry.get("fetched_at", "")
    if not fetched:
        return True
    try:
        fetched_dt = datetime.strptime(fetched, "%Y-%m-%d %H:%M:%S")
        age = (datetime.now() - fetched_dt).days
        return age >= CACHE_MAX_AGE_DAYS
    except ValueError:
        return True


def load_products():
    """商品リストを読み込み"""
    if not os.path.exists(INPUT_FILE):
        print(f"エラー: {INPUT_FILE} が見つかりません。先に step1 を実行してください。")
        sys.exit(1)
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_price_cache():
    """価格キャッシュを読み込み"""
    if os.path.exists(PRICE_CACHE_FILE):
        with open(PRICE_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_price_cache(cache):
    """価格キャッシュを保存"""
    with open(PRICE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_sales_chart(product_id, condition_id):
    """sales-chart API から取引履歴を取得"""
    url = (
        f"https://snkrdunk.com/v1/apparels/{product_id}"
        f"/sales-chart/used?range=all&salesChartOptionId={condition_id}"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            points = data.get("points", [])
            # [[timestamp_ms, price], ...] → [(date_str, price), ...]
            result = []
            for ts, price in points:
                dt = datetime.fromtimestamp(ts / 1000)
                result.append((dt.strftime("%Y-%m-%d"), int(price)))
            return result
        else:
            return []
    except Exception:
        return []


def fetch_product_name(product_id):
    """商品ページから商品名・画像URL・英語名を取得"""
    url = f"https://snkrdunk.com/apparels/{product_id}"
    name = ""
    image_url = ""
    en_name = ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            # 商品名
            match = re.search(r"<title>(.+?)の新品/中古フリマ", r.text)
            if match:
                name = match.group(1).strip()
            else:
                og = re.search(r'property="og:title"\s+content="([^"]*)"', r.text)
                if og:
                    name = og.group(1).split("の新品/中古")[0].strip()
            # 画像URL
            og_img = re.search(r'property="og:image"\s+content="([^"]*)"', r.text)
            if og_img:
                image_url = og_img.group(1)
    except Exception:
        pass

    # 英語名: sales-historiesページのh1タグから取得
    try:
        r2 = requests.get(
            f"https://snkrdunk.com/apparels/{product_id}/sales-histories",
            headers=HEADERS, timeout=10,
        )
        if r2.status_code == 200:
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", r2.text, re.DOTALL)
            if h1:
                raw = h1.group(1).strip()
                # HTMLエンティティをデコード
                raw = raw.replace("&#34;", "").replace("&amp;", "&").replace("&#39;", "").replace('"', '')
                # 連続スペースを1つに正規化
                en_name = re.sub(r'\s+', ' ', raw).strip()
    except Exception:
        pass

    return name, image_url, en_name


def check_is_single_card(product_id):
    """sales-chart APIのsalesChartOptionにPSA10があるか確認（シングルカード判定）"""
    url = (
        f"https://snkrdunk.com/v1/apparels/{product_id}"
        f"/sales-chart/used?range=all&salesChartOptionId=18"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            options = data.get("salesChartOption", [])
            # PSA10 (id=22) が選択肢にあればシングルカード
            for opt in options:
                if opt.get("id") == CONDITION_PSA10:
                    return True, options
        return False, []
    except Exception:
        return False, []


def fetch_single_product(pid, info, total):
    """1商品のデータを取得"""
    global progress_count

    with progress_lock:
        progress_count += 1
        current = progress_count

    # まずシングルカード判定 + 状態Aのデータ取得
    is_single, options = check_is_single_card(pid)
    if not is_single:
        if current % 50 == 0 or current == total:
            print(f"  [{current}/{total}] ID: {pid} → シングルカードではない、スキップ")
        return pid, {"id": pid, "is_single_card": False, "skipped": True}

    time.sleep(REQUEST_DELAY)

    # 状態Aの全履歴
    a_data = fetch_sales_chart(pid, CONDITION_A)
    time.sleep(REQUEST_DELAY)

    # PSA10の全履歴
    psa10_data = fetch_sales_chart(pid, CONDITION_PSA10)
    time.sleep(REQUEST_DELAY)

    # 商品名・画像URL・英語名取得
    name, image_url, en_name = fetch_product_name(pid)
    time.sleep(REQUEST_DELAY)

    a_prices = [p for _, p in a_data]
    a_dates = [d for d, _ in a_data]
    psa10_prices = [p for _, p in psa10_data]
    psa10_dates = [d for d, _ in psa10_data]

    result = {
        "id": pid,
        "name": name,
        "en_name": en_name,
        "release_year": extract_release_year(en_name),
        "image_url": image_url,
        "is_single_card": True,
        "a_prices": a_prices,
        "a_dates": a_dates,
        "psa10_prices": psa10_prices,
        "psa10_dates": psa10_dates,
        "a_all_points": len(a_data),
        "psa10_all_points": len(psa10_data),
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 進捗表示
    a_count = len(a_prices)
    p_count = len(psa10_prices)
    msg = f"  [{current}/{total}] {name[:30] if name else pid} | A: {a_count}件 | PSA10: {p_count}件"
    if a_prices and psa10_prices:
        a_med = statistics.median(a_prices[-5:])  # 直近5件
        p_med = statistics.median(psa10_prices[-5:])
        ratio = p_med / a_med if a_med > 0 else 0
        msg += f" | 倍率: {ratio:.1f}x"
    print(msg)

    return pid, result


def fetch_prices(limit=0, top=0):
    """全商品のデータをAPI経由で取得"""
    global progress_count
    progress_count = 0

    products = load_products()
    cache = load_price_cache()

    to_fetch = []
    stale_count = 0
    for pid, info in products.items():
        if pid not in cache:
            to_fetch.append((pid, info))
        elif is_cache_stale(cache[pid]):
            to_fetch.append((pid, info))
            stale_count += 1

    if limit > 0:
        to_fetch = to_fetch[:limit]

    total = len(to_fetch)
    print(f"取得対象: {total} 商品（新規: {total - stale_count}, 更新: {stale_count}, キャッシュ有効: {len(cache) - stale_count}）")
    print(f"並列数: {NUM_WORKERS} スレッド（API直接アクセス）")
    print(f"リクエスト間隔: {REQUEST_DELAY}秒 | キャッシュ有効期限: {CACHE_MAX_AGE_DAYS}日")

    if total == 0 and len(cache) == 0:
        print("取得対象がありません。")
        return

    if total > 0:
        print(f"\n相場データ取得開始...\n")

        try:
            with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
                futures = {
                    executor.submit(fetch_single_product, pid, info, total): pid
                    for pid, info in to_fetch
                }

                batch_count = 0
                for future in as_completed(futures):
                    try:
                        pid, result = future.result()
                        with cache_lock:
                            cache[pid] = result
                            batch_count += 1

                        # 100件ごとに途中保存
                        if batch_count % 100 == 0:
                            with cache_lock:
                                save_price_cache(cache)
                                print(f"  [途中保存: {batch_count}/{total}]")

                    except Exception as e:
                        print(f"  エラー: {e}")

            save_price_cache(cache)
            print(f"\n取得完了: {progress_count}/{total}")

        except KeyboardInterrupt:
            print("\n\n中断されました。取得済みデータを保存します...")
            save_price_cache(cache)

    print(f"\n=== CSV出力 ===")
    generate_csv(cache, top)


def generate_csv(cache, top=0):
    """キャッシュデータからCSVを生成（倍率順、トレンド分析付き）"""
    products_order = load_products()
    order_map = {}
    for idx, pid in enumerate(products_order.keys(), 1):
        order_map[pid] = idx

    one_month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    one_week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

    rows = []

    for pid, data in cache.items():
        if not data.get("is_single_card"):
            continue

        a_prices = data.get("a_prices", [])
        a_dates = data.get("a_dates", [])
        psa10_prices = data.get("psa10_prices", [])
        psa10_dates = data.get("psa10_dates", [])

        if not a_prices or not psa10_prices:
            continue

        # 直近1ヶ月以内の取引があるかチェック
        a_recent = any(d >= one_month_ago for d in a_dates if d)
        psa10_recent = any(d >= one_month_ago for d in psa10_dates if d)
        if not (a_recent and psa10_recent):
            continue

        # 全データの直近5件の中央値（APIは時系列順なので末尾が最新）
        a_median = statistics.median(a_prices[-5:])
        psa10_median = statistics.median(psa10_prices[-5:])

        if a_median <= 0:
            continue

        ratio = psa10_median / a_median
        diff = psa10_median - a_median

        # --- トレンド分析 ---
        # 直近1週間のデータ
        a_1w = [p for d, p in zip(a_dates, a_prices) if d >= one_week_ago]
        psa10_1w = [p for d, p in zip(psa10_dates, psa10_prices) if d >= one_week_ago]

        # 1〜2週間前のデータ
        a_2w = [p for d, p in zip(a_dates, a_prices) if two_weeks_ago <= d < one_week_ago]
        psa10_2w = [p for d, p in zip(psa10_dates, psa10_prices) if two_weeks_ago <= d < one_week_ago]

        a_1w_med = statistics.median(a_1w) if a_1w else 0
        psa10_1w_med = statistics.median(psa10_1w) if psa10_1w else 0
        ratio_1w = psa10_1w_med / a_1w_med if a_1w_med > 0 else 0

        # 週トレンド: 直近1週間 vs 1〜2週間前の中央値変化率
        trend = ""
        if psa10_1w and psa10_2w:
            med_now = statistics.median(psa10_1w)
            med_prev = statistics.median(psa10_2w)
            if med_prev > 0:
                change = (med_now - med_prev) / med_prev * 100
                if change > 10:
                    trend = f"↑{change:.0f}%"
                elif change < -10:
                    trend = f"↓{abs(change):.0f}%"
                else:
                    trend = f"→{change:+.0f}%"

        rows.append({
            "抽出順": order_map.get(pid, 9999),
            "商品ID": pid,
            "商品名": data.get("name", ""),
            "A中央値": int(a_median),
            "PSA10中央値": int(psa10_median),
            "差額": int(diff),
            "倍率": round(ratio, 2),
            "A取引数": len(a_prices),
            "PSA10取引数": len(psa10_prices),
            "A最新日": a_dates[-1] if a_dates else "",
            "PSA10最新日": psa10_dates[-1] if psa10_dates else "",
            "A_1w中央値": int(a_1w_med) if a_1w_med else "",
            "PSA10_1w中央値": int(psa10_1w_med) if psa10_1w_med else "",
            "1w倍率": round(ratio_1w, 2) if ratio_1w else "",
            "週トレンド": trend,
            "URL": f"https://snkrdunk.com/apparels/{pid}",
        })

    # 倍率の大きい順にソート
    rows.sort(key=lambda x: x["倍率"], reverse=True)

    if top > 0:
        rows = rows[:top]

    if not rows:
        print("出力対象のデータがありません。")
        return

    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"出力件数: {len(rows)}")
    print(f"保存先: {OUTPUT_CSV}")

    # トップ10を表示
    print(f"\n--- 倍率トップ10 ---")
    print(f"{'商品名':<35} {'A中央値':>8} {'PSA10中央値':>10} {'倍率':>6} {'トレンド':>8}")
    print("-" * 75)
    for row in rows[:10]:
        name = row["商品名"][:33]
        trend_str = row["週トレンド"] if row["週トレンド"] else "-"
        print(
            f"{name:<35} ¥{row['A中央値']:>7,} ¥{row['PSA10中央値']:>9,} "
            f"{row['倍率']:>5.1f}x {trend_str:>8}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="スニダン商品の相場データをAPI経由で取得・比較")
    parser.add_argument("--limit", type=int, default=0, help="取得する商品数の上限 (0=全件)")
    parser.add_argument("--top", type=int, default=0, help="CSV出力する上位件数 (0=全件)")
    parser.add_argument("--csv-only", action="store_true", help="取得せずCSV出力のみ")
    args = parser.parse_args()

    if args.csv_only:
        cache = load_price_cache()
        generate_csv(cache, args.top)
    else:
        fetch_prices(limit=args.limit, top=args.top)
