"""
Step 2 (BOX版): BOX商品の価格データをAPI経由で取得
使い方: python step2_box_api.py [--limit 0]

スニダンの /v1/apparels/{id} API から未開封BOXの出品価格を取得。
商品名でフィルタリング（1パック・シュリンクなし等を除外）。

取得データ:
  - regularPrice: 定価
  - minPriceOfNewListing: 新品最安出品価格（=現在の相場）
  - listingCount: 出品数
  - displayReleasedAt: 発売日
  - primaryMedia.url: 画像URL

※ BOX商品はsales-chart API（取引履歴）が利用不可のため、
   出品価格ベースで相場を表示する。

出力: box_price_data.json
"""

import html
import json
import os
import re
import sys
import time
import argparse
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import requests

import snkrdunk_api

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("警告: Pillow未インストール。画像ダウンロードをスキップします。")


INPUT_FILE = "box_product_links.json"
PRICE_CACHE_FILE = "box_price_data.json"
IMAGES_DIR = "images"
IMAGE_WIDTH = 500
IMAGE_QUALITY = 90

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://snkrdunk.com/",
}

# フィルタリングはcolorLocalizedNameベースのみ（シュリンクなし/パック除外）
# step1_box_linksがスニダンの「ボックス・パック」カテゴリから取得するため、
# サプライ品（スリーブ等）は入ってこない。最終フィルタはstep3の掲載条件（10件以上取引+出品中）。

# シュリンクなし除外の例外キーワード（colorLocalizedNameがシュリンクなしでも掲載）
# これらは元々シュリンクなしで流通する商品
SHRINK_EXEMPT_KEYWORDS = [
    "スタートデッキ", "スターターセット",
    "ケース", "クラシック", "アカデミー", "セット",
]

NUM_WORKERS = 20
REQUEST_DELAY = 0.1
CACHE_MAX_AGE_DAYS = 1

cache_lock = threading.Lock()
progress_lock = threading.Lock()
progress_count = 0


def is_cache_stale(entry):
    """キャッシュエントリが古いか判定"""
    if not entry:
        return True
    if entry.get("skipped"):
        # フィルタ条件変更時に再評価するため、全skippedを再取得対象にする
        return True
    if entry.get("error"):
        return True
    # 旧フォーマットを検出して強制再取得
    if (entry.get("schema") or 1) < 5:
        return True
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
    """BOX商品リストを読み込み"""
    if not os.path.exists(INPUT_FILE):
        print(f"エラー: {INPUT_FILE} が見つかりません。先に step1_box_links.py を実行してください。")
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


def is_shrink_exempt(name):
    """シュリンクなし除外の例外か判定"""
    for kw in SHRINK_EXEMPT_KEYWORDS:
        if kw in name:
            return True
    return False


def download_and_resize_image(product_id, image_url):
    """画像をダウンロードしてWebP形式でリサイズ保存"""
    if not HAS_PILLOW or not image_url:
        return False
    # 全商品共通のロゴ画像は商品画像ではないので保存しない
    if snkrdunk_api.is_generic_image(image_url):
        return False

    os.makedirs(IMAGES_DIR, exist_ok=True)
    filepath = os.path.join(IMAGES_DIR, f"box_{product_id}.webp")

    # 既知の不正画像（共通ロゴ等）が焼き付いている場合は破棄して取り直す
    if os.path.exists(filepath):
        if not snkrdunk_api.is_known_bad_image_file(filepath):
            return True
        try:
            os.remove(filepath)
        except OSError:
            return True

    try:
        r = requests.get(image_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return False

        img = Image.open(BytesIO(r.content))
        if img.mode in ("RGBA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[3])
            img = bg

        if img.width > IMAGE_WIDTH:
            ratio = IMAGE_WIDTH / img.width
            new_h = int(img.height * ratio)
            img = img.resize((IMAGE_WIDTH, new_h), Image.LANCZOS)

        img.save(filepath, "WEBP", quality=IMAGE_QUALITY)
        return True
    except Exception:
        return False


def _parse_size_to_qty(size_str):
    """「14個」→ 14 に変換。パースできなければ1"""
    if not size_str:
        return 1
    m = re.search(r"(\d+)", str(size_str))
    return int(m.group(1)) if m else 1


def _parse_relative_date(date_str, now=None):
    """スニダンAPIの相対日付表記("N時間前","N日前","YYYY/MM/DD")をdateオブジェクトに変換"""
    if now is None:
        now = datetime.now()
    s = str(date_str).strip()
    if not s:
        return None
    # "YYYY/MM/DD"
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except ValueError:
            return None
    # "N時間前" / "N分前" → 今日
    if "時間前" in s or "分前" in s or s == "たった今":
        return now.date()
    # "N日前"
    m = re.match(r"^(\d+)日前$", s)
    if m:
        return (now - timedelta(days=int(m.group(1)))).date()
    # "MM/DD"（今年）
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})$", s)
    if m:
        try:
            d = datetime(now.year, int(m.group(1)), int(m.group(2))).date()
            # もし未来日付になったら去年
            if d > now.date():
                d = datetime(now.year - 1, int(m.group(1)), int(m.group(2))).date()
            return d
        except ValueError:
            return None
    return None


def _fetch_sales_history(pid, result):
    """sales-history APIで個別取引を取得、全期間分を単価化してresultに格納"""
    now = datetime.now()
    prices = []
    dates = []
    max_pages = 500  # 20件×500=10000件上限
    for page in range(1, max_pages + 1):
        try:
            url = f"https://snkrdunk.com/v1/apparels/{pid}/sales-history?page={page}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                break
            hist = r.json().get("history", []) or []
            if not hist:
                break
            for it in hist:
                d = _parse_relative_date(it.get("date", ""), now)
                if d is None:
                    continue
                price = int(it.get("price", 0) or 0)
                qty = _parse_size_to_qty(it.get("size", ""))
                if price <= 0 or qty <= 0:
                    continue
                unit = price / qty
                prices.append(int(round(unit)))
                dates.append(d.strftime("%Y-%m-%d"))
            # 次ページへ
            time.sleep(REQUEST_DELAY)
        except Exception:
            break
    result["prices"] = prices
    result["dates"] = dates


def fetch_single_product(pid, info, total):
    """1商品のBOXデータを取得"""
    global progress_count

    with progress_lock:
        progress_count += 1
        current = progress_count

    # /v1/apparels/{id} APIで商品情報取得（カード版と共通モジュール）
    d = snkrdunk_api.fetch_apparel_detail(pid, timeout=10)
    if d is None:
        return pid, {"id": pid, "skipped": True, "reason": "api_error", "error": "detail api failed"}

    time.sleep(REQUEST_DELAY)

    name = d.get("localizedName", d.get("name", ""))
    color_ln = d.get("colorLocalizedName", "") or ""
    reg_price = d.get("regularPrice", 0) or 0
    min_price_new = d.get("minPriceOfNewListing", 0) or 0
    used_min = d.get("usedMinPrice", 0) or 0
    listing_count = d.get("listingCount", 0) or 0
    released_at = d.get("displayReleasedAt", "")
    # 画像URL（共通モジュールでロゴ画像を除外）
    _, _, image_url = snkrdunk_api.extract_names_and_image(d)

    # フィルタリング: colorLocalizedName のシュリンクなし（例外あり）
    if ("シュリンクなし" in color_ln or "シュリンク無し" in color_ln) and not is_shrink_exempt(name):
        return pid, {"id": pid, "skipped": True, "reason": "no_shrink", "name": name, "color": color_ln}

    # フィルタリング: colorLocalizedName がパック単体（ボックス/スターター系でないパック表記）
    if "パック" in color_ln and "ボックス" not in color_ln and not is_shrink_exempt(name):
        return pid, {"id": pid, "skipped": True, "reason": "pack_only", "name": name, "color": color_ln}

    # 出品がない商品はスキップ
    if min_price_new <= 0:
        return pid, {"id": pid, "skipped": True, "reason": "no_listing", "name": name}

    # 画像ダウンロード
    download_and_resize_image(pid, image_url)

    # プレミア率計算
    premium = round((min_price_new / reg_price - 1) * 100, 1) if reg_price > 0 else 0

    result = {
        "id": pid,
        "name": name,
        "color": color_ln,
        "image_url": image_url,
        "is_box": True,
        "schema": 5,  # v5: フィルタ簡素化（BOX_KEYWORDS/EXCLUDE_KEYWORDS廃止）
        "msrp": reg_price,
        "current_price": min_price_new,
        "used_price": used_min,
        "premium": premium,
        "listing_count": listing_count,
        "released_at": released_at,
        "prices": [],    # 単価の配列（各取引の price/quantity）
        "dates": [],     # 対応する日付 YYYY-MM-DD
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 取引履歴を sales-history API で取得（個別取引ごとの価格＋個数）
    # 3ヶ月以内の取引のみ対象にして単価化
    _fetch_sales_history(pid, result)

    # 進捗表示
    msg = f"  [{current}/{total}] {name[:45]} | JPY{min_price_new:,}"
    if reg_price:
        msg += f" (teika JPY{reg_price:,}, {premium:+.0f}%)"
    print(msg)

    return pid, result


def fetch_prices(limit=0, hot_only=False):
    """全BOX商品のデータをAPI経由で取得"""
    global progress_count
    progress_count = 0

    products = load_products()
    cache = load_price_cache()

    to_fetch = []
    stale_count = 0

    if hot_only:
        # 前日取引≥5件のBOXのみ強制再取得
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        hot_pids = set()
        for pid, data in cache.items():
            if not data.get("is_box") or data.get("skipped"):
                continue
            dates = data.get("dates", [])
            day_count = sum(1 for d in dates if d == yesterday)
            if day_count >= 5:
                hot_pids.add(pid)
        for pid, info in products.items():
            if pid in hot_pids:
                to_fetch.append((pid, info))
        print(f"[HOT-ONLY] 前日({yesterday})取引≥5件: {len(hot_pids)}件を強制再取得")
    else:
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
    print(f"並列数: {NUM_WORKERS} スレッド")

    if total == 0:
        print("取得対象がありません。")
        if cache:
            print_summary(cache)
        return

    print(f"\nBOX相場データ取得開始...\n")

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

                    if batch_count % 50 == 0:
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

    print_summary(cache)


def print_summary(cache):
    """サマリー表示"""
    box_count = sum(1 for d in cache.values() if d.get("is_box") and not d.get("skipped"))
    skipped = sum(1 for d in cache.values() if d.get("skipped"))
    print(f"\n=== サマリー ===")
    print(f"BOX商品: {box_count}件")
    print(f"除外: {skipped}件")

    # スキップ理由別
    from collections import Counter
    reasons = Counter()
    for d in cache.values():
        if d.get("skipped"):
            reasons[d.get("reason", "?")] += 1
    if reasons:
        print(f"  内訳: " + ", ".join(f"{k}={v}" for k, v in reasons.most_common()))

    # プレミア率トップ10
    rows = []
    for pid, data in cache.items():
        if not data.get("is_box") or data.get("skipped"):
            continue
        rows.append((
            data.get("name", pid),
            data.get("current_price", 0),
            data.get("msrp", 0),
            data.get("premium", 0),
        ))

    rows.sort(key=lambda x: x[3], reverse=True)
    if rows:
        print(f"\n--- プレミア率トップ10 ---")
        for name, price, msrp, prem in rows[:10]:
            msrp_str = f"JPY{msrp:,}" if msrp else "-"
            print(f"  {name[:50]:<50} JPY{price:>9,} (teika {msrp_str}) {prem:>+7.0f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="スニダンBOX商品の相場データをAPI経由で取得")
    parser.add_argument("--limit", type=int, default=0, help="取得する商品数の上限 (0=全件)")
    parser.add_argument("--hot-only", action="store_true", help="前日取引≥5件のBOXのみ強制再取得")
    args = parser.parse_args()

    fetch_prices(limit=args.limit, hot_only=args.hot_only)
