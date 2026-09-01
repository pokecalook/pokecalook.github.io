"""
スニダン商品詳細API の共通アクセスモジュール

カード（step2_api.py）とBOX（step2_box_api.py）で共通利用する。

API: GET /v1/apparels/{id}
  - 認証不要
  - localizedName: 和名（例: "メガレックウザex SAR [M6 110/076](拡張パック「ストームエメラルダ」)"）
  - name:          英名（例: 'MEGA Rayquaza ex SAR [M6 110/076](Expansion Pack "Storm Emeralda")'）
  - primaryMedia.imageUrl: 商品画像URL（背景除去済みwebp）

【なぜHTMLスクレイピングをやめたか】
2026年8月、スニダンが商品ページのHTML構造を変更した:
  - <title> が「{商品名}の新品/中古フリマ(通販)｜スニダン」から
    「{商品名}通販・買取・相場｜スニダン」に変わり、旧正規表現が全滅
  - og:image が商品画像から全商品共通のロゴ画像
    （cdn.snkrdunk.com/images/ogp/og-image.png）に変わった
結果、商品名にSEO文言が混入し、画像が全部ロゴになる事故が発生した。
このAPIはSEO/マーケ文言の影響を受けないため、恒久対策として採用する。
"""

import hashlib
import os

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://snkrdunk.com/",
}

# 商品名として不正と判断するNGワード（SEO文言混入の検知用）
NAME_NG_WORDS = ("スニダン", "通販・買取・相場", "の新品/中古フリマ")

# og:image に設定される全商品共通のロゴ画像（商品画像として使ってはいけない）
GENERIC_OG_IMAGE_MARKER = "images/ogp/og-image"

# 過去に商品画像として誤保存された不正画像の sha256（変換後webpのハッシュ）
#   - 069bfee...: スニダンの共通OGPロゴ (cdn.snkrdunk.com/images/ogp/og-image.png) を
#     IMAGE_WIDTH=500 / quality=90 でwebp変換したもの。51,624 bytes
# download_and_resize_image() は既存ファイルがこれに一致したら破棄して再取得する。
# サイズが一致した場合のみハッシュを計算するので、通常時のコストはstat 1回分。
KNOWN_BAD_IMAGE_HASHES = {
    "069bfeebac4a8e52bebcea25ba7bd5908a9664cf0398087a197d461fdc87e5b0": 51624,
}
_KNOWN_BAD_SIZES = set(KNOWN_BAD_IMAGE_HASHES.values())


def fetch_apparel_detail(product_id, timeout=10):
    """商品詳細APIを叩いて生のdictを返す。失敗時はNone。"""
    url = f"https://snkrdunk.com/v1/apparels/{product_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def is_valid_product_name(name):
    """商品名にSEO文言が混入していないか検証"""
    if not name:
        return False
    return not any(ng in name for ng in NAME_NG_WORDS)


def is_generic_image(image_url):
    """全商品共通のロゴ画像（=商品画像ではない）かどうか"""
    if not image_url:
        return True
    return GENERIC_OG_IMAGE_MARKER in image_url


def extract_names_and_image(detail):
    """API レスポンスから (和名, 英名, 画像URL) を取り出す。

    英名は既存キャッシュとの互換のためダブルクォートを除去する。
    （旧実装は sales-histories ページの h1 から取得し `"` を除去していた。
      extract_release_year() のパック名マッチと cards/*.html の表示に影響するため形式を揃える）

    Returns: (name, en_name, image_url) — 取得できなかった項目は空文字列
    """
    if not detail:
        return "", "", ""

    name = (detail.get("localizedName") or "").strip()
    en_name = (detail.get("name") or "").strip().replace('"', '')

    image_url = ""
    media = detail.get("primaryMedia")
    if isinstance(media, dict):
        image_url = (media.get("imageUrl") or media.get("url") or "").strip()
    if is_generic_image(image_url):
        image_url = ""

    if not is_valid_product_name(name):
        name = ""

    return name, en_name, image_url


def fetch_names_and_image(product_id, timeout=10):
    """商品IDから (和名, 英名, 画像URL) を取得するショートカット"""
    return extract_names_and_image(fetch_apparel_detail(product_id, timeout=timeout))


def is_known_bad_image_file(filepath):
    """保存済み画像ファイルが既知の不正画像（共通ロゴ等）かどうか。

    既存ファイルがあると内容を検証せずスキップする実装だと、
    一度誤画像が焼き付くと永久に直らない。その事故を防ぐための検査。
    サイズが既知の不正サイズと一致した場合のみハッシュ計算する。
    """
    try:
        if os.path.getsize(filepath) not in _KNOWN_BAD_SIZES:
            return False
        with open(filepath, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        return digest in KNOWN_BAD_IMAGE_HASHES
    except OSError:
        return False
