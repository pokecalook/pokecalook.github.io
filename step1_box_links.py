"""
Step 1 (BOX版): BOX商品リンク収集
使い方: python step1_box_links.py [--pages 100]

スニダンの「ボックス・パック」カテゴリから未開封BOX商品リンクを収集。
シュリンクなし（開封済み）BOXや1パック商品は除外。

検索URL: https://snkrdunk.com/search?keywords=Pokemon+Card+Game+トレカ+(ボックス・パック)
          &searchCategoryIds=6/26&brandIds=pokemon&itemConditions=brand_new
"""

import json
import os
import re
import sys
import time
import argparse

import requests


OUTPUT_FILE = "box_product_links.json"
BASE_URL = (
    "https://snkrdunk.com/search?"
    "keywords=Pokemon+Card+Game+"
    "%E3%83%88%E3%83%AC%E3%82%AB+%28%E3%83%9C%E3%83%83%E3%82%AF%E3%82%B9"
    "%E3%83%BB%E3%83%91%E3%83%83%E3%82%AF%29"
    "&searchCategoryIds=6%2F26&brandIds=pokemon"
    "&itemConditions=brand_new&sort=hottest&page={page}"
)

# スタートデッキ系の検索URL（キーワード検索で拾う）
STARTDECK_URL = (
    "https://snkrdunk.com/search?"
    "keywords=%E3%82%B9%E3%82%BF%E3%83%BC%E3%83%88%E3%83%87%E3%83%83%E3%82%AD"
    "&brandIds=pokemon"
    "&itemConditions=brand_new&sort=hottest&page={page}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# 除外キーワード: 1パック、シュリンクなし、開封済み、バラ売り等
# ※「スタートデッキ100」は掲載対象に含める（BOX扱い）
EXCLUDE_KEYWORDS = [
    "1パック", "パック単品", "バラ", "シュリンクなし", "シュリンク無し",
    "開封済み", "開封済", "サーチ済み", "サーチ済",
    "パック売り", "バラ売り", "バラパック",
    "スリーブ", "デッキシールド", "プレイマット", "デッキケース",
    "カードファイル", "コレクションファイル",
]

# BOXとして含めるキーワード（タイトルにこれらが含まれていればBOXと判定）
INCLUDE_KEYWORDS = [
    "BOX", "ボックス", "box", "Box",
    "スタートデッキ",  # スタートデッキ100等も掲載対象
]


def load_existing_products():
    """既存のJSONファイルから商品リストを読み込み"""
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_products(products):
    """商品リストをJSONに保存"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


def should_exclude(title):
    """タイトルから除外すべき商品か判定"""
    title_lower = title.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in title_lower:
            return True
    return False


def is_box_product(title):
    """タイトルからBOX商品か判定"""
    for kw in INCLUDE_KEYWORDS:
        if kw in title:
            return True
    return False


def collect_links(max_pages=100):
    """検索結果ページを巡回してBOX商品リンクを収集"""
    existing = load_existing_products()
    existing_ids = set(existing.keys())
    print(f"既存BOX商品数: {len(existing_ids)}")

    new_count = 0

    # 複数の検索URLを順次巡回
    search_sources = [
        ("ボックス・パックカテゴリ", BASE_URL),
        ("スタートデッキ系キーワード", STARTDECK_URL),
    ]

    try:
        for source_name, url_template in search_sources:
            print(f"\n=== {source_name} ===")
            empty_pages = 0

            for page in range(1, max_pages + 1):
                url = url_template.format(page=page)
                print(f"  ページ {page}/{max_pages}", end="")

                try:
                    r = requests.get(url, headers=HEADERS, timeout=15)
                    if r.status_code != 200:
                        print(f" → HTTP {r.status_code}")
                        empty_pages += 1
                        if empty_pages >= 3:
                            print("  3ページ連続で失敗、このソースを終了")
                            break
                        continue
                except requests.RequestException as e:
                    print(f" → エラー: {e}")
                    empty_pages += 1
                    if empty_pages >= 3:
                        break
                    continue

                # HTMLから商品IDを抽出
                product_ids = set(re.findall(r"/apparels/(\d+)", r.text))

                if len(product_ids) == 0:
                    empty_pages += 1
                    print(f" → 0件（連続{empty_pages}回）")
                    if empty_pages >= 3:
                        print("  3ページ連続で商品なし、このソースを終了")
                        break
                    continue
                else:
                    empty_pages = 0

                page_new = 0
                for pid in product_ids:
                    if pid not in existing_ids:
                        existing[pid] = {
                            "id": pid,
                            "url": f"https://snkrdunk.com/apparels/{pid}",
                            "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "source": source_name,
                        }
                        existing_ids.add(pid)
                        page_new += 1
                        new_count += 1

                print(f" → {len(product_ids)}件検出, +{page_new}新規, 計{len(existing)}")

                # 途中保存（10ページごと）
                if page % 10 == 0:
                    save_products(existing)

                # レート制限対策
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n中断されました。収集済みデータを保存します...")
    finally:
        save_products(existing)

    print(f"\n=== 完了 ===")
    print(f"新規追加: {new_count}")
    print(f"総BOX商品数: {len(existing)}")
    print(f"保存先: {OUTPUT_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="スニダンBOX商品リンクを収集")
    parser.add_argument("--pages", type=int, default=100, help="巡回するページ数 (デフォルト: 100)")
    args = parser.parse_args()

    collect_links(max_pages=args.pages)
