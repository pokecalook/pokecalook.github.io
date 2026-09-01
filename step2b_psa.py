"""
Step 2b: PSA Pop Report から Gem Rate (PSA10率) を取得
使い方: python step2b_psa.py

PSA の公開API (psacard.com/Pop/GetSetItems) を叩いてPop Reportを取得し、
スニダン商品とマッチングしてキャッシュに gem_rate, psa10_pop, psa_total を追加する。

処理フロー:
1. PSA_SET_IDS (下記定数) にある全セットのPop Reportを取得
2. スニダンのカード名+カード番号とPSAカードをマッチング
3. price_data_api.json に gem_rate 等を書き込む

PSA_SET_IDSは初回だけ手動作成してもいいが、今は主要セットのみ対応。
不足セットがあれば psacard.com/pop/tcg-cards/ から手動で追加。
"""

import json
import os
import re
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


PRICE_CACHE_FILE = "price_data_api.json"
PSA_CACHE_FILE = "psa_pop_cache.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

CATEGORY_ID_TCG = "156940"

# PSA heading IDs for Japanese Pokemon sets
# 新セット追加時はここに追記: (日本語セット略称, heading_id, 英語正規名キーワード)
# psacard.com/pop/tcg-cards/{year}/{slug}/{heading_id} から取得
PSA_SETS = [
    # 2022
    ("VSTAR Universe", 225772, ["vstar universe"]),
    ("Lost Abyss", 219293, ["lost abyss"]),
    ("Paradigm Trigger", 225151, ["paradigm trigger"]),
    ("Star Birth", 208708, ["star birth"]),
    ("Pokemon GO", 214879, ["pokemon go"]),
    ("Dark Phantasma", 213166, ["dark phantasma"]),
    ("Incandescent Arcana", 221517, ["incandescent arcana"]),
    # 2023
    ("Pokemon Card 151", 240107, ["pokemon card 151", "151"]),
    ("Scarlet ex", 228958, ["scarlet ex"]),
    ("Violet ex", 228959, ["violet ex"]),
    ("Triplet Beat", 231150, ["triplet beat"]),
    ("Clay Burst", 232898, ["clay burst"]),
    ("Snow Hazard", 232897, ["snow hazard"]),
    ("Ruler of the Black Flame", 235892, ["ruler of the black flame"]),
    ("Shiny Treasure ex", 243310, ["shiny treasure"]),
    ("Ancient Roar", 245832, ["ancient roar"]),
    ("Future Flash", 245833, ["future flash"]),
    # 2024
    ("Wild Force", 250042, ["wild force"]),
    ("Cyber Judge", 250041, ["cyber judge"]),
    ("Mask of Change", 252548, ["mask of change"]),
    ("Crimson Haze", 252547, ["crimson haze"]),
    ("Stellar Miracle", 256995, ["stellar miracle"]),
    ("Paradise Dragona", 256994, ["paradise dragona"]),
    ("Night Wanderer", 256990, ["night wanderer"]),
    ("Super Electric Breaker", 258925, ["super electric breaker"]),
    ("Terastal Fest ex", 260657, ["terastal fest"]),
    ("Battle Partners", 262557, ["battle partners"]),
    # 2025
    ("Black Bolt", 268116, ["black bolt"]),
    ("White Flare", 268117, ["white flare"]),
    ("Mega Dream ex", 272430, ["mega dream"]),
    ("Mega Brave", 272429, ["mega brave"]),
    ("Mega Symphonia", 274750, ["mega symphonia"]),
    ("Team Rocket", 270500, ["team rocket"]),
    ("Bandit Ring", 274751, ["bandit ring"]),
    # 2021
    ("25th Anniversary Collection", 199357, ["25th anniversary"]),
    ("VMAX Climax", 206137, ["vmax climax"]),
    ("Blue Sky Stream", 196503, ["blue sky stream"]),
    ("Silver Lance", 195940, ["silver lance"]),
    ("Jet Black Spirit", 195941, ["jet black"]),
    ("Eevee Heroes", 192450, ["eevee heroes"]),
    ("Fusion Arts", 199356, ["fusion arts"]),
    ("Single Strike Master", 190828, ["single strike"]),
    ("Rapid Strike Master", 190829, ["rapid strike"]),
    # 2020
    ("Shiny Star V", 185859, ["shiny star v"]),
    ("VMAX Rising", 183104, ["vmax rising"]),
    # 2019
    ("Tag All Stars", 171183, ["tag team gx all stars", "tag all stars"]),
    ("Miracle Twin", 170094, ["miracle twin"]),
    ("Double Blaze", 168547, ["double blaze"]),
    ("Night Unison", 164959, ["night unison"]),
]


def fetch_psa_set(heading_id, set_name):
    """1セットのPop Reportを取得"""
    url = "https://www.psacard.com/Pop/GetSetItems"
    body = {
        "draw": 1,
        "start": 0,
        "length": 2000,
        "headingID": heading_id,
        "categoryID": CATEGORY_ID_TCG,
        "isPSADNA": False,
        "search": {"value": "", "regex": False},
        "order": [],
        "columns": [],
    }
    try:
        r = requests.post(url, headers=HEADERS, json=body, timeout=20)
        if r.status_code != 200:
            print(f"  {set_name}: Status {r.status_code}")
            return None
        data = r.json()
        return data.get("data", [])
    except Exception as e:
        print(f"  {set_name}: エラー {e}")
        return None


def calc_gem_rate(card):
    """PSAカードデータからGem Rateを計算"""
    # 個別グレードのみ（集計フィールドGradeTotal等は除外）
    # 有効フィールド: Grade1, Grade1_5, Grade2, ..., Grade10, Grade1Q, Grade2Q, ..., GradeN0
    total = 0
    grade10 = card.get("Grade10", 0) or 0
    for key, val in card.items():
        if not isinstance(val, int):
            continue
        # GradeTotal, HalfGradeTotal, QualifiedGradeTotal, Total は集計なので除外
        if key in ("GradeTotal", "HalfGradeTotal", "QualifiedGradeTotal", "Total", "SortOrder", "CardNumberSort", "SpecID"):
            continue
        # Grade{数字} か Grade{数字}_5 か Grade{数字}Q か GradeN0 のみ加算
        if re.match(r"^Grade(\d+(_\d+)?Q?|N0)$", key):
            total += val
    gem_rate = (grade10 / total * 100) if total > 0 else 0
    return {
        "psa_total": total,
        "psa10_pop": grade10,
        "psa9_pop": card.get("Grade9", 0) or 0,
        "gem_rate": round(gem_rate, 1),
    }


def normalize_card_number(s):
    """カード番号を比較用に正規化。077 → 77, 226/172 → 226"""
    if not s:
        return ""
    s = str(s).strip()
    # 分数形式 "226/172" の場合は分子のみ使う
    if "/" in s:
        s = s.split("/")[0]
    # 先頭の0を除去
    s = s.lstrip("0") or "0"
    return s


def match_scores(psa_card, snk_card_number, snk_en_name):
    """PSAカードとスニダンカードのマッチングスコア (0-100)"""
    # カード番号の一致
    psa_num = normalize_card_number(psa_card.get("CardNumber", ""))
    snk_num = normalize_card_number(snk_card_number)
    if not psa_num or not snk_num:
        return 0
    if psa_num != snk_num:
        return 0
    # 番号一致のベース点
    score = 70

    # 名前類似度（簡易）
    psa_name = (psa_card.get("SubjectName") or "").lower()
    snk_name = (snk_en_name or "").lower()
    # ポケモン名抽出（英語名）
    snk_before_bracket = re.sub(r"\[.*$", "", snk_name).strip()
    snk_tokens = set(re.findall(r"[a-z]+", snk_before_bracket))
    psa_tokens = set(re.findall(r"[a-z]+", psa_name))
    if snk_tokens and psa_tokens:
        overlap = len(snk_tokens & psa_tokens)
        if overlap > 0:
            score += min(30, overlap * 10)
    return score


def parse_snkrdunk_card(card_data):
    """スニダン商品データから (en_name, card_number, set_slug) を抽出"""
    en = card_data.get("en_name", "")
    if not en:
        return None, None, None

    # カード番号抽出: [S12a 226/172] → "226/172", セットキー: "s12a"
    m = re.search(r"\[([A-Za-z0-9-]+)\s+(\d+(?:/\d+)?)\]", en)
    if not m:
        return en, "", ""
    set_key = m.group(1).lower()
    card_num = m.group(2)
    return en, card_num, set_key


def match_set_to_psa(snk_en_name, snk_set_key):
    """スニダンカードのセット情報から、対応するPSA heading IDを見つける"""
    en_lower = (snk_en_name or "").lower()
    best_match = None
    best_score = 0

    for set_name, heading_id, keywords in PSA_SETS:
        for kw in keywords:
            if kw in en_lower:
                # より長いキーワードが一致した方が優先
                if len(kw) > best_score:
                    best_score = len(kw)
                    best_match = (set_name, heading_id)

    return best_match


def main():
    if not os.path.exists(PRICE_CACHE_FILE):
        print(f"エラー: {PRICE_CACHE_FILE} が見つかりません")
        sys.exit(1)

    with open(PRICE_CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    print(f"=== PSA Pop Report 取得 ===")
    print(f"対象セット数: {len(PSA_SETS)}")

    # 既存のPSAキャッシュがあれば読み込む
    psa_data = {}
    if os.path.exists(PSA_CACHE_FILE):
        with open(PSA_CACHE_FILE, "r", encoding="utf-8") as f:
            psa_data = json.load(f)
        print(f"既存PSAキャッシュ: {len(psa_data)} セット")

    # 全セット取得（並列）
    def fetch_one(item):
        set_name, heading_id, _ = item
        cards = fetch_psa_set(heading_id, set_name)
        return heading_id, set_name, cards

    fetched = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_one, item): item for item in PSA_SETS}
        for future in as_completed(futures):
            try:
                heading_id, set_name, cards = future.result()
                if cards:
                    psa_data[str(heading_id)] = {
                        "set_name": set_name,
                        "cards": cards,
                        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    fetched += 1
                    print(f"  ✓ {set_name}: {len(cards)}件")
                else:
                    print(f"  ✗ {set_name}: 取得失敗")
            except Exception as e:
                print(f"  エラー: {e}")

    print(f"\n取得成功: {fetched}/{len(PSA_SETS)} セット")

    with open(PSA_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(psa_data, f, ensure_ascii=False, indent=2)

    # スニダンカードとマッチング
    print(f"\n=== マッチング ===")
    matched = 0
    unmatched = 0
    low_sample = 0

    for pid, snk in cache.items():
        if not snk.get("is_single_card"):
            continue
        en_name, card_num, _ = parse_snkrdunk_card(snk)
        if not en_name or not card_num:
            unmatched += 1
            continue

        set_match = match_set_to_psa(en_name, None)
        if not set_match:
            unmatched += 1
            continue

        set_name, heading_id = set_match
        psa_set = psa_data.get(str(heading_id))
        if not psa_set:
            unmatched += 1
            continue

        # セット内で最適なカードを探す
        best = None
        best_score = 0
        for psa_card in psa_set["cards"]:
            if psa_card.get("SpecID", 0) == 0:
                continue  # TOTAL POPULATION行
            score = match_scores(psa_card, card_num, en_name)
            if score > best_score:
                best_score = score
                best = psa_card

        if best and best_score >= 70:
            gr = calc_gem_rate(best)
            # サンプル数が少なすぎる場合は信頼度マーカー
            if gr["psa_total"] < 20:
                low_sample += 1
                gr["gem_rate_reliable"] = False
            else:
                gr["gem_rate_reliable"] = True
            snk.update(gr)
            matched += 1
        else:
            unmatched += 1

    print(f"マッチ成功: {matched}件")
    print(f"サンプル不足(<20): {low_sample}件")
    print(f"マッチ失敗: {unmatched}件")

    # price_data_api.json を更新
    with open(PRICE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"\nキャッシュ更新完了: {PRICE_CACHE_FILE}")


if __name__ == "__main__":
    main()
