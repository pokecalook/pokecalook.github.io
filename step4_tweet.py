"""
Step 4: Xポスト文生成（リニューアル版 2026/5/24〜）
- 指数1本 + カード2本 + BOX2本 = 計5本/日
- URLはポスト文に含めない
- ハッシュタグなし
- 絵文字を各行に配置（表情豊かに）
- 問いかけ系全廃 → データ事実で締める
- B（比較型）7割 / C（ストーリー型）3割
- 期間を必ず明示（週間/月間/前日比）
"""
import json, os, sys, random, re, statistics, glob
import html as html_mod
from datetime import datetime, timedelta, timezone

PRICE_CACHE = "price_data_api.json"
BOX_CACHE = "box_price_data.json"
POSTED_FILE = "posted_tweets.json"
OUTPUT_HTML = "tweets.html"
IMG_DIR = "images"
SITE_URL = "https://pokecalook.com"
JST = timezone(timedelta(hours=9))
DEDUP_DAYS = 3


# ============================================================
# テンプレートパーツ（カード）
# ============================================================

# --- 見出し（B型） ---
HEADLINE_B_CARD_DIVERGE = [
    "⚡ {name}、PSA10と美品が逆行中",
    "🔀 {name}、PSA10と美品で真逆の動き",
    "⚡ {name}、美品とPSA10で明暗が分かれています",
]
HEADLINE_B_CARD_BOTH_UP = [
    "📈 {name}、美品・PSA10ともに上昇中",
    "🔥 {name}、美品もPSA10も上がっています",
    "⬆️ {name}、美品もPSA10も買われています",
]
HEADLINE_B_CARD_BOTH_DOWN = [
    "📉 {name}、美品・PSA10ともに下落中",
    "⬇️ {name}、美品もPSA10も下がっています",
    "😢 {name}、美品もPSA10も売られています",
]
HEADLINE_B_CARD_ONE_SIDE = [
    "💡 {name}、{grade}中心に動いています",
    "👀 {name}、{grade}の変動が目立ちます",
    "⚡ {name}、{grade}に大きな動き",
]

# --- 見出し（C型） ---
HEADLINE_C_CARD = [
    "👀 {name}、1週間で動きあり",
    "💡 {name}、面白い動きをしています",
    "🔍 {name}、この1週間で変化",
    "⚡ {name}、直近の値動きが気になります",
]

# --- データ行パターン ---
DATA_LINE_PSA_FIRST = "💎 PSA10: {p}（週間{pch}）\n✨ 美品: {a}（週間{ach}）"
DATA_LINE_BIHIN_FIRST = "✨ 美品: {a}（週間{ach}）\n💎 PSA10: {p}（週間{pch}）"
DATA_LINE_STORY_PSA = "💎 PSA10: {p}（1週間で{pch}）\n✨ 美品: {a}（1週間で{ach}）"
DATA_LINE_STORY_BIHIN = "✨ 美品: {a}（1週間で{ach}）\n💎 PSA10: {p}（1週間で{pch}）"

# --- 事実締め（条件分岐で選択） ---
CLOSING_DIVERGE = [
    "🔄 週間{wc}件取引。\nこの1ヶ月ではPSA10が{p_mch}、美品が{a_mch}。\n月間でも方向が分かれています🤔",
    "📊 取引件数は週{wc}件。\n月間で見るとPSA10 {p_mch}、美品 {a_mch}。\n逆方向に動いています⚡",
    "🔄 週{wc}件の取引あり。\n先月比でPSA10は{p_mch}、美品は{a_mch}。\n1ヶ月通して逆行しています🔀",
]
CLOSING_BOTH_UP = [
    "🔄 週間{wc}件取引。\nこの1ヶ月ではPSA10が{p_mch}、美品が{a_mch}。\n上昇が続いています🔥",
    "📊 取引件数は週{wc}件。\n月間で見るとPSA10 {p_mch}、美品 {a_mch}。\nどちらも上がっています⬆️",
    "🔄 週{wc}件の取引あり。\n先月比でPSA10は{p_mch}、美品は{a_mch}。\n1ヶ月通して買いが続いています✨",
]
CLOSING_BOTH_DOWN = [
    "🔄 週間{wc}件取引。\nこの1ヶ月ではPSA10が{p_mch}、美品が{a_mch}。\n下落が続いています😢",
    "📊 取引件数は週{wc}件。\n月間で見るとPSA10 {p_mch}、美品 {a_mch}。\nどちらも下がっています⬇️",
    "🔄 週{wc}件の取引あり。\n先月比でPSA10は{p_mch}、美品は{a_mch}。\n1ヶ月通して売りが続いています💧",
]
CLOSING_ONE_SIDE = [
    "🔄 週間{wc}件取引。\nこの1ヶ月では{move_grade}が{mch}、{still_grade}はほぼ横ばいです👀",
    "📊 取引件数は週{wc}件。\n月間で見ると{move_grade}は{mch}。\n{still_grade}はあまり動いていません💤",
    "🔄 週{wc}件の取引あり。\n先月比で{move_grade}だけ{mch}の変動。\n{still_grade}は安定しています🍃",
]

# --- 追加データ行（文字数調整用） ---
EXTRA_DATA = [
    "直近の取引ペースは1日{daily}件前後で推移しています📊",
    "取引件数は週間{wc}件で活発に動いています🔄",
    "PSA10と美品の価格差は{spread}で推移しています💎",
]


# ============================================================
# テンプレートパーツ（BOX）
# ============================================================

HEADLINE_B_BOX_UP = [
    "📦 {name}、じわじわ上昇中⬆️",
    "📦 {name}、価格が上がっています🔥",
    "📦 {name}、上昇トレンド継続中📈",
]
HEADLINE_B_BOX_DOWN = [
    "📦 {name}、下落が続いています⬇️",
    "📦 {name}、価格が下がっています😢",
    "📦 {name}、値下がり中📉",
]
HEADLINE_C_BOX = [
    "📦 {name}、この1週間で動きあり👀",
    "📦 {name}、直近の値動きが気になります🔍",
    "📦 {name}、相場に変化が出ています⚡",
]

DATA_LINE_BOX = [
    "💰 現在の中央値: {med}（週間{ch}）\n🔄 週間{wc}個取引 / 出品数{listings}件",
    "💰 直近7日の中央値: {med}（先週比{ch}）\n🔄 週間{wc}個取引 / 出品数{listings}件",
    "💰 今の相場: {med}（1週間で{ch}）\n🔄 週間{wc}個取引 / 出品数{listings}件",
]
CLOSING_BOX_UP = [
    "🗓️ 1ヶ月前は{med_prev}だったので月間で{mch}の上昇。\n取引件数は多めで、買いが強い状況です🔥",
    "🗓️ 先月の{med_prev}から月間{mch}上がっています。\n出品は{listings}件ありますが、それでも上昇中📈",
    "🗓️ この1ヶ月で{mch}の上昇。\n{med_prev}から着実に上がっています。\n取引ペースも落ちていません✨",
]
CLOSING_BOX_DOWN = [
    "🗓️ 1ヶ月前は{med_prev}だったので月間で{mch}の下落。\n出品が増えて売り圧が強い状況です😢",
    "🗓️ 先月の{med_prev}から月間{mch}下がっています。\n出品数{listings}件で、売りたい人が多い印象です⬇️",
    "🗓️ この1ヶ月で{mch}の下落。\n{med_prev}から下がり続けています。\n底値はまだ見えません💧",
]


# ============================================================
# テンプレートパーツ（指数）
# ============================================================

HEADLINE_INDEX = [
    "📊 最新のポケカ指数",
    "📊 本日のポケカ指数",
    "📊 ポケカ指数アップデート",
]
CLOSING_INDEX = [
    "📅 週間ではPSA10が{p_wch}、美品が{a_wch}。\nこの1ヶ月で見るとPSA10が{p_mch}、美品が{a_mch}の変動です。\n{trend_comment}",
    "🗓️ 今週はPSA10 {p_wch}、美品 {a_wch}。\n月間トレンドではPSA10 {p_mch}、美品 {a_mch}です。\n{trend_comment}",
    "📅 週間変動: PSA10 {p_wch} / 美品 {a_wch}\n🗓️ 月間変動: PSA10 {p_mch} / 美品 {a_mch}\n{trend_comment}",
]
TREND_COMMENTS = {
    "both_up": [
        "月間で見ると両方上がっていて、買い優勢の1ヶ月でした🔥",
        "この1ヶ月はどちらも上昇。じわじわ来てます📈",
        "月間トレンドは上向き。勢いありますね✨",
    ],
    "both_down": [
        "月間で見ると両方下がっていて、売り優勢の1ヶ月でした😢",
        "この1ヶ月はどちらも下落。様子見が続いています⬇️",
        "月間トレンドは下向き。まだ底が見えません💧",
    ],
    "p_up_a_down": [
        "月間で見るとPSA10だけ上がって美品は下がっています🤔",
        "この1ヶ月、鑑定品に資金が集中している印象です💎",
        "月間トレンドはPSA10↑美品↓。美品とPSA10で差が出ています⚡",
    ],
    "p_down_a_up": [
        "月間で見ると美品が上がってPSA10は下がっています🤔",
        "この1ヶ月、未鑑定品に買いが入っている状況です🌱",
        "月間トレンドは美品↑PSA10↓。面白い動きです⚡",
    ],
    "flat": [
        "月間で見ると大きな動きはなく安定しています😌",
        "この1ヶ月はほぼ横ばい。静かな相場です🍃",
        "月間トレンドは安定。嵐の前の静けさかも🌊",
    ],
}


# ============================================================
# ユーティリティ関数
# ============================================================

def fmt(n):
    """¥付きカンマ区切り"""
    return f"¥{n:,}"

def fmt_change(n):
    """変動額表示"""
    if n > 0:
        return f"+¥{n:,}"
    elif n < 0:
        return f"-¥{abs(n):,}"
    return "±¥0"

def fmt_short(n):
    """短縮表記（万単位）"""
    if abs(n) >= 10000:
        v = n / 10000
        if v == int(v):
            return f"{int(v)}万"
        return f"{v:.1f}万"
    return f"¥{n:,}"

def x_char_count(text):
    """Xの文字数カウント（日本語=2、英数=1、改行=1）"""
    t = re.sub(r'https?://\S+', 'x' * 23, text)
    count = 0
    for ch in t:
        if ch == '\n':
            count += 1
        elif ord(ch) > 0x7F:
            count += 2
        else:
            count += 1
    return count

def parse_card_name(raw_name):
    card_num_m = re.search(r'\[([^\]]+)\]', raw_name)
    card_num = card_num_m.group(1) if card_num_m else ""
    short_name = re.sub(r'\s*\[.*', '', raw_name).strip()
    parts = short_name.rsplit(' ', 1) if ' ' in short_name else [short_name]
    rarity_codes = {"C","U","R","RR","RRR","SR","SAR","UR","HR","AR","S","P","MA","MUR","CSR","CHR","SSR","TR","PR","K","A","H","FA"}
    has_rarity = len(parts) > 1 and parts[-1].replace(':','').replace('仕様','').strip() in rarity_codes
    if not has_rarity and card_num:
        short_name = f"{short_name} [{card_num}]"
    return short_name

def get_pokemon_name(name):
    """カード名からポケモン名を抽出"""
    pokemon_names = ["ピカチュウ","リザードン","ミュウツー","ミュウ","ゲンガー","イーブイ",
                     "レックウザ","ブラッキー","リーリエ","カイリュー","ルギア","ニンフィア",
                     "エーフィ","カメックス","ルカリオ","ゲッコウガ","ギラティナ","カビゴン",
                     "ミミッキュ","フシギバナ","ヒトカゲ","ゼニガメ","ブースター","シャワーズ",
                     "サンダース","ナンジャモ","サーナイト","ゼラオラ"]
    for pn in pokemon_names:
        if pn in name:
            return pn
    m = re.match(r'^([ァ-ヶー]+)', name)
    return m.group(1) if m else name.split()[0] if name else ""

# --- BOX名短縮 ---
_BOX_SERIES = ['MEGA', 'ソード&シールド', 'ソード＆シールド', 'スカーレット&バイオレット',
               'スカーレット＆バイオレット', 'サン&ムーン', 'サン＆ムーン',
               'XY BREAK', 'XY', 'BW', 'DP', 'ADV', 'PCG', 'VS', 'neo', 'e']
_BOX_NAME_RE = re.compile(r'^ポケモンカードゲーム\s*(?:' + '|'.join(re.escape(s) for s in _BOX_SERIES) + r')?\s*')

def shorten_box_name(name):
    short = _BOX_NAME_RE.sub('', name).strip()
    return short if short else name


# ============================================================
# 重複管理
# ============================================================

def load_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_posted(posted):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(posted, f, ensure_ascii=False, indent=2)

def clean_posted(posted):
    cutoff = (datetime.now(JST) - timedelta(days=DEDUP_DAYS)).isoformat()
    return [p for p in posted if p.get("ts", "") > cutoff]

def is_recently_used(posted, card_id=None, pokemon=None):
    for p in posted:
        if card_id and p.get("id") == card_id:
            return True
        if pokemon and p.get("pokemon") == pokemon:
            return True
    return False


# ============================================================
# カード候補取得
# ============================================================

def get_card_candidates():
    with open(PRICE_CACHE, "r", encoding="utf-8") as f:
        cache = json.load(f)
    one_w = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    two_w = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    four_w = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")
    three_m = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    cards = []
    for pid, d in cache.items():
        if not d.get("is_single_card") or d.get("skipped"):
            continue
        sold_data = d.get("sold_data", [])
        if not sold_data:
            continue
        sold_a = [(s["date"], s["price"]) for s in sold_data if s.get("condition") == "A"]
        sold_p = [(s["date"], s["price"]) for s in sold_data if s.get("condition") == "PSA10"]
        sold_a.sort(key=lambda x: x[0])
        sold_p.sort(key=lambda x: x[0])
        ad_ = [dt for dt, _ in sold_a]
        ap = [p for _, p in sold_a]
        pd_ = [dt for dt, _ in sold_p]
        pp = [p for _, p in sold_p]
        if not ap or not pp:
            continue
        a3 = [(dt, p) for dt, p in zip(ad_, ap) if dt >= three_m]
        p3 = [(dt, p) for dt, p in zip(pd_, pp) if dt >= three_m]
        if len(a3) < 5 or len(p3) < 5:
            continue

        wc = sum(1 for dt in ad_ if dt >= one_w) + sum(1 for dt in pd_ if dt >= one_w)
        if wc < 50:
            continue

        # PSA10 weekly change
        p_one_w = [p for dt, p in zip(pd_, pp) if dt >= one_w]
        p_two_w = [p for dt, p in zip(pd_, pp) if two_w <= dt < one_w]
        pch_yen = int(statistics.median(p_one_w) - statistics.median(p_two_w)) if p_one_w and p_two_w else None

        # Bihin weekly change
        a_one_w = [p for dt, p in zip(ad_, ap) if dt >= one_w]
        a_two_w = [p for dt, p in zip(ad_, ap) if two_w <= dt < one_w]
        ach_yen = int(statistics.median(a_one_w) - statistics.median(a_two_w)) if a_one_w and a_two_w else None

        # Monthly change (4 weeks)
        p_four_w = [p for dt, p in zip(pd_, pp) if four_w <= dt < one_w]
        a_four_w = [p for dt, p in zip(ad_, ap) if four_w <= dt < one_w]
        p_mch = int(statistics.median(p_one_w) - statistics.median(p_four_w)) if p_one_w and p_four_w else None
        a_mch = int(statistics.median(a_one_w) - statistics.median(a_four_w)) if a_one_w and a_four_w else None

        max_ch = max(abs(pch_yen) if pch_yen else 0, abs(ach_yen) if ach_yen else 0)
        if max_ch < 3000:
            continue

        # Median prices
        am = int(statistics.median(a_one_w)) if a_one_w else int(statistics.median([p for _, p in a3[-5:]]))
        pm = int(statistics.median(p_one_w)) if p_one_w else int(statistics.median([p for _, p in p3[-5:]]))

        # Previous week medians (for story type)
        am_prev = int(statistics.median(a_two_w)) if a_two_w else am
        pm_prev = int(statistics.median(p_two_w)) if p_two_w else pm

        name = parse_card_name(d.get("name", ""))
        if len(name) > 30:
            name = name[:29] + "…"
        pokemon = get_pokemon_name(name)

        # Ratio
        ratio_now = round(pm / am, 1) if am > 0 else 0
        ratio_prev = round(pm_prev / am_prev, 1) if am_prev > 0 else 0

        cards.append({
            "id": pid, "name": name, "pokemon": pokemon,
            "a": am, "p": pm, "a_prev": am_prev, "p_prev": pm_prev,
            "wc": wc,
            "pch": pch_yen, "ach": ach_yen,
            "p_mch": p_mch, "a_mch": a_mch,
            "max_ch": max_ch,
            "ratio_now": ratio_now, "ratio_prev": ratio_prev,
        })

    cards.sort(key=lambda x: x["max_ch"], reverse=True)
    return cards


# ============================================================
# BOX候補取得
# ============================================================

def get_box_candidates():
    if not os.path.exists(BOX_CACHE):
        return []
    with open(BOX_CACHE, "r", encoding="utf-8") as f:
        box_cache = json.load(f)
    one_w = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    two_w = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    four_w = (datetime.now() - timedelta(days=28)).strftime("%Y-%m-%d")

    boxes = []
    for pid, d in box_cache.items():
        if not d.get("is_box") or d.get("skipped"):
            continue
        prices = d.get("prices", [])
        dates = d.get("dates", [])
        if not prices or not dates:
            continue
        wc = sum(1 for dt in dates if dt >= one_w)
        if wc < 100:
            continue
        w1 = [p for dt, p in zip(dates, prices) if dt >= one_w]
        w2 = [p for dt, p in zip(dates, prices) if two_w <= dt < one_w]
        w4 = [p for dt, p in zip(dates, prices) if four_w <= dt < one_w]
        if not w1 or not w2:
            continue
        med1 = statistics.median(w1)
        med2 = statistics.median(w2)
        med4 = statistics.median(w4) if w4 else med2
        if med2 <= 0:
            continue
        ch_yen = int(med1 - med2)
        mch_yen = int(med1 - med4)
        if abs(ch_yen) < 800:
            continue

        name = shorten_box_name(d.get("name", ""))
        if len(name) > 30:
            name = name[:29] + "…"

        msrp = d.get("msrp", 0)
        listings = d.get("listing_count", 0)

        boxes.append({
            "id": pid, "name": name, "wc": wc,
            "ch": ch_yen, "mch": mch_yen,
            "med": int(med1), "med_prev": int(med4),
            "msrp": msrp, "listings": listings,
        })

    boxes.sort(key=lambda x: abs(x["ch"]), reverse=True)
    return boxes


# ============================================================
# ポスト文生成: カード
# ============================================================

def classify_card_movement(card):
    """カードの動きを分類（週間+月間の両方を考慮して矛盾を防ぐ）"""
    pch = card["pch"] or 0
    ach = card["ach"] or 0
    p_mch = card["p_mch"] or 0
    a_mch = card["a_mch"] or 0

    # 週間の方向判定
    # ±500円未満は「あまり動いてない」扱い（完全に動いてないとは言わない）
    small = 500
    p_moving = abs(pch) >= small
    a_moving = abs(ach) >= small
    p_dir = 1 if pch > 0 else (-1 if pch < 0 else 0)
    a_dir = 1 if ach > 0 else (-1 if ach < 0 else 0)

    # 両方動いてて逆方向
    if p_moving and a_moving and p_dir != a_dir:
        return "diverge"
    # 両方動いてて同方向（上昇）
    elif p_moving and a_moving and p_dir > 0 and a_dir > 0:
        return "both_up"
    # 両方動いてて同方向（下落）
    elif p_moving and a_moving and p_dir < 0 and a_dir < 0:
        return "both_down"
    # 片方だけ動いてる（もう片方は±500未満）
    elif p_moving and not a_moving:
        return "psa10_only"
    elif a_moving and not p_moving:
        return "bihin_only"
    # どっちも動いてない（ここには来ないはずだが念のため）
    else:
        return "both_up" if pch + ach > 0 else "both_down"


def make_card_text(card):
    """カードのポスト文を生成（B型7割/C型3割）"""
    pch = card["pch"] or 0
    ach = card["ach"] or 0
    movement = classify_card_movement(card)
    is_up = (abs(pch) >= abs(ach) and pch > 0) or (abs(ach) > abs(pch) and ach > 0)
    emoji = "📈" if is_up else "📉"

    # B型 or C型を選択（7:3）
    use_story = random.random() < 0.3

    # --- 見出し ---
    if use_story:
        headline = random.choice(HEADLINE_C_CARD).format(name=card["name"])
    else:
        if movement == "diverge":
            headline = random.choice(HEADLINE_B_CARD_DIVERGE).format(name=card["name"])
        elif movement == "both_up":
            headline = random.choice(HEADLINE_B_CARD_BOTH_UP).format(name=card["name"])
        elif movement == "both_down":
            headline = random.choice(HEADLINE_B_CARD_BOTH_DOWN).format(name=card["name"])
        else:
            # psa10_only or bihin_only
            grade = "PSA10" if movement == "psa10_only" else "美品"
            headline = random.choice(HEADLINE_B_CARD_ONE_SIDE).format(name=card["name"], grade=grade)

    # --- データ行 ---
    # 表記揺れ: ¥付き or 万単位をランダム
    use_man = random.random() < 0.3 and card["p"] >= 10000
    p_str = fmt_short(card["p"]) if use_man else fmt(card["p"])
    a_str = fmt_short(card["a"]) if use_man else fmt(card["a"])
    pch_str = fmt_change(pch)
    ach_str = fmt_change(ach)

    if use_story:
        if random.random() < 0.5:
            data_line = DATA_LINE_STORY_PSA.format(p=p_str, pch=pch_str, a=a_str, ach=ach_str)
        else:
            data_line = DATA_LINE_STORY_BIHIN.format(p=p_str, pch=pch_str, a=a_str, ach=ach_str)
    else:
        if random.random() < 0.5:
            data_line = DATA_LINE_PSA_FIRST.format(p=p_str, pch=pch_str, a=a_str, ach=ach_str)
        else:
            data_line = DATA_LINE_BIHIN_FIRST.format(p=p_str, pch=pch_str, a=a_str, ach=ach_str)

    # --- 締め行（事実ベース） ---
    p_mch_str = fmt_change(card["p_mch"]) if card["p_mch"] else "±¥0"
    a_mch_str = fmt_change(card["a_mch"]) if card["a_mch"] else "±¥0"

    if movement == "diverge":
        closing = random.choice(CLOSING_DIVERGE).format(
            wc=card["wc"], p_mch=p_mch_str, a_mch=a_mch_str
        )
    elif movement == "both_up":
        closing = random.choice(CLOSING_BOTH_UP).format(
            wc=card["wc"], p_mch=p_mch_str, a_mch=a_mch_str
        )
    elif movement == "both_down":
        closing = random.choice(CLOSING_BOTH_DOWN).format(
            wc=card["wc"], p_mch=p_mch_str, a_mch=a_mch_str
        )
    else:
        # one_side
        if movement == "psa10_only":
            move_grade = "PSA10"
            still_grade = "美品"
            mch = p_mch_str
        else:
            move_grade = "美品"
            still_grade = "PSA10"
            mch = a_mch_str
        closing = random.choice(CLOSING_ONE_SIDE).format(
            move_grade=move_grade, still_grade=still_grade,
            wc=card["wc"], mch=mch
        )

    # --- 組み立て ---
    text = f"{headline}\n\n{data_line}"

    url = f"{SITE_URL}/cards/{card['id']}.html"
    return text, url


# ============================================================
# ポスト文生成: BOX
# ============================================================

def make_box_text(box):
    """BOXのポスト文を生成"""
    is_up = box["ch"] > 0
    ch_str = fmt_change(box["ch"])
    mch_str = fmt_change(box["mch"])
    med_str = fmt(box["med"])
    med_prev_str = fmt(box["med_prev"])
    msrp_str = fmt(box["msrp"]) if box["msrp"] else "不明"
    ratio = round(box["med"] / box["msrp"], 1) if box["msrp"] and box["msrp"] > 0 else 0

    # B型 or C型（7:3）
    use_story = random.random() < 0.3

    if use_story:
        headline = random.choice(HEADLINE_C_BOX).format(name=box["name"])
    else:
        headlines = HEADLINE_B_BOX_UP if is_up else HEADLINE_B_BOX_DOWN
        headline = random.choice(headlines).format(name=box["name"])

    data_line = random.choice(DATA_LINE_BOX).format(med=med_str, ch=ch_str, wc=box["wc"], listings=box["listings"])

    closings = CLOSING_BOX_UP if is_up else CLOSING_BOX_DOWN
    closing = random.choice(closings).format(
        med_prev=med_prev_str, mch=mch_str,
        listings=box["listings"]
    )

    text = f"{headline}\n\n{data_line}"

    url = f"{SITE_URL}/box/{box['id']}.html"
    return text, url


# ============================================================
# ポスト文生成: 指数
# ============================================================

def make_index_text(index_data, history=None):
    """ポケカ指数ポスト生成"""
    latest, prev = index_data
    a_idx = latest["a_idx"]
    p_idx = latest["p_idx"]
    a_diff = a_idx - prev["a_idx"]
    p_diff = p_idx - prev["p_idx"]
    a_pct = round(a_diff / prev["a_idx"] * 100, 2) if prev["a_idx"] > 0 else 0
    p_pct = round(p_diff / prev["p_idx"] * 100, 2) if prev["p_idx"] > 0 else 0
    d = latest["d"]
    mon = int(d[5:7])
    day = int(d[8:10])

    # 月間変動（30日前のデータと比較）
    p_mch = 0
    a_mch = 0
    if history and len(history) > 30:
        month_ago = history[-31]
        p_mch = p_idx - month_ago.get("p_idx", p_idx)
        a_mch = a_idx - month_ago.get("a_idx", a_idx)
    p_mch_str = fmt_change(p_mch)
    a_mch_str = fmt_change(a_mch)

    def pct_str(v):
        return f"+{v}%" if v >= 0 else f"{v}%"

    # トレンド判定（月間変動ベースで判定）
    if p_mch > 0 and a_mch > 0:
        trend_key = "both_up"
    elif p_mch < 0 and a_mch < 0:
        trend_key = "both_down"
    elif p_mch > 0 and a_mch <= 0:
        trend_key = "p_up_a_down"
    elif p_mch <= 0 and a_mch > 0:
        trend_key = "p_down_a_up"
    else:
        trend_key = "flat"

    trend_comment = random.choice(TREND_COMMENTS[trend_key])

    headline = random.choice(HEADLINE_INDEX)

    date_line = f"{mon}月{day}日時点"
    data_lines = (
        f"✨ 美品指数: ¥{a_idx:,}（前日比{fmt_change(a_diff)} / {pct_str(a_pct)}）\n"
        f"💎 PSA10指数: ¥{p_idx:,}（前日比{fmt_change(p_diff)} / {pct_str(p_pct)}）"
    )

    # 週間変動（7日前のデータと比較）
    p_wch = 0
    a_wch = 0
    if history and len(history) > 7:
        week_ago = history[-8]
        p_wch = p_idx - week_ago.get("p_idx", p_idx)
        a_wch = a_idx - week_ago.get("a_idx", a_idx)
    p_wch_str = fmt_change(p_wch)
    a_wch_str = fmt_change(a_wch)

    closing = random.choice(CLOSING_INDEX).format(
        p_mch=p_mch_str, a_mch=a_mch_str,
        p_wch=p_wch_str, a_wch=a_wch_str,
        trend_comment=trend_comment
    )

    text = f"{headline}\n\n{date_line}\n{data_lines}"
    url = f"{SITE_URL}/index-chart.html"
    return text, url


# ============================================================
# HTML生成
# ============================================================

def generate_html(tweets):
    now = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    items = ""
    for i, (text, url, card_img) in enumerate(tweets):
        esc = html_mod.escape(text)
        imgs = ""
        if card_img:
            imgs = f'<div style="margin-top:8px"><img src="{card_img}" style="max-width:300px;max-height:400px;object-fit:cover;border-radius:8px"><br><a href="{card_img}" download="tweet_{i}.jpg" class="tw-dl">📥 画像を保存</a></div>'
        items += f'''<div class="tw"><pre class="tw-body" id="tw{i}">{esc}</pre>
<div class="tw-btns"><button class="tw-copy" onclick="copyTw({i})">📋 ポスト文コピー</button></div>
{imgs}</div>\n'''

    return f'''<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Xポスト文 - ポケカるっく</title><style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;padding:20px}}.wrap{{max-width:900px;margin:0 auto}}h1{{font-size:1.3rem;margin-bottom:8px;color:#38bdf8}}.meta{{color:#64748b;font-size:.8rem;margin-bottom:20px}}.grid{{display:flex;flex-direction:column;gap:16px}}.tw{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px}}.tw-body{{white-space:pre-wrap;font-size:.85rem;line-height:1.6;font-family:inherit;color:#f1f5f9;margin-bottom:12px}}.tw-btns{{display:flex;gap:8px;flex-wrap:wrap}}.tw-copy,.tw-dl{{padding:8px 16px;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:.8rem;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}}.tw-copy:hover{{background:#1d4ed8}}.tw-copy.done{{background:#059669}}.tw-dl{{background:#7c3aed;margin-top:8px}}.char-count{{color:#64748b;font-size:.75rem;margin-top:4px}}</style></head><body><div class="wrap"><h1>📝 今日のXポスト文</h1><p class="meta">生成日時: {now} JST ｜ 画像付きで投稿</p><div class="grid">{items}</div></div><script>
function copyTw(i){{const el=document.getElementById('tw'+i);const ta=document.createElement('textarea');ta.value=el.textContent;ta.style.cssText='position:fixed;left:-9999px';document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);const btn=el.parentElement.querySelector('.tw-copy');btn.textContent='✅ コピー済み';btn.classList.add('done');setTimeout(()=>{{btn.textContent='📋 ポスト文コピー';btn.classList.remove('done')}},2000)}}
</script></body></html>'''


# ============================================================
# メイン
# ============================================================

def main():
    if not os.path.exists(PRICE_CACHE):
        print(f"エラー: {PRICE_CACHE} が見つかりません")
        sys.exit(1)

    posted = clean_posted(load_posted())
    cards = get_card_candidates()
    boxes = get_box_candidates()
    print(f"カード候補: {len(cards)}枚, BOX候補: {len(boxes)}個")

    tweets = []

    # --- 指数ポスト ---
    if os.path.exists("index_history.json"):
        try:
            with open("index_history.json", "r", encoding="utf-8") as f:
                ih = json.load(f)
                if len(ih) >= 2:
                    index_data = (ih[-1], ih[-2])
                    text, url = make_index_text(index_data, history=ih)
                    idx_img = "images/tw_index.jpg"
                    tweets.append((text, url, idx_img))
        except Exception as e:
            print(f"指数データ読み込み失敗: {e}")

    # --- カード2本選定 ---
    card_count = 0
    for card in cards:
        if card_count >= 2:
            break
        if is_recently_used(posted, card_id=card["id"], pokemon=card["pokemon"]):
            continue
        text, url = make_card_text(card)
        card_img = f"images/tw_{card['id']}.jpg"
        tweets.append((text, url, card_img))
        posted.append({"id": card["id"], "pokemon": card["pokemon"], "ts": datetime.now(JST).isoformat()})
        card_count += 1

    # 重複排除で足りない場合
    if card_count < 2 and cards:
        for card in cards:
            if card_count >= 2:
                break
            # 既に選んだカードはスキップ
            if any(p.get("id") == card["id"] for p in posted if "pokemon" in p):
                continue
            text, url = make_card_text(card)
            card_img = f"images/tw_{card['id']}.jpg"
            tweets.append((text, url, card_img))
            posted.append({"id": card["id"], "pokemon": card["pokemon"], "ts": datetime.now(JST).isoformat()})
            card_count += 1

    # --- BOX2本選定 ---
    box_count = 0
    for box in boxes:
        if box_count >= 2:
            break
        if is_recently_used(posted, card_id=f"box_{box['id']}"):
            continue
        text, url = make_box_text(box)
        box_img = f"images/tw_box_{box['id']}.jpg"
        tweets.append((text, url, box_img))
        posted.append({"id": f"box_{box['id']}", "ts": datetime.now(JST).isoformat()})
        box_count += 1

    if box_count < 2 and boxes:
        for box in boxes:
            if box_count >= 2:
                break
            if any(p.get("id") == f"box_{box['id']}" for p in posted if "pokemon" not in p):
                continue
            text, url = make_box_text(box)
            box_img = f"images/tw_box_{box['id']}.jpg"
            tweets.append((text, url, box_img))
            posted.append({"id": f"box_{box['id']}", "ts": datetime.now(JST).isoformat()})
            box_count += 1
    # --- HTML生成 ---
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(generate_html(tweets))
    save_posted(posted)

    print(f"生成完了: {OUTPUT_HTML} ({len(tweets)}件)")
    for text, url, _ in tweets:
        cc = x_char_count(text)
        print(f"\n--- ({cc}/280文字 = 日本語約{cc//2}文字) ---")
        print(text)
        print(f"[URL] {url}")


if __name__ == "__main__":
    main()
