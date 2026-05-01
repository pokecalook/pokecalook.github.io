"""
Step 1: 検索結果ページから商品リンクを収集（requests版）
使い方: python step1_collect_links.py [--pages 100]

Seleniumなし。requestsでHTMLを取得し、
/apparels/XXXXX 形式の商品IDを正規表現で抽出。
既存のJSONがあれば差分マージ（新規商品だけ追加）。
"""

import json
import os
import re
import sys
import time
import argparse

import requests


OUTPUT_FILE = "product_links.json"
BASE_URL = (
    "https://snkrdunk.com/search?"
    "keywords=Pokemon+Card+Game+"
    "%E3%83%88%E3%83%AC%E3%82%AB+%28%E3%82%B7%E3%83%B3%E3%82%B0%E3%83%AB"
    "%E3%82%AB%E3%83%BC%E3%83%89%29"
    "&searchCategoryIds=6%2F33&brandIds=pokemon&sort=hottest&page={page}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


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


def collect_links(max_pages=100):
    """検索結果ページを巡回して商品リンクを収集（requests版）"""
    existing = load_existing_products()
    existing_ids = set(existing.keys())
    print(f"既存商品数: {len(existing_ids)}")

    new_count = 0
    empty_pages = 0

    try:
        for page in range(1, max_pages + 1):
            url = BASE_URL.format(page=page)
            print(f"  ページ {page}/{max_pages}", end="")

            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code != 200:
                    print(f" → HTTP {r.status_code}")
                    empty_pages += 1
                    if empty_pages >= 3:
                        print("  3ページ連続で失敗、終了")
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
                    print("  3ページ連続で商品なし、終了")
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
                        "sales_history_url": f"https://snkrdunk.com/apparels/{pid}/sales-histories",
                        "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
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
    print(f"総商品数: {len(existing)}")
    print(f"保存先: {OUTPUT_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="スニダン検索結果から商品リンクを収集")
    parser.add_argument("--pages", type=int, default=100, help="巡回するページ数 (デフォルト: 100)")
    args = parser.parse_args()

    collect_links(max_pages=args.pages)
