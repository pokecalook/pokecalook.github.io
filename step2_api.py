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
import html
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
from io import BytesIO

import requests

import snkrdunk_api

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("警告: Pillow未インストール。画像ダウンロードをスキップします。pip install Pillow で導入してください。")


INPUT_FILE = "product_links.json"
OUTPUT_CSV = "psa10_vs_a_comparison.csv"
PRICE_CACHE_FILE = "price_data_api.json"
IMAGES_DIR = "images"
IMAGE_WIDTH = 500  # リサイズ後の幅（px）
IMAGE_QUALITY = 90  # WebP品質

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://snkrdunk.com/",
}

# 状態ID（シングルカード判定用）
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

CACHE_MAX_AGE_DAYS = 1  # 毎日全件更新（GitHub Actionsなら7分で終わる）
MIN_LISTING_SCHEMA = 2   # min_listing枚数割り対応バージョン
# 商品名・画像URLの取得方式バージョン
#   1: HTML(<title>/og:image/sales-histories h1)パース方式（SEO文言変更で破損）
#   2: /v1/apparels/{id} API方式
NAME_SCHEMA = 2

cache_lock = threading.Lock()
progress_lock = threading.Lock()
progress_count = 0


def is_cache_stale(entry):
    """キャッシュエントリが古い or エラーかどうか判定"""
    if not entry:
        return True
    # スキップ（非シングルカード）は毎回再判定
    # → 新弾カードが発売直後にskippedされても、取引開始後に拾い直せる
    # （BOX版と同じ方式）
    if entry.get("skipped"):
        return True
    # エラーで取得失敗したデータはリトライ
    if entry.get("error"):
        return True
    # sold_dataフィールドを持たないシングルカードは強制再取得
    if entry.get("is_single_card") and "sold_data" not in entry:
        return True
    # 旧形式（qtyフィールドなし）のsold_dataは強制再取得
    if entry.get("is_single_card"):
        sold = entry.get("sold_data", [])
        if sold and not all("qty" in s for s in sold):
            return True
    # min_listing枚数割り未対応の旧キャッシュは強制再取得
    if entry.get("is_single_card") and entry.get("ml_schema", 0) < MIN_LISTING_SCHEMA:
        return True
    # シングルカードでsold_dataが10件未満（新弾カードで出品一覧APIから取れていないケース）は強制再取得
    # → sales-chartフォールバックで補完されるはず
    if entry.get("is_single_card") and len(entry.get("sold_data", [])) < 10:
        return True
    # 商品名・画像がHTMLパース方式（旧）で取得されたキャッシュは強制再取得
    # → SEO文言混入・ロゴ画像汚染を一掃する
    if entry.get("name_schema", 0) < NAME_SCHEMA:
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



def fetch_product_name(product_id):
    """商品詳細APIから商品名・画像URL・英語名を取得。

    /v1/apparels/{id} の1リクエストで和名・英名・画像URLが揃う。
    以前はHTMLの<title>/og:image/sales-historiesのh1をパースしていたが、
    スニダンのSEO文言変更で商品名・画像が壊れたためAPIに移行した。
    詳細は snkrdunk_api.py の docstring を参照。
    """
    name, en_name, image_url = snkrdunk_api.fetch_names_and_image(product_id)
    # 連続スペースを1つに正規化（旧実装と同じ形式を維持）
    if en_name:
        en_name = re.sub(r'\s+', ' ', en_name).strip()
    if name:
        name = re.sub(r'\s+', ' ', name).strip()
    return name, image_url, en_name


def download_and_resize_image(product_id, image_url):
    """画像をダウンロードしてWebP形式でリサイズ保存。既存ファイルはスキップ。"""
    if not HAS_PILLOW or not image_url:
        return False
    # 全商品共通のロゴ画像は商品画像ではないので保存しない
    if snkrdunk_api.is_generic_image(image_url):
        return False

    os.makedirs(IMAGES_DIR, exist_ok=True)
    filepath = os.path.join(IMAGES_DIR, f"{product_id}.webp")

    # キャッシュ: ファイルが既に存在すればスキップ
    # ただし既知の不正画像（共通ロゴ等）が焼き付いている場合は破棄して取り直す
    if os.path.exists(filepath):
        if not snkrdunk_api.is_known_bad_image_file(filepath):
            return True
        try:
            os.remove(filepath)
            print(f"    不正画像を破棄して再取得: {filepath}")
        except OSError:
            return True

    try:
        r = requests.get(image_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return False

        img = Image.open(BytesIO(r.content))

        # RGBA → RGB変換（WebP保存時にアルファチャンネルがあると容量が増える場合がある）
        if img.mode in ("RGBA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[3])
            img = bg

        # 余白トリミング（白背景を除去）
        w, h = img.size
        THR = 250  # ほぼ白のピクセルを余白と判定
        top = 0
        for y in range(h):
            if all(img.getpixel((x, y))[0] > THR and img.getpixel((x, y))[1] > THR and img.getpixel((x, y))[2] > THR for x in range(0, w, 3)):
                top = y + 1
            else:
                break
        bot = h
        for y in range(h - 1, -1, -1):
            if all(img.getpixel((x, y))[0] > THR and img.getpixel((x, y))[1] > THR and img.getpixel((x, y))[2] > THR for x in range(0, w, 3)):
                bot = y
            else:
                break
        left = 0
        for x in range(w):
            if all(img.getpixel((x, y))[0] > THR and img.getpixel((x, y))[1] > THR and img.getpixel((x, y))[2] > THR for y in range(0, h, 3)):
                left = x + 1
            else:
                break
        right = w
        for x in range(w - 1, -1, -1):
            if all(img.getpixel((x, y))[0] > THR and img.getpixel((x, y))[1] > THR and img.getpixel((x, y))[2] > THR for y in range(0, h, 3)):
                right = x
            else:
                break
        if top > 0 or bot < h or left > 0 or right < w:
            img = img.crop((left, top, right, bot))

        # アスペクト比を維持してリサイズ
        if img.width > IMAGE_WIDTH:
            ratio = IMAGE_WIDTH / img.width
            new_h = int(img.height * ratio)
            img = img.resize((IMAGE_WIDTH, new_h), Image.LANCZOS)

        img.save(filepath, "WEBP", quality=IMAGE_QUALITY)
        return True
    except Exception:
        return False


def check_is_single_card(product_id):
    """シングルカード判定:
    1. sales-chart APIにPSA10オプションがあればシングルカード
    2. PSA10オプションがなくても、出品一覧APIでSOLD(status=4)が10件以上あればシングルカード
       → 新弾カードはPSA鑑定前でもA状態で大量に取引されるため
    """
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
            # PSA10オプションがなくても、取引データ(points)が10件以上あればシングルカード
            points = data.get("points", [])
            if len(points) >= 10:
                return True, options
        return False, []
    except Exception:
        return False, []


def fetch_min_listing_prices(product_id):
    """出品一覧APIから状態別の最安1枚単価を取得。
    セット売り（2枚以上）も price÷枚数 で1枚単価に換算して比較。
    Returns: (min_listing_a, min_listing_psa10) — 出品なしの場合はNone
    """
    # 出品一覧を取得（全サイズ、出品中のみ、100件）
    try:
        r = requests.get(
            f"https://snkrdunk.com/v1/apparels/{product_id}/used",
            params={"perPage": 100, "page": 1, "isSaleOnly": "false"},
            headers=HEADERS, timeout=10
        )
        if r.status_code != 200:
            return None, None
        items = r.json().get("apparelUsedItems", [])
    except Exception:
        return None, None

    # 状態別に最安1枚単価を抽出
    min_a = None
    min_psa10 = None
    for item in items:
        # 出品中（status != 4）のみ対象
        if item.get("status") == 4:
            continue
        cond = item.get("displayShortConditionTitle", "")
        price = item.get("price", 0)
        if price <= 0:
            continue
        # size から枚数を抽出
        size_info = item.get("size", {})
        size_name = size_info.get("localizedName", "") if size_info else ""
        qty_match = re.match(r'^(\d+)', size_name)
        qty = int(qty_match.group(1)) if qty_match else 1
        if qty <= 0:
            qty = 1
        unit_price = int(price / qty)
        if unit_price <= 0:
            continue
        if cond == "A":
            if min_a is None or unit_price < min_a:
                min_a = unit_price
        elif cond == "PSA10":
            if min_psa10 is None or unit_price < min_psa10:
                min_psa10 = unit_price

    return min_a, min_psa10


def fetch_sold_data(product_id, max_pages=100):
    """出品一覧APIから全ページのSOLDデータ（status=4）を取得。
    セット売り（2枚以上）も含め、price÷枚数で1枚単価を算出。

    出品一覧APIのSOLDが10件未満の場合（新弾カード等で発生）は、
    sales-chart APIのpointsデータで「補完」する。
    出品一覧APIで取れた枚数割済みデータは必ず保持し、
    重複は (timestamp秒, price, condition) でユニーク化する。

    Returns: list of {"date": "YYYY-MM-DD", "price": int, "condition": "A"|"PSA10"|..., "qty": int}
    """
    sold_items = []  # 内部処理中は "_ts"(秒単位) も含む
    page = 1

    while page <= max_pages:
        try:
            r = requests.get(
                f"https://snkrdunk.com/v1/apparels/{product_id}/used",
                params={"perPage": 100, "page": page, "isSaleOnly": "false"},
                headers=HEADERS, timeout=15
            )
            if r.status_code != 200:
                break
            items = r.json().get("apparelUsedItems", [])
            if not items:
                break

            for item in items:
                # status=4 のみ（取引完了）
                if item.get("status") != 4:
                    continue
                # size_nameから枚数を抽出（"1枚", "2枚", "3枚"等）
                size_info = item.get("size", {})
                size_name = size_info.get("localizedName", "") if size_info else ""
                if not size_name:
                    continue
                # 先頭の数字を枚数として抽出
                qty_match = re.match(r'^(\d+)', size_name)
                if not qty_match:
                    continue
                qty = int(qty_match.group(1))
                if qty <= 0:
                    continue
                # 価格・日付・状態を抽出
                price = item.get("price", 0)
                if price <= 0:
                    continue
                # 1枚単価を算出（整数に丸め）
                unit_price = int(price / qty)
                if unit_price <= 0:
                    continue
                updated_at = item.get("updatedAt", "")
                if not updated_at:
                    continue
                date_str = updated_at[:10]  # "2026-05-06T00:34:42Z" → "2026-05-06"
                condition = item.get("displayShortConditionTitle", "")
                # 重複排除用: ISO秒文字列 → unix秒
                try:
                    ts_sec = int(datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ").timestamp())
                except ValueError:
                    ts_sec = 0
                sold_items.append({
                    "date": date_str,
                    "price": unit_price,
                    "condition": condition,
                    "qty": qty,
                    "_ts": ts_sec,
                })

            # 100件未満ならこれが最終ページ
            if len(items) < 100:
                break
            page += 1
            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"    SOLD取得エラー (page {page}): {e}")
            break

    # 出品一覧APIのSOLDが10件未満の場合、sales-chart APIで「補完」する。
    # 出品一覧APIのデータ（セット売り枚数割済み）は優先保持。
    # 重複は (秒精度ts, price, condition) でユニーク化する。
    if len(sold_items) < 10:
        existing_keys = set(
            (s["_ts"], s["price"], s["condition"])
            for s in sold_items if s["_ts"] > 0
        )
        chart_items = _fetch_sold_from_saleschart(product_id)
        for c in chart_items:
            key = (c.get("_ts", 0), c["price"], c["condition"])
            if c.get("_ts", 0) > 0 and key in existing_keys:
                continue
            sold_items.append(c)

    # 内部用 _ts を除去（既存スキーマ互換）
    for s in sold_items:
        s.pop("_ts", None)

    return sold_items


def _fetch_sold_from_saleschart(product_id):
    """sales-chart APIのpointsデータから取引履歴を構築（補完用）。
    出品一覧APIにSOLDが少ない新弾カード等で使用。
    points: [[timestamp_ms, price], ...] 形式。
    重複排除用に内部フィールド "_ts"（unix秒）を含む。
    """
    sold_items = []
    # 状態A (id=18) と PSA10 (id=22) を取得
    for cond_id, cond_name in [(18, "A"), (22, "PSA10")]:
        try:
            url = (
                f"https://snkrdunk.com/v1/apparels/{product_id}"
                f"/sales-chart/used?range=all&salesChartOptionId={cond_id}"
            )
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            points = data.get("points", [])
            for ts_ms, price in points:
                if price <= 0:
                    continue
                ts_sec = int(ts_ms / 1000)
                dt = datetime.fromtimestamp(ts_sec)
                sold_items.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "price": int(price),
                    "condition": cond_name,
                    "qty": 1,  # sales-chart APIは1枚単価
                    "_ts": ts_sec,
                })
            time.sleep(REQUEST_DELAY)
        except Exception:
            continue

    return sold_items


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
        return pid, {"id": pid, "is_single_card": False, "skipped": True, "name_schema": NAME_SCHEMA, "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    time.sleep(REQUEST_DELAY)

    # 商品名・画像URL・英語名取得
    name, image_url, en_name = fetch_product_name(pid)
    time.sleep(REQUEST_DELAY)

    # 画像ダウンロード+リサイズ
    img_saved = download_and_resize_image(pid, image_url)

    # --- 出品一覧から1枚売り最安出品価格を取得 ---
    min_listing_a, min_listing_psa10 = fetch_min_listing_prices(pid)
    time.sleep(REQUEST_DELAY)

    # --- 出品一覧APIからSOLDデータ（status=4, size=1枚）を全ページ取得 ---
    sold_data = fetch_sold_data(pid)
    time.sleep(REQUEST_DELAY)

    result = {
        "id": pid,
        "name": name,
        "en_name": en_name,
        "release_year": extract_release_year(en_name),
        "image_url": image_url,
        "is_single_card": True,
        "min_listing_a": min_listing_a,
        "min_listing_psa10": min_listing_psa10,
        "ml_schema": MIN_LISTING_SCHEMA,
        "name_schema": NAME_SCHEMA,
        "sold_data": sold_data,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 進捗表示
    sold_a = len([s for s in sold_data if s["condition"] == "A"])
    sold_p = len([s for s in sold_data if s["condition"] == "PSA10"])
    msg = f"  [{current}/{total}] {name[:30] if name else pid} | SOLD(A:{sold_a},P10:{sold_p})"
    if sold_a > 0 and sold_p > 0:
        a_prices_recent = sorted([s["price"] for s in sold_data if s["condition"] == "A"], reverse=True)[:5]
        p_prices_recent = sorted([s["price"] for s in sold_data if s["condition"] == "PSA10"], reverse=True)[:5]
        if a_prices_recent and p_prices_recent:
            a_med = statistics.median(a_prices_recent)
            p_med = statistics.median(p_prices_recent)
            ratio = p_med / a_med if a_med > 0 else 0
            msg += f" | 倍率: {ratio:.1f}x"
    print(msg)

    return pid, result


def fetch_prices(limit=0, top=0, hot_only=False):
    """全商品のデータをAPI経由で取得"""
    global progress_count
    progress_count = 0

    products = load_products()
    cache = load_price_cache()

    to_fetch = []
    stale_count = 0

    if hot_only:
        # 前日SOLD≥5件のカードのみ強制再取得
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        hot_pids = set()
        for pid, data in cache.items():
            if not data.get("is_single_card"):
                continue
            sold = data.get("sold_data", [])
            day_count = sum(1 for s in sold if s.get("date") == yesterday)
            if day_count >= 5:
                hot_pids.add(pid)
        for pid, info in products.items():
            if pid in hot_pids:
                to_fetch.append((pid, info))
        print(f"[HOT-ONLY] 前日({yesterday})SOLD≥5件: {len(hot_pids)}枚を強制再取得")
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

    # --- 画像ダウンロード（キャッシュ済み商品も含む） ---
    if HAS_PILLOW:
        os.makedirs(IMAGES_DIR, exist_ok=True)
        missing_images = []
        for pid, data in cache.items():
            if not data.get("is_single_card") or data.get("skipped"):
                continue
            img_path = os.path.join(IMAGES_DIR, f"{pid}.webp")
            if not os.path.exists(img_path) and data.get("image_url"):
                missing_images.append((pid, data["image_url"]))

        if missing_images:
            print(f"\n=== 画像ダウンロード ===")
            print(f"未取得画像: {len(missing_images)} 枚")
            img_count = 0

            def dl_image(args):
                pid, url = args
                return pid, download_and_resize_image(pid, url)

            with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
                futures = {executor.submit(dl_image, item): item for item in missing_images}
                for future in as_completed(futures):
                    try:
                        pid, ok = future.result()
                        if ok:
                            img_count += 1
                            if img_count % 100 == 0:
                                print(f"  画像ダウンロード: {img_count}/{len(missing_images)}")
                    except Exception as e:
                        print(f"  画像エラー: {e}")

            print(f"画像ダウンロード完了: {img_count}/{len(missing_images)}")
        else:
            print(f"\n画像: 全件取得済み")

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

        sold_data = data.get("sold_data", [])
        if not sold_data:
            continue

        sold_a = [(s["date"], s["price"]) for s in sold_data if s.get("condition") == "A"]
        sold_p = [(s["date"], s["price"]) for s in sold_data if s.get("condition") == "PSA10"]
        sold_a.sort(key=lambda x: x[0])
        sold_p.sort(key=lambda x: x[0])
        a_dates = [d for d, _ in sold_a]
        a_prices = [p for _, p in sold_a]
        psa10_dates = [d for d, _ in sold_p]
        psa10_prices = [p for _, p in sold_p]

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
    parser.add_argument("--hot-only", action="store_true", help="前日SOLD≥5件のカードのみ強制再取得")
    args = parser.parse_args()

    if args.csv_only:
        cache = load_price_cache()
        generate_csv(cache, args.top)
    else:
        fetch_prices(limit=args.limit, top=args.top, hot_only=args.hot_only)
