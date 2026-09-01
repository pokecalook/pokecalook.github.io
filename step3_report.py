"""
Step 3: HTMLレポート生成（大量データ対応版）
使い方: python step3_report.py [--top 0]

price_data_api.json → report.html
- 遅延描画（IntersectionObserver）で3000件でも快適
- ページネーション（50件/ページ）
- ソート（状態A / PSA10 / 倍率 / トレンド）
- スパークライン（直近90日）
"""

import json
import math
import os
import re
import sys
import argparse
import html as htmllib
import statistics
import urllib.parse
from common_html import get_header, get_nav, get_footer, get_gtag, get_meta_keywords, get_brand_bar
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

INPUT_FILE = "product_links.json"
PRICE_CACHE_FILE = "price_data_api.json"
OUTPUT_HTML = "report.html"


def load_products():
    if not os.path.exists(INPUT_FILE):
        return {}
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_price_cache():
    if not os.path.exists(PRICE_CACHE_FILE):
        print(f"エラー: {PRICE_CACHE_FILE} が見つかりません。")
        sys.exit(1)
    with open(PRICE_CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def name_to_pokeca_chart_url(name):
    """商品名からpokeca-chart.comのURLを生成。
    例: 'ルカリオVSTAR SAR[s12a 226/172](...)' → 'https://grading.pokeca-chart.com/s12a-226-172'
    例: 'ピカチュウ S [SV4a 236/190](...)' → 'https://grading.pokeca-chart.com/sv4a-236-190'
    """
    # [セット番号 カード番号/分母] パターンを抽出
    m = re.search(r'\[([A-Za-z0-9]+)\s+(\d+)/(\d+)\]', name)
    if m:
        set_id = m.group(1).lower()
        card_no = m.group(2)
        denom = m.group(3)
        return f"https://grading.pokeca-chart.com/{set_id}-{card_no}-{denom}"
    # [セット番号 カード番号] パターン（分母なし）
    m2 = re.search(r'\[([A-Za-z0-9-]+)\s+(\d+)\]', name)
    if m2:
        set_id = m2.group(1).lower()
        card_no = m2.group(2)
        return f"https://grading.pokeca-chart.com/{set_id}-{card_no}"
    return ""


def build_card_data(cache, top=0):
    products_order = load_products()
    order_map = {pid: idx for idx, pid in enumerate(products_order.keys(), 1)}

    now = datetime.now()
    one_month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    one_week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    two_weeks_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    cards = []
    for pid, data in cache.items():
        if not data.get("is_single_card"):
            continue

        # --- SOLDデータから状態別に分離 ---
        sold_data = data.get("sold_data", [])
        if not sold_data:
            continue
        if len(sold_data) < 10:
            continue
        sold_a = [(s["date"], s["price"]) for s in sold_data if s["condition"] == "A"]
        sold_psa10 = [(s["date"], s["price"]) for s in sold_data if s["condition"] == "PSA10"]
        # 日付順にソート
        sold_a.sort(key=lambda x: x[0])
        sold_psa10.sort(key=lambda x: x[0])
        a_dates = [d for d, _ in sold_a]
        a_prices = [p for _, p in sold_a]
        p_dates = [d for d, _ in sold_psa10]
        p_prices = [p for _, p in sold_psa10]

        if not a_prices:
            continue

        # 直近7日間の中央値を算出
        one_week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        a_recent_7d = [p for d, p in zip(a_dates, a_prices) if d >= one_week_ago]
        p_recent_7d = [p for d, p in zip(p_dates, p_prices) if d >= one_week_ago]
        a_med = int(statistics.median(a_recent_7d)) if a_recent_7d else int(statistics.median(a_prices[-5:]))
        p_med = int(statistics.median(p_recent_7d)) if p_recent_7d else (int(statistics.median(p_prices[-5:])) if p_prices else 0)
        if a_med <= 0:
            continue
        ratio = round(p_med / a_med, 2) if p_med > 0 else 0

        # SOLDデータはサイズ確定済みなのでフィルタ不要
        a_dates_clean, a_prices_clean = a_dates, a_prices
        p_dates_clean, p_prices_clean = p_dates, p_prices

        # weekly medians
        def wk(dates, prices, w):
            s = (now - timedelta(days=7*w)).strftime("%Y-%m-%d")
            e = (now - timedelta(days=7*(w-1))).strftime("%Y-%m-%d")
            wp = [p for d, p in zip(dates, prices) if s <= d < e]
            return int(statistics.median(wp)) if wp else None

        a_wk = [wk(a_dates_clean, a_prices_clean, w) for w in range(4, 0, -1)]
        p_wk = [wk(p_dates_clean, p_prices_clean, w) for w in range(4, 0, -1)]

        # 週間変動額 (PSA10): 直近7日中央値 - 前週7日中央値
        p1w = [p for d, p in zip(p_dates_clean, p_prices_clean) if d >= one_week_ago]
        p2w = [p for d, p in zip(p_dates_clean, p_prices_clean) if two_weeks_ago <= d < one_week_ago]
        trend = None
        if p1w and p2w:
            mn, mp = statistics.median(p1w), statistics.median(p2w)
            trend = int(mn - mp)

        # 週間変動額 (美品)
        a1w = [p for d, p in zip(a_dates_clean, a_prices_clean) if d >= one_week_ago]
        a2w = [p for d, p in zip(a_dates_clean, a_prices_clean) if two_weeks_ago <= d < one_week_ago]
        a_trend = None
        if a1w and a2w:
            amn, amp = statistics.median(a1w), statistics.median(a2w)
            a_trend = int(amn - amp)

        # sparkline (全期間 daily median — JS側で期間切り替え)
        def spark(dates, prices):
            by_d = {}
            for d, p in zip(dates, prices):
                by_d.setdefault(d, []).append(p)
            return [[d, int(statistics.median(v))] for d, v in sorted(by_d.items())]

        # お買い得スコア削除（取引件数ソートに置き換え）
        total_trades = len(a_prices_clean) + len(p_prices_clean)

        # レアリティ抽出
        card_name = htmllib.unescape(data.get("name", pid))
        en_name_decoded = htmllib.unescape(data.get("en_name", ""))
        rarity = ""
        before_bracket = re.sub(r'\[.*$', '', card_name).strip()
        before_bracket = re.sub(r'\(.*?\)', '', before_bracket).strip()
        name_words = before_bracket.split()
        for wi in range(len(name_words) - 1, 0, -1):
            if name_words[wi] in {"SAR", "SR", "AR", "RR", "RRR", "UR", "HR", "SSR", "S",
                                   "MA", "MUR", "CHR", "CSR", "K", "P", "PR", "C", "U", "R",
                                   "TR", "FA", "GX", "EX", "V", "VMAX", "VSTAR", "ex"}:
                rarity = name_words[wi]
                break

        # 検索用テキスト生成
        # カード番号抽出: 複数パターンに対応
        #  [s12a 226/172] → 226
        #  [001/SV-P] → 001 (番号/セット順)
        #  [SVP EN 085] → 085 (スペース混在セット)
        #  [PROMO339/S-P] → 339 (PROMO接頭+番号)
        #  [SM3+ 041/072] → 041
        #  [XY-P 175/XY-P] → 175 (真ん中の番号)
        #  [PROMO339 S-P] → 339 (数字直後にスペース)
        card_num = ""
        bracket_texts = re.findall(r'\[([^\[\]]+)\]', card_name)
        if not bracket_texts and data.get("en_name"):
            bracket_texts = re.findall(r'\[([^\[\]]+)\]', data.get("en_name", ""))
        for bt in bracket_texts:
            bt = bt.strip()
            # パターン1: 末尾が数字 or 数字/数字 (例: [s12a 226/172], [SVP EN 085])
            m = re.search(r'(\d+)(?:/\d+)?\s*$', bt)
            if m:
                card_num = m.group(1).lstrip("0") or "0"
                break
            # パターン2: "001/XX-X" (先頭が番号/セット)
            m = re.match(r'^\s*(\d+)\s*/', bt)
            if m:
                card_num = m.group(1).lstrip("0") or "0"
                break
            # パターン3: 真ん中にある "数字" or "数字/X" を拾う (例: [XY-P 175/XY-P], [BW-P 144/BW-P])
            m = re.search(r'(?:^|\s)(\d+)(?:/[A-Za-z]|/\d+)', bt)
            if m:
                card_num = m.group(1).lstrip("0") or "0"
                break
            # パターン4: "PROMO339 S-P" のように文字+数字の塊から数字を拾う
            m = re.search(r'(\d+)', bt)
            if m:
                card_num = m.group(1).lstrip("0") or "0"
                break
        # ポケモン名+レアリティ（日本語）: "ルカリオVSTAR SAR"
        search_name = before_bracket  # レアリティ含む

        cards.append({
            "id": pid,
            "n": card_name,
            "en": en_name_decoded,
            "yr": data.get("release_year", ""),
            "img": f"images/{pid}.webp" if os.path.exists(os.path.join("images", f"{pid}.webp")) else data.get("image_url", ""),
            "a": int(a_med),
            "p": int(p_med),
            "r": ratio,
            "d": int(p_med - a_med) if p_med > 0 else 0,
            "ac": len(a_prices_clean),
            "pc": len(p_prices_clean),
            "t": trend,
            "at": a_trend,
            "mt": int(a_wk[3] - a_wk[0]) if a_wk[0] and a_wk[3] else None,
            "pmt": int(p_wk[3] - p_wk[0]) if p_wk[0] and p_wk[3] else None,
            "sc": total_trades,
            "aw": a_wk,
            "pw": p_wk,
            "as": spark(a_dates_clean, a_prices_clean),
            "ps": spark(p_dates_clean, p_prices_clean),
            "af": a_dates_clean[0] if a_dates_clean else "",
            "al": a_dates_clean[-1] if a_dates_clean else "",
            "pf": p_dates_clean[0] if p_dates_clean else "",
            "pl": p_dates_clean[-1] if p_dates_clean else "",
            "u": f"https://snkrdunk.com/apparels/{pid}",
            "gc": name_to_pokeca_chart_url(data.get("name", "")),
            "rar": rarity,
            "sn": search_name,
            "cn": card_num,
            "gr": data.get("gem_rate"),
            "grR": data.get("gem_rate_reliable", False),
            "grT": data.get("psa_total"),
            "mla": data.get("min_listing_a"),
            "mlp": data.get("min_listing_psa10"),
        })

    cards.sort(key=lambda x: x["sc"], reverse=True)
    if top > 0:
        cards = cards[:top]
    return cards


def generate_html(cards):
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    cards_json = json.dumps(cards, ensure_ascii=False, separators=(',', ':'))

    # BOXサマリーデータ（ID+中央値）を埋め込む
    box_summary = []
    try:
        if os.path.exists("box_price_data.json"):
            with open("box_price_data.json", "r", encoding="utf-8") as bf:
                box_cache = json.load(bf)
            for pid, v in box_cache.items():
                if not v.get("is_box") or v.get("skipped"):
                    continue
                prices = v.get("prices", [])
                if not prices:
                    continue
                current = v.get("current_price", 0)
                if current <= 0:
                    continue
                # 過去3ヶ月の取引10件以上チェック
                three_mo_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
                dates = v.get("dates", [])
                recent = [p for d, p in zip(dates, prices) if d >= three_mo_ago]
                if len(recent) < 10:
                    continue
                med = int(statistics.median(recent))
                box_summary.append({"id": pid, "med": med, "cur": current})
    except Exception:
        pass
    box_summary_json = json.dumps(box_summary, ensure_ascii=False, separators=(',', ':'))

    html = _HTML_TEMPLATE.replace("__CARDS_JSON__", cards_json)
    html = html.replace("__BOX_SUMMARY_JSON__", box_summary_json)
    html = html.replace("__NOW__", now_str)
    html = html.replace("__TOTAL__", str(len(cards)))
    html = html.replace("__FOOTER__", _FOOTER_HTML)
    html = html.replace("__GTAG__", get_gtag())
    html = html.replace("__META_KEYWORDS__", get_meta_keywords())
    html = html.replace("__HEADER__", get_header())
    html = html.replace("__NAV__", get_nav(active="single"))

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    # index.html にも同時出力（ワークフロー経由しない手動pushでも反映されるように）
    import shutil
    shutil.copy(OUTPUT_HTML, "index.html")
    print(f"HTMLレポート生成完了: {OUTPUT_HTML} → index.html")
    print(f"対象カード: {len(cards)}枚")


SITE_URL = "https://pokecalook.com"
CARDS_DIR = "cards"

RARITY_SET = {
    "SAR", "SR", "AR", "RR", "RRR", "UR", "HR", "SSR", "S",
    "MA", "MUR", "CHR", "CSR", "K", "P", "PR", "C", "U", "R",
    "TR", "FA", "GX", "EX", "V", "VMAX", "VSTAR", "ex",
}


def parse_card_name(name):
    """カード名からポケモン名、レアリティ、セット番号を抽出。
    例: 'リザードンVSTAR SAR[s12a 226/172](状態A)' → ('リザードンVSTAR', 'SAR', 's12a 226/172')
    """
    # ブラケット部分を抽出
    set_info = ""
    m = re.search(r'\[([^\]]+)\]', name)
    if m:
        set_info = m.group(1)

    # ブラケットより前の部分
    before = re.sub(r'\[.*$', '', name).strip()
    # (状態A) 等を除去
    before = re.sub(r'\(.*?\)', '', before).strip()

    # 末尾からレアリティを探す
    words = before.split()
    rarity = ""
    pokemon = before
    for i in range(len(words) - 1, 0, -1):
        if words[i] in RARITY_SET:
            rarity = words[i]
            pokemon = " ".join(words[:i])
            break

    return pokemon, rarity, set_info


def fmt_price(v):
    if v <= 0:
        return "データなし"
    return f"¥{v:,}"


def build_card_analysis(c, pokemon, rarity, set_info):
    """カードデータから日本語の解説文を自動生成"""
    parts = []
    pokemon_esc = _esc(pokemon) if pokemon else "このカード"
    rarity_text = f"{rarity}" if rarity else ""
    rarity_phrase = f"レアリティ「{rarity}」の" if rarity else ""

    a = c.get("a", 0) or 0
    p = c.get("p", 0) or 0
    r = c.get("r", 0) or 0
    diff = c.get("d", 0) or 0
    ac = c.get("ac", 0) or 0
    pc = c.get("pc", 0) or 0
    t_w = c.get("t")    # PSA10 週間変動額
    at_w = c.get("at")  # 美品 週間変動額
    t_m = c.get("pmt")  # PSA10 1ヶ月変動額
    at_m = c.get("mt")  # 美品 1ヶ月変動額

    # --- 概要 ---
    parts.append('<h2>📝 このカードの相場概要</h2>')
    overview = []
    overview.append(f'{pokemon_esc}（{rarity_phrase}ポケモンカード）の')
    if a > 0 and p > 0:
        overview.append(f'直近7日間の取引中央値は、美品が <span class="hl">¥{a:,}</span>、PSA10が <span class="hl">¥{p:,}</span> となっています。')
        overview.append(f'美品とPSA10の差額は <span class="hl">¥{diff:,}</span>、倍率は <span class="hl">{r:.1f}倍</span> です。')
    elif a > 0:
        overview.append(f'美品の直近7日間の取引中央値は <span class="hl">¥{a:,}</span> です。PSA10の取引データはまだ十分に蓄積されていません。')
    elif p > 0:
        overview.append(f'PSA10の直近7日間の取引中央値は <span class="hl">¥{p:,}</span> です。美品の取引データはまだ十分に蓄積されていません。')
    else:
        overview.append('取引データの蓄積が不十分なため、現在の相場は明確ではありません。')
    parts.append(f'<p>{"".join(overview)}</p>')

    # --- 倍率の評価 ---
    if a > 0 and p > 0 and r > 0:
        parts.append('<h3>🎯 PSA10鑑定の妙味</h3>')
        if r >= 4:
            parts.append(f'<p>倍率は <span class="up">{r:.1f}倍</span> と高水準です。美品の状態が良好でPSA10を取得できれば、鑑定費用（一般的には1枚あたり数千円〜）を考慮しても利益が出やすい水準と言えます。ただし、実際にPSA10が取得できる確率はカードの個体差・印刷ロット・センタリング・コーナーの状態などに強く依存するため、過信は禁物です。</p>')
        elif r >= 3:
            parts.append(f'<p>倍率は <span class="flat">{r:.1f}倍</span> です。鑑定の妙味は中程度で、PSA10取得率と鑑定費用を慎重に試算する必要があります。状態に自信がある個体に絞って鑑定に出すのが賢明でしょう。</p>')
        elif r >= 2:
            parts.append(f'<p>倍率は <span class="flat">{r:.1f}倍</span> と控えめです。鑑定費用と返送リスクを考慮すると、利益を出すハードルは低くありません。よほど状態に自信がある場合や、コレクション目的でPSA10を所有したい場合に限って鑑定を検討するのが無難です。</p>')
        else:
            parts.append(f'<p>倍率は <span class="down">{r:.1f}倍</span> と低めです。鑑定費用を回収しづらい水準のため、現状では美品のまま売却したほうが手取りが多くなる可能性が高いと考えられます。</p>')

    # --- 価格動向 ---
    parts.append('<h3>📈 直近の価格動向</h3>')
    trend_lines = []

    def trend_word(v):
        if v is None:
            return None
        if abs(v) < 100:
            return ('flat', '横ばい', f'±¥{abs(v):,}')
        if v > 0:
            return ('up', '上昇', f'+¥{v:,}')
        return ('down', '下落', f'-¥{abs(v):,}')

    psa_w = trend_word(t_w)
    bi_w = trend_word(at_w)
    psa_m = trend_word(t_m)
    bi_m = trend_word(at_m)

    # 週間
    if psa_w and bi_w:
        if psa_w[1] == bi_w[1] == '上昇':
            trend_lines.append(f'直近1週間で美品が <span class="{bi_w[0]}">{bi_w[2]}</span>、PSA10が <span class="{psa_w[0]}">{psa_w[2]}</span> と、美品・PSA10の両方が値上がりしました。連動して上昇しているため、市場全体でこのカードへの需要が高まっていると考えられます。')
        elif psa_w[1] == bi_w[1] == '下落':
            trend_lines.append(f'直近1週間で美品が <span class="{bi_w[0]}">{bi_w[2]}</span>、PSA10が <span class="{psa_w[0]}">{psa_w[2]}</span> と、美品・PSA10ともに値下がりしました。需要の落ち着きや、相場の調整局面に入っている可能性があります。')
        elif psa_w[1] == bi_w[1] == '横ばい':
            trend_lines.append(f'直近1週間は美品 <span class="{bi_w[0]}">{bi_w[2]}</span>、PSA10 <span class="{psa_w[0]}">{psa_w[2]}</span> と、ほぼ動きのない安定した相場でした。')
        else:
            trend_lines.append(f'直近1週間で美品が <span class="{bi_w[0]}">{bi_w[2]}（{bi_w[1]}）</span>、PSA10が <span class="{psa_w[0]}">{psa_w[2]}（{psa_w[1]}）</span> と、片方だけが大きく動く展開になっています。グレード別の需給バランスに変化がある可能性があり、注意が必要です。')
    elif psa_w:
        trend_lines.append(f'直近1週間でPSA10価格は <span class="{psa_w[0]}">{psa_w[2]}（{psa_w[1]}）</span> しています。')
    elif bi_w:
        trend_lines.append(f'直近1週間で美品価格は <span class="{bi_w[0]}">{bi_w[2]}（{bi_w[1]}）</span> しています。')

    # 1ヶ月
    if psa_m and bi_m:
        trend_lines.append(f'直近1ヶ月では美品 <span class="{bi_m[0]}">{bi_m[2]}</span>、PSA10 <span class="{psa_m[0]}">{psa_m[2]}</span> という推移です。')
    elif psa_m:
        trend_lines.append(f'直近1ヶ月のPSA10価格は <span class="{psa_m[0]}">{psa_m[2]}</span> 動きました。')
    elif bi_m:
        trend_lines.append(f'直近1ヶ月の美品価格は <span class="{bi_m[0]}">{bi_m[2]}</span> 動きました。')

    if trend_lines:
        for line in trend_lines:
            parts.append(f'<p>{line}</p>')
    else:
        parts.append('<p>変動データを算出するための十分なサンプルがまだ揃っていないため、明確なトレンドは示せません。今後データが蓄積され次第、表示が更新されます。</p>')

    # --- 取引データの厚み ---
    parts.append('<h3>📊 取引データの信頼性</h3>')
    total = ac + pc
    if total >= 50:
        reliability = '<span class="up">高い</span>'
        reliability_msg = 'サンプル数が十分にあるため、表示されている中央値は実態に近い相場を反映していると考えられます。'
    elif total >= 20:
        reliability = '<span class="flat">中程度</span>'
        reliability_msg = 'サンプル数は一定程度あるものの、外れ値の影響を受ける余地は残っています。中央値を目安にしつつ、複数日のデータを横断的に確認することをおすすめします。'
    else:
        reliability = '<span class="down">限定的</span>'
        reliability_msg = '取引件数が少ないため、表示価格は参考値として扱ってください。サンプルが増えるにつれて精度が上がります。'
    parts.append(f'<p>このカードの取引件数は美品 <span class="hl">{ac}件</span>、PSA10 <span class="hl">{pc}件</span> で、データの信頼性は{reliability}です。{reliability_msg}</p>')

    # --- アクション提案 ---
    parts.append('<h3>💡 こんな方におすすめ</h3>')
    suggestions = []
    if r >= 3 and a > 0 and ac >= 5:
        suggestions.append('美品で所有しているなら、PSA鑑定に出すかどうかを検討する価値があります。')
    if psa_w and psa_w[1] == '上昇' and t_w and t_w >= 1000:
        suggestions.append('PSA10価格が上昇トレンドのため、鑑定済みカードを所有している方は売却タイミングを意識してもよいかもしれません。')
    if psa_w and psa_w[1] == '下落' and t_w and t_w <= -1000:
        suggestions.append('PSA10価格が下落しているため、いま買い増すか様子を見るかの判断が分かれる局面です。')
    if a > 30000:
        suggestions.append('価格帯が高めのカードのため、購入時は出品状態の写真を入念に確認することをおすすめします。')
    if not suggestions:
        suggestions.append('シンプルな相場確認として、お気に入り登録をして日々の動きを追ってみてください。')
    parts.append('<ul>')
    for s in suggestions:
        parts.append(f'<li>{s}</li>')
    parts.append('</ul>')

    parts.append('<p style="font-size:.75rem;color:#9ca3af;margin-top:12px">※ 投資・売買・鑑定の最終判断はご自身の責任で行ってください。</p>')

    return "\n".join(parts)


def generate_card_pages(cards):
    """各カードの個別HTMLページを cards/ ディレクトリに生成"""
    os.makedirs(CARDS_DIR, exist_ok=True)
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    # 取引10件未満のカードは除外
    cards = [c for c in cards if c.get("sc", 0) >= 10]

    for c in cards:
        pid = c["id"]
        pokemon, rarity, set_info = parse_card_name(c["n"])
        rarity_text = f" {rarity}" if rarity else ""

        # SEO用テキスト
        title = f"{_esc(c['n'])} 相場・PSA10価格推移 | ポケカるっく"
        if c["p"] > 0:
            desc = f"{pokemon}{rarity_text} の美品・PSA10相場を毎日更新。美品 {fmt_price(c['a'])} → PSA10 {fmt_price(c['p'])}（{c['r']:.1f}倍）"
        else:
            desc = f"{pokemon}{rarity_text} の美品相場を毎日更新。美品 {fmt_price(c['a'])}。PSA10の取引データなし。"

        card_json = json.dumps(c, ensure_ascii=False, separators=(',', ':'))

        # JSON-LD 構造化データ
        jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "Product",
            "name": f"{pokemon}{rarity_text} PSA10",
            "description": desc,
            "image": f"{SITE_URL}/images/{pid}.webp",
            "offers": {
                "@type": "AggregateOffer",
                "priceCurrency": "JPY",
                "lowPrice": c["a"],
                "highPrice": c["p"] if c["p"] > 0 else c["a"],
            }
        }, ensure_ascii=False, separators=(',', ':'))

        html = _CARD_PAGE_TEMPLATE
        html = html.replace("__GTAG_CARD__", get_gtag())
        html = html.replace("__CARD_BRAND_BAR__", get_brand_bar())
        html = html.replace("__CARD_HEADER__", get_header(prefix="../"))
        html = html.replace("__CARD_NAV__", get_nav(prefix="../", active="single"))
        # 取引20件未満はnoindexにする（AdSense審査対策）
        total_trades = c.get("sc", 0)
        if total_trades < 20:
            html = html.replace("__NOINDEX__", '<meta name="robots" content="noindex">')
        else:
            html = html.replace("__NOINDEX__", "")
        html = html.replace("__FOOTER__", _FOOTER_HTML_REL)
        html = html.replace("__TITLE__", _esc(title))
        html = html.replace("__DESC__", _esc(desc))
        html = html.replace("__POKEMON__", _esc(pokemon))
        html = html.replace("__RARITY__", _esc(rarity_text))
        html = html.replace("__CARD_NAME__", _esc(c["n"]))
        html = html.replace("__CARD_JSON__", card_json)
        html = html.replace("__JSONLD__", jsonld)
        html = html.replace("__NOW__", now_str)
        html = html.replace("__URL__", f"{SITE_URL}/cards/{pid}.html")
        html = html.replace("__IMG__", f"../images/{pid}.webp")
        # OGP画像はフルURL
        html = html.replace(f'content="../images/{pid}.webp"', f'content="{SITE_URL}/images/{pid}.webp"')
        html = html.replace("__PRICE_A__", fmt_price(c["a"]))
        html = html.replace("__PRICE_P__", fmt_price(c["p"]))
        html = html.replace("__RATIO__", f"{c['r']:.1f}")
        rc = "r-hot" if c["r"] >= 4 else "r-warm" if c["r"] >= 3 else "r-cool"
        html = html.replace("__RATIO_CLASS__", rc)
        html = html.replace("__SNKR_URL__", c.get("u", ""))
        # メルカリ・カードラッシュ検索URL
        _sn = c.get("sn", "")
        _cn = c.get("cn", "")
        html = html.replace("__MERCARI_URL__", f"https://jp.mercari.com/search?keyword={urllib.parse.quote(_sn)}&category_id=1289" if _sn else "")
        html = html.replace("__CARDRUSH_URL__", f"https://www.cardrush-pokemon.jp/product-list?keyword={urllib.parse.quote(_sn + (' ' + _cn if _cn else ''))}" if _sn else "")
        html = html.replace("__DIFF__", fmt_price(c["d"]))
        html = html.replace("__A_COUNT__", str(c["ac"]))
        html = html.replace("__P_COUNT__", str(c["pc"]))
        html = html.replace("__MIN_A__", fmt_price(c.get("mla")) if c.get("mla") else "ー")
        html = html.replace("__MIN_P__", fmt_price(c.get("mlp")) if c.get("mlp") else "ー")
        html = html.replace("__EN_NAME__", _esc(c.get("en", "")))
        html = html.replace("__YEAR__", _esc(str(c.get("yr", ""))))
        # 変動額プレースホルダー置換
        def _fmt_delta(v):
            if v is None:
                return '<span style="color:#6b7280">ー</span>'
            sign = "+" if v > 0 else "-" if v < 0 else "±"
            col = "#0d9488" if v > 0 else "#dc2626" if v < 0 else "#2563eb"
            return f'<span style="color:{col};font-weight:700">{sign}¥{abs(v):,}</span>'

        t_w = c.get("t")   # PSA10 週間変動額
        at_w = c.get("at") # 美品 週間変動額
        t_m = c.get("pmt") # PSA10 1ヶ月変動額
        at_m = c.get("mt") # 美品 1ヶ月変動額
        html = html.replace("__T_W__", _fmt_delta(t_w))
        html = html.replace("__AT_W__", _fmt_delta(at_w))
        html = html.replace("__T_M__", _fmt_delta(t_m))
        html = html.replace("__AT_M__", _fmt_delta(at_m))
        html = html.replace("__A_FIRST__", c.get("af", "ー") or "ー")
        html = html.replace("__A_LAST__", c.get("al", "ー") or "ー")
        html = html.replace("__P_FIRST__", c.get("pf", "ー") or "ー")
        html = html.replace("__P_LAST__", c.get("pl", "ー") or "ー")

        # Xシェア用URL
        tweet_parts = [c["n"]]
        price_parts = []
        if c["a"] > 0:
            price_parts.append(f"美品: ¥{c['a']:,}")
        if c["p"] > 0:
            price_parts.append(f"PSA10: ¥{c['p']:,}")
        if price_parts:
            tweet_parts.append(" / ".join(price_parts))
        tweet_parts.append(f"{SITE_URL}/cards/{pid}.html")
        tweet_parts.append("#ポケカるっく")
        tweet_text = "\n".join(tweet_parts)
        html = html.replace("__TWEET_ENC__", urllib.parse.quote(tweet_text))

        # 解説文の自動生成
        analysis_html = build_card_analysis(c, pokemon, rarity, set_info)
        html = html.replace("__ANALYSIS__", analysis_html)

        filepath = os.path.join(CARDS_DIR, f"{pid}.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

    print(f"個別カードページ生成完了: {len(cards)}枚 → {CARDS_DIR}/")


def _esc(s):
    """HTML属性用エスケープ"""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def generate_sitemap(cards, box_ids=None):
    """sitemap.xmlを生成"""
    # 取引20件未満のカードはnoindexなのでsitemapからも除外
    cards = [c for c in cards if c.get("sc", 0) >= 20]
    today = datetime.now(JST).strftime("%Y-%m-%d")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    # トップページ
    lines.append(f'  <url>\n    <loc>{SITE_URL}/</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>')
    # 指数チャートページ
    lines.append(f'  <url>\n    <loc>{SITE_URL}/index-chart.html</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.9</priority>\n  </url>')
    # BOXページ
    lines.append(f'  <url>\n    <loc>{SITE_URL}/box.html</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.9</priority>\n  </url>')
    # 静的ページ
    for page, prio in [("guide.html", "0.6"), ("about.html", "0.6"), ("privacy.html", "0.4"), ("contact.html", "0.5"), ("portfolio.html", "0.6")]:
        lines.append(f'  <url>\n    <loc>{SITE_URL}/{page}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>{prio}</priority>\n  </url>')
    # 記事ページ
    for page, prio in [("articles/index.html", "0.8"), ("articles/weekly-rising.html", "0.8"), ("articles/weekly-falling.html", "0.8"), ("articles/box-trends.html", "0.8")]:
        lines.append(f'  <url>\n    <loc>{SITE_URL}/{page}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>{prio}</priority>\n  </url>')
    # 個別カードページ
    for c in cards:
        lines.append(f'  <url>\n    <loc>{SITE_URL}/cards/{c["id"]}.html</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.7</priority>\n  </url>')
    # BOX詳細ページ
    if box_ids:
        for bid in box_ids:
            lines.append(f'  <url>\n    <loc>{SITE_URL}/box/{bid}.html</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.7</priority>\n  </url>')
    lines.append('</urlset>')

    total_urls = len(cards) + (len(box_ids) if box_ids else 0) + 1
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"sitemap.xml 生成完了: {total_urls} URL")


def generate_portfolio_page(cards):
    """portfolio.html（持ってるリスト管理ページ）を生成"""
    # カードデータをJSON化（ポートフォリオページで使う最小限のデータ）
    pf_data = []
    for c in cards:
        pf_data.append({
            "id": c["id"], "n": c["n"], "img": c.get("img", ""),
            "a": c["a"], "p": c["p"], "r": c["r"], "d": c["d"],
        })
    pf_json = json.dumps(pf_data, ensure_ascii=False, separators=(',', ':'))

    # BOXデータも読み込んで埋め込む
    box_pf_data = []
    try:
        if os.path.exists("box_price_data.json"):
            with open("box_price_data.json", "r", encoding="utf-8") as bf:
                import statistics
                box_cache = json.load(bf)
            for pid, v in box_cache.items():
                if not v.get("is_box") or v.get("skipped"):
                    continue
                prices = v.get("prices", [])
                if not prices:
                    continue
                med = int(statistics.median(prices))
                box_pf_data.append({
                    "id": "box_" + pid,
                    "n": v.get("name", ""),
                    "img": f"images/box_{pid}.webp",
                    "med": med,
                    "cur": v.get("current_price", 0),
                })
    except Exception:
        pass
    box_json = json.dumps(box_pf_data, ensure_ascii=False, separators=(',', ':'))

    html = _PORTFOLIO_TEMPLATE.replace("__PF_JSON__", pf_json)
    html = html.replace("__BOX_PF_JSON__", box_json)
    html = html.replace("__FOOTER__", _FOOTER_HTML)
    html = html.replace("__PF_HEADER__", get_header())
    html = html.replace("__PF_NAV__", get_nav(active="portfolio"))
    with open("portfolio.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("portfolio.html 生成完了")


# ===== 共通フッターHTML =====
_FOOTER_HTML = get_footer()
_FOOTER_HTML_REL = get_footer(prefix="../")


_PORTFOLIO_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
<title>持ってるリスト管理 - ポケカるっく</title>
<style>
.main-content{flex:1;min-width:0;max-width:800px;margin:0 auto}
}
.back{display:inline-block;margin-bottom:16px;color:#3b82f6;text-decoration:none;font-size:.85rem;font-weight:600}
.back:hover{text-decoration:underline}
h1{font-size:1.6rem;margin-bottom:6px;color:#1a1a2e;font-weight:900;text-align:center}
.sub{color:#6b7280;font-size:.8rem;text-align:center;margin-bottom:20px}
.summary{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin-bottom:20px}
.sm{background:linear-gradient(135deg,#ecfdf5,#d1fae5);border:2px solid #6ee7b7;border-radius:12px;padding:14px 24px;text-align:center}
.sm .v{font-size:1.4rem;font-weight:800;color:#065f46}
.sm .l{font-size:.7rem;color:#047857;font-weight:600;margin-top:2px}
.actions{display:flex;gap:8px;justify-content:center;margin-bottom:20px}
.act-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:8px 18px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;font-family:inherit}
.act-btn:hover{border-color:#3b82f6;color:#1d4ed8;background:#eff6ff}
.act-btn.danger{border-color:#fca5a5;color:#dc2626}
.act-btn.danger:hover{background:#fef2f2;border-color:#dc2626}
.empty{text-align:center;padding:60px 20px;color:#6b7280;font-size:1rem}
.pf-list{display:flex;flex-direction:column;gap:10px}
.pf-card{display:flex;align-items:center;gap:12px;background:#fff;border:2px solid #e5e7eb;border-radius:12px;padding:12px 16px;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.pf-img{width:60px;height:80px;object-fit:cover;border-radius:6px;flex-shrink:0}
.pf-info{flex:1;min-width:0}
.pf-name{font-size:.85rem;font-weight:600;color:#1a1a2e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pf-name a{color:#1a1a2e;text-decoration:none}
.pf-name a:hover{text-decoration:underline;color:#ea580c}
.pf-prices{font-size:.75rem;color:#4b5563;margin-top:4px}
.pf-prices span{margin-right:12px}
.pf-controls{display:flex;align-items:center;gap:8px;flex-shrink:0}
.pf-qty{display:flex;align-items:center;gap:4px}
.pf-qty button{width:28px;height:28px;border-radius:6px;border:2px solid #d1d5db;background:#fff;cursor:pointer;font-size:.9rem;font-weight:700;color:#374151}
.pf-qty button:hover{background:#ecfdf5;border-color:#10b981}
.pf-qty span{font-size:.95rem;font-weight:700;min-width:24px;text-align:center}
.pf-del{background:none;border:none;color:#9ca3af;cursor:pointer;font-size:1.1rem;padding:4px}
.pf-del:hover{color:#dc2626}
.pf-subtotal{text-align:right;min-width:90px;flex-shrink:0}
.pf-subtotal .sv{font-size:.9rem;font-weight:700;color:#065f46}
.pf-subtotal .sl{font-size:.6rem;color:#6b7280}
@media(max-width:768px){
  h1{font-size:1.2rem}
  .summary{gap:8px}
  .sm{padding:10px 14px}
  .sm .v{font-size:1rem}
  .pf-card{flex-wrap:wrap;gap:8px;padding:10px 12px}
  .pf-img{width:48px;height:64px}
  .pf-name{font-size:.75rem}
  .pf-prices{font-size:.65rem}
  .pf-qty button{width:24px;height:24px;font-size:.8rem}
  .pf-subtotal{min-width:auto}
  .pf-subtotal .sv{font-size:.8rem}
}
</style>
</head>
<body>
__PF_HEADER__
__PF_NAV__
<div class="main-content">
<p class="sub">登録したカードの枚数変更・削除ができます</p>
<div class="summary">
  <div class="sm"><div class="v" id="s-count">0枚</div><div class="l">所持カード</div></div>
  <div class="sm"><div class="v" id="s-a">¥0</div><div class="l">カード美品 合計</div></div>
  <div class="sm"><div class="v" id="s-p">¥0</div><div class="l">PSA10 合計</div></div>
  <div class="sm"><div class="v" id="s-box">¥0</div><div class="l">BOX 合計</div></div>
  <div class="sm" style="background:linear-gradient(135deg,#fef3c7,#fde68a);border-color:#f59e0b"><div class="v" id="s-total" style="color:#92400e">¥0</div><div class="l" style="color:#b45309">総合計</div></div>
</div>
<div class="actions">
  <button class="act-btn danger" onclick="clearAll()">🗑 一括削除</button>
</div>
<div id="list" class="pf-list"></div>
</div><!-- main-content -->
__FOOTER__
<script>
function goBackToList(el){
  try{
    var ref=document.referrer;
    if(ref){
      var u=new URL(ref);
      if(u.origin===location.origin && u.pathname.indexOf('/cards/')!==0){
        history.back();
        return false;
      }
    }
  }catch(e){}
  return true;
}
const CARDS=__PF_JSON__;
const BOXES=__BOX_PF_JSON__;
const cardMap={};CARDS.forEach(c=>{cardMap[c.id]=c});
const boxMap={};BOXES.forEach(b=>{boxMap[b.id]=b});
function loadOwned(){try{return JSON.parse(localStorage.getItem('pokecalook_owned'))||{}}catch(e){return{}}}
function saveOwned(o){localStorage.setItem('pokecalook_owned',JSON.stringify(o))}
function fmt(v){return v?'¥'+v.toLocaleString():'¥0'}
function render(){
  const owned=loadOwned();
  const cardIds=Object.keys(owned).filter(id=>owned[id]>0&&cardMap[id]);
  const boxIds=Object.keys(owned).filter(id=>owned[id]>0&&boxMap[id]);
  // summary
  let aT=0,pT=0,cnt=0,boxCnt=0,boxTotal=0;
  cardIds.forEach(id=>{const c=cardMap[id],q=owned[id];aT+=c.a*q;pT+=c.p*q;cnt+=q});
  boxIds.forEach(id=>{const b=boxMap[id],q=owned[id];boxCnt+=q;boxTotal+=b.cur*q});
  document.getElementById('s-count').textContent=cnt+'枚'+(boxCnt>0?' + BOX'+boxCnt+'個':'');
  document.getElementById('s-a').textContent=fmt(aT);
  document.getElementById('s-p').textContent=fmt(pT);
  document.getElementById('s-box').textContent=fmt(boxTotal);
  document.getElementById('s-total').textContent=fmt(aT+boxTotal);
  const el=document.getElementById('list');
  if(!cardIds.length&&!boxIds.length){el.innerHTML='<div class="empty">まだカードが登録されていません。<br>一覧ページでカードの「持ってる」ボタンから追加できます。</div>';return}
  let html='';
  // BOX一覧
  if(boxIds.length){
    html+='<div style="margin-bottom:12px;font-weight:700;color:#ea580c;font-size:.9rem">📦 未開封BOX</div>';
    html+=boxIds.map(id=>{
      const b=boxMap[id],q=owned[id];
      return`<div class="pf-card" data-id="${id}">
        ${b.img?`<img class="pf-img" src="${b.img}" alt="" style="object-fit:contain">`:''}<div class="pf-info">
          <div class="pf-name"><a href="box/${id.replace('box_','')}.html" style="color:#1a1a2e;text-decoration:none">${esc(b.n)}</a></div>
          <div class="pf-prices"><span>3ヶ月中央値 ${fmt(b.med)}</span><span>最安 ${fmt(b.cur)}</span></div>
        </div>
        <div class="pf-controls">
          <div class="pf-qty"><button onclick="chg('${id}',-1)">−</button><span>${q}</span><button onclick="chg('${id}',1)">+</button></div>
          <button class="pf-del" onclick="del('${id}')" title="削除">✕</button>
        </div>
        <div class="pf-subtotal"><div class="sv">${fmt(b.cur*q)}</div><div class="sl">最安小計</div></div>
      </div>`}).join('');
  }
  // カード一覧
  if(cardIds.length){
    html+='<div style="margin:12px 0;font-weight:700;color:#3b82f6;font-size:.9rem">🃏 シングルカード</div>';
    html+=cardIds.map(id=>{
      const c=cardMap[id],q=owned[id];
      return`<div class="pf-card" data-id="${id}">
        ${c.img?`<img class="pf-img" src="${c.img}" alt="">`:''}<div class="pf-info">
          <div class="pf-name"><a href="cards/${id}.html">${esc(c.n)}</a></div>
          <div class="pf-prices"><span>美品 ${fmt(c.a)}</span><span>PSA10 ${fmt(c.p)}</span><span>倍率 ${c.r.toFixed(1)}x</span></div>
        </div>
        <div class="pf-controls">
          <div class="pf-qty"><button onclick="chg('${id}',-1)">−</button><span>${q}</span><button onclick="chg('${id}',1)">+</button></div>
          <button class="pf-del" onclick="del('${id}')" title="削除">✕</button>
        </div>
        <div class="pf-subtotal"><div class="sv">${fmt(c.a*q)}</div><div class="sl">美品小計</div><div class="sv" style="color:#d97706">${fmt(c.p*q)}</div><div class="sl">PSA10小計</div></div>
      </div>`}).join('');
  }
  el.innerHTML=html;
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function chg(id,delta){
  const o=loadOwned();
  o[id]=Math.max(0,(o[id]||0)+delta);
  if(o[id]<=0)delete o[id];
  saveOwned(o);render();
}
function del(id){
  const o=loadOwned();delete o[id];saveOwned(o);render();
}
function clearAll(){
  if(!confirm('持ってるリストを全て削除しますか？'))return;
  localStorage.removeItem('pokecalook_owned');render();
}
render();
</script>
</body>
</html>"""


_CARD_PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/png" href="../images/logo.png">
<link rel="stylesheet" href="../common.css">
__GTAG_CARD__
__NOINDEX__
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:type" content="website">
<meta property="og:url" content="__URL__">
<meta property="og:image" content="__IMG__">
<meta property="og:site_name" content="ポケカるっく">
<link rel="canonical" href="__URL__">
<script type="application/ld+json">__JSONLD__</script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#fffbf0;color:#1a1a2e;padding:16px}
a{color:#3b82f6;text-decoration:none}a:hover{text-decoration:underline}
.back{display:inline-block;margin-bottom:16px;font-size:.85rem;font-weight:600}
h1{font-size:1.4rem;margin-bottom:4px;color:#1a1a2e;font-weight:800;line-height:1.4}
.meta{color:#6b7280;font-size:.8rem;margin-bottom:16px}
.card-detail{background:#fff;border-radius:14px;border:2px solid #e5e7eb;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.card-top{display:flex;gap:0}
.card-img-wrap{flex-shrink:0;width:320px;text-align:center;padding:16px;background:#f9fafb;border-right:2px solid #e5e7eb}
.card-img{width:100%;border-radius:8px;object-fit:cover;aspect-ratio:3/4}
.card-side{flex:1;padding:20px;min-width:0}
.stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px}
.st{text-align:center;background:#f9fafb;border-radius:10px;padding:10px 6px;border:1px solid #e5e7eb}
.st-l{font-size:.75rem;color:#374151;margin-bottom:3px;font-weight:700}
.st-v{font-size:1.3rem;font-weight:800;color:#111827}
.st-p{color:#d97706}.st-s{font-size:.7rem;color:#4b5563;margin-top:2px;font-weight:600}
.r-hot{color:#059669}.r-warm{color:#d97706}.r-cool{color:#6b7280}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:14px 0}
.info-box{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px}
.info-box h3{font-size:.75rem;color:#374151;margin-bottom:6px;font-weight:700}
.info-row{display:flex;justify-content:space-between;font-size:.8rem;padding:2px 0}
.info-row .lbl{color:#6b7280}.info-row .val{font-weight:700;color:#111827}
.info-period{margin-top:6px;padding-top:6px;border-top:1px dashed #e5e7eb;font-size:.75rem}
.info-period .lbl{color:#6b7280;font-weight:600}
.info-period .val{color:#111827;font-weight:700;text-align:center;margin-top:2px;white-space:nowrap}
.trend-box{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px;text-align:center;margin-bottom:14px}
.trend-box .lbl{font-size:.75rem;color:#374151;font-weight:700}.trend-box .val{font-size:1.1rem;margin-top:4px}
.spark-section{margin:16px 0;padding:0 20px}
.legend{display:flex;gap:14px;justify-content:center;margin-bottom:10px;font-size:.85rem;color:#374151;font-weight:600}
.ldot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:5px;vertical-align:middle}
.sp-btns{display:flex;gap:6px;justify-content:center;margin-bottom:10px}
.sp-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:.8rem;font-weight:600}
.sp-btn:hover{border-color:#3b82f6;color:#1d4ed8}.sp-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.spark-wrap{background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:10px;min-height:140px;position:relative}
.spark-wrap canvas{width:100%;height:140px;display:block}
.trade-period{font-size:.75rem;color:#4b5563;text-align:center;margin:10px 0;padding:6px 10px;background:#f9fafb;border-radius:6px;border:1px solid #e5e7eb}
.spark-tip{display:none;position:absolute;top:2px;left:50%;transform:translateX(-50%);background:rgba(17,24,39,.92);color:#fff;font-size:.72rem;font-weight:700;padding:5px 10px;border-radius:6px;white-space:nowrap;z-index:10;pointer-events:none}
.spark-tip::after{content:'';position:absolute;bottom:-5px;left:50%;transform:translateX(-50%);border-left:5px solid transparent;border-right:5px solid transparent;border-top:5px solid rgba(17,24,39,.92)}
.card-analysis{padding:18px 20px;border-top:2px dashed #e5e7eb;background:#fffef5}
.card-analysis h2{font-size:1rem;font-weight:800;color:#1e40af;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #dbeafe}
.card-analysis h3{font-size:.9rem;font-weight:700;color:#374151;margin:14px 0 6px}
.card-analysis p{font-size:.85rem;color:#374151;margin:6px 0;line-height:1.7}
.card-analysis ul{margin:6px 0 6px 20px;font-size:.85rem;color:#374151}
.card-analysis li{margin:3px 0}
.card-analysis .hl{background:#fef3c7;padding:1px 5px;border-radius:3px;font-weight:600}
.card-analysis .up{color:#0d9488;font-weight:700}
.card-analysis .down{color:#dc2626;font-weight:700}
.card-analysis .flat{color:#6b7280;font-weight:700}
.links{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap;padding:0 20px 20px}
.links a,.links button{font-size:.8rem;padding:8px 16px;border-radius:8px;text-decoration:none;font-weight:600;border:2px solid #d1d5db;cursor:pointer;font-family:inherit}
.links a.lk-snkr{color:#2563eb;border-color:#93c5fd;background:#eff6ff}
.links a.lk-gem{color:#b45309;border-color:#fcd34d;background:#fefce8}
.links button.lk-copy{color:#059669;border-color:#a7f3d0;background:#ecfdf5}
.links button.lk-copy.copied{background:#d1fae5;color:#047857}
.links a.lk-top{color:#374151;border-color:#d1d5db;background:#fff}
.footer{text-align:center;padding:20px;margin-top:20px;font-size:.75rem;color:#6b7280}
.footer a{color:#3b82f6;text-decoration:none;margin:0 8px}
@media(max-width:768px){
  body{padding:8px}h1{font-size:1.1rem}
  .card-top{flex-direction:column}
  .card-img-wrap{width:100%;border-right:none;border-bottom:2px solid #e5e7eb;padding:10px}
  .card-img{max-width:200px;margin:0 auto;display:block}
  .card-side{padding:10px}
  .stats{grid-template-columns:1fr 1fr 1fr;gap:6px}
  .st{padding:6px 3px}
  .st-v{font-size:.95rem}
  .st-l{font-size:.55rem}
  .st-s{font-size:.55rem}
  .trend-box{padding:8px;margin-bottom:10px}
  .trend-box .lbl{font-size:.7rem}
  .trend-box .val{font-size:.95rem}
  .info-grid{grid-template-columns:1fr 1fr;gap:6px}
  .info-box{padding:8px}
  .info-box h3{font-size:.7rem}
  .info-row{font-size:.7rem;padding:1px 0}
  .info-period .lbl{font-size:.65rem}
  .info-period .val{font-size:.7rem}
  .links{padding:0 10px 10px;gap:6px}
  .links a,.links button{font-size:.7rem;padding:6px 10px}
  .spark-section{padding:0 10px;margin:10px 0}
  .sp-btns{gap:4px}
  .sp-btn{padding:3px 8px;font-size:.7rem}
}
.main-content{flex:1;min-width:0;max-width:800px;margin:0 auto}
}
</style>
</head>
<body>
__CARD_BRAND_BAR__
__CARD_HEADER__
__CARD_NAV__
<a class="back" href="../" onclick="return goBackToList(this)">← 一覧に戻る</a>
<div class="main-content">
<h1 style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">__CARD_NAME__ 相場・PSA10価格推移</h1>
<p class="meta">__CARD_NAME__ ｜ 最終更新: __NOW__</p>
<div class="card-detail">
  <div class="card-top">
    <div class="card-img-wrap"><img class="card-img" src="__IMG__" alt="__POKEMON____RARITY__" loading="lazy"></div>
    <div class="card-side">
      <div class="stats">
        <div class="st"><div class="st-l">💎 美品（直近7日 中央値）</div><div class="st-v">__PRICE_A__</div><div class="st-s">本日最安出品 __MIN_A__</div></div>
        <div class="st"><div class="st-l">🏆 PSA10（直近7日 中央値）</div><div class="st-v st-p">__PRICE_P__</div><div class="st-s">本日最安出品 __MIN_P__</div></div>
        <div class="st"><div class="st-l">⚡ 倍率</div><div class="st-v __RATIO_CLASS__">__RATIO__x</div><div class="st-s">差額 __DIFF__</div></div>
        <div class="st"><div class="st-l">📈 週間変動額</div><div class="st-v" style="font-size:.85rem;line-height:1.5">美品 __AT_W__<br>PSA10 __T_W__</div></div>
        <div class="st"><div class="st-l">📊 1ヶ月変動額</div><div class="st-v" style="font-size:.85rem;line-height:1.5">美品 __AT_M__<br>PSA10 __T_M__</div></div>
      </div>
      <div class="info-grid">
        <div class="info-box"><h3>💎 美品 取引データ</h3>
          <div class="info-row"><span class="lbl">取引件数</span><span class="val">__A_COUNT__ 件</span></div>
          <div class="info-period"><div class="lbl">取引期間</div><div class="val">__A_FIRST__ 〜 __A_LAST__</div></div>
        </div>
        <div class="info-box"><h3>🏆 PSA10 取引データ</h3>
          <div class="info-row"><span class="lbl">取引件数</span><span class="val">__P_COUNT__ 件</span></div>
          <div class="info-period"><div class="lbl">取引期間</div><div class="val">__P_FIRST__ 〜 __P_LAST__</div></div>
        </div>
      </div>
    </div>
  </div>
  <div class="spark-section">
    <div class="legend"><span><span class="ldot" style="background:#3b82f6"></span>美品</span><span><span class="ldot" style="background:#ef4444"></span>PSA10</span></div>
    <div class="sp-btns">
      <button class="sp-btn" data-days="30">1ヶ月</button><button class="sp-btn" data-days="90">3ヶ月</button>
      <button class="sp-btn" data-days="180">6ヶ月</button><button class="sp-btn" data-days="365">1年</button>
      <button class="sp-btn active" data-days="0">全期間</button>
    </div>
    <div class="trade-period" id="trade-period"></div>
    <div class="spark-wrap"><div class="spark-tip" id="spark-tip"></div><canvas id="spark"></canvas></div>
  </div>
  <div class="card-analysis">__ANALYSIS__</div>
  <div class="links">
    <a class="lk-snkr" href="__SNKR_URL__" target="_blank">📦 スニダンで見る</a>
    <a class="lk-snkr" href="__MERCARI_URL__" target="_blank" style="color:#dc2626;border-color:#fca5a5;background:#fef2f2">🛒 メルカリで探す</a>
    <a class="lk-snkr" href="__CARDRUSH_URL__" target="_blank" style="color:#059669;border-color:#6ee7b7;background:#ecfdf5">🃏 カードラッシュ</a>
    <button class="lk-copy lk-gem-detail" data-en="__EN_NAME__" data-yr="__YEAR__">🎯 PSA10鑑定率チェック</button>
    <a class="lk-snkr lk-tw-share" href="javascript:void(0)" data-tw="__TWEET_ENC__" style="color:#111827;border-color:#d1d5db;background:#f9fafb">𝕏 共有</a>
    <a class="lk-top" href="../" onclick="return goBackToList(this)">🏠 一覧に戻る</a>
  </div>
</div>
</div><!-- main-content -->
__FOOTER__
<script>
function goBackToList(el){
  try{
    var ref=document.referrer;
    if(ref){
      var u=new URL(ref);
      if(u.origin===location.origin && u.pathname.indexOf('/cards/')!==0){
        history.back();
        return false;
      }
    }
  }catch(e){}
  return true;
}
const C=__CARD_JSON__;
let sparkDays=0;
function filterByDays(data,days){if(!days||days<=0)return data;const cutoff=new Date();cutoff.setDate(cutoff.getDate()-days);const cs=cutoff.toISOString().slice(0,10);return data.filter(p=>p[0]>=cs)}
function drawSpark(){
  const canvas=document.getElementById('spark'),ctx=canvas.getContext('2d');
  const dpr=window.devicePixelRatio||1,rect=canvas.getBoundingClientRect();
  canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;ctx.scale(dpr,dpr);
  const W=rect.width,H=rect.height;
  const aD=filterByDays(C.as,sparkDays),pD=filterByDays(C.ps,sparkDays);
  const allDates=[...aD.map(x=>x[0]),...pD.map(x=>x[0])].sort();
  const tp=document.getElementById('trade-period');
  if(allDates.length){tp.textContent='📅 表示期間: '+allDates[0]+' 〜 '+allDates[allDates.length-1]}
  else{tp.textContent='📅 美品: '+(C.af||'ー')+' 〜 '+(C.al||'ー')+' ｜ PSA10: '+(C.pf||'ー')+' 〜 '+(C.pl||'ー')}
  if(!aD.length&&!pD.length){ctx.fillStyle='#6b7280';ctx.font='14px sans-serif';ctx.textAlign='center';ctx.fillText('この期間のデータなし',W/2,H/2);return}
  const allD=[...aD.map(x=>x[0]),...pD.map(x=>x[0])].sort();
  const minD=allD[0],maxD=allD[allD.length-1];
  const allV=[...aD.map(x=>x[1]),...pD.map(x=>x[1])];
  const minV=Math.min(...allV)*.9,maxV=Math.max(...allV)*1.05;
  const pad={l:50,r:10,t:10,b:18},cw=W-pad.l-pad.r,ch=H-pad.t-pad.b;
  function xFn(ds){const t0=new Date(minD),t1=new Date(maxD),t=new Date(ds);return pad.l+(t1-t0>0?(t-t0)/(t1-t0)*cw:cw/2)}
  function yFn(v){return pad.t+ch-(maxV>minV?(v-minV)/(maxV-minV)*ch:ch/2)}
  function render(hoverX){
    ctx.clearRect(0,0,W,H);
    ctx.strokeStyle='#e2e8f0';ctx.lineWidth=.5;
    for(let i=0;i<=4;i++){const yy=pad.t+ch*i/4;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(W-pad.r,yy);ctx.stroke();ctx.fillStyle='#6b7280';ctx.font='10px sans-serif';ctx.textAlign='right';ctx.fillText('¥'+Math.round(maxV-(maxV-minV)*i/4).toLocaleString(),pad.l-4,yy+3)}
    function line(data,color){if(data.length<2)return;ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.lineJoin='round';data.forEach((p,i)=>{const px=xFn(p[0]),py=yFn(p[1]);i===0?ctx.moveTo(px,py):ctx.lineTo(px,py)});ctx.stroke();ctx.globalAlpha=.08;ctx.lineTo(xFn(data[data.length-1][0]),pad.t+ch);ctx.lineTo(xFn(data[0][0]),pad.t+ch);ctx.closePath();ctx.fillStyle=color;ctx.fill();ctx.globalAlpha=1;const last=data[data.length-1];ctx.beginPath();ctx.arc(xFn(last[0]),yFn(last[1]),3.5,0,Math.PI*2);ctx.fillStyle=color;ctx.fill()}
    line(aD,'#3b82f6');line(pD,'#ef4444');
    if(hoverX!=null&&hoverX>=pad.l&&hoverX<=W-pad.r){
      ctx.beginPath();ctx.strokeStyle='rgba(0,0,0,.2)';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.moveTo(hoverX,pad.t);ctx.lineTo(hoverX,pad.t+ch);ctx.stroke();ctx.setLineDash([]);
      const all=[...aD.map(p=>({d:p[0],v:p[1],c:'#3b82f6',l:'美品'})),...pD.map(p=>({d:p[0],v:p[1],c:'#ef4444',l:'PSA10'}))];
      if(all.length){
        let closest=all[0],minDist=Math.abs(xFn(all[0].d)-hoverX);
        all.forEach(p=>{const dist=Math.abs(xFn(p.d)-hoverX);if(dist<minDist){minDist=dist;closest=p}});
        const aVal=aD.find(p=>p[0]===closest.d),pVal=pD.find(p=>p[0]===closest.d);
        if(aVal){ctx.beginPath();ctx.arc(xFn(aVal[0]),yFn(aVal[1]),5,0,Math.PI*2);ctx.fillStyle='#3b82f6';ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.stroke()}
        if(pVal){ctx.beginPath();ctx.arc(xFn(pVal[0]),yFn(pVal[1]),5,0,Math.PI*2);ctx.fillStyle='#ef4444';ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.stroke()}
        let txt=closest.d;
        if(pVal)txt+='\nPSA10: ¥'+pVal[1].toLocaleString();
        if(aVal)txt+='\n美品: ¥'+aVal[1].toLocaleString();
        canvas._lastTip=txt.replace(/\n/g,' ｜ ');
        const lines=txt.split('\n');
        ctx.font='bold 11px sans-serif';
        const tw=Math.max(...lines.map(l=>ctx.measureText(l).width))+14;
        const th=lines.length*16+10;
        let tx=xFn(closest.d)+10,ty=pad.t+6;
        if(tx+tw>W-pad.r)tx=xFn(closest.d)-tw-10;
        // タッチデバイスではCanvas内ツールチップを非表示（trade-periodに表示するため）
        const isMobile='ontouchstart' in window;
        if(!isMobile){
        ctx.fillStyle='rgba(30,41,59,.9)';ctx.beginPath();
        const br=5;ctx.moveTo(tx+br,ty);ctx.lineTo(tx+tw-br,ty);ctx.quadraticCurveTo(tx+tw,ty,tx+tw,ty+br);ctx.lineTo(tx+tw,ty+th-br);ctx.quadraticCurveTo(tx+tw,ty+th,tx+tw-br,ty+th);ctx.lineTo(tx+br,ty+th);ctx.quadraticCurveTo(tx,ty+th,tx,ty+th-br);ctx.lineTo(tx,ty+br);ctx.quadraticCurveTo(tx,ty,tx+br,ty);ctx.fill();
        ctx.fillStyle='#fff';ctx.textAlign='left';
        lines.forEach((l,i)=>{ctx.fillText(l,tx+7,ty+16+i*16)});
        }
      }
    }
  }
  render(null);
  canvas._sparkRender=render;
  if(!canvas._sparkHover){
    canvas._sparkHover=true;
    canvas._rafPending=false;
    canvas.style.cursor='crosshair';
    canvas.addEventListener('mousemove',function(e){const r=this.getBoundingClientRect();const mx=e.clientX-r.left;if(!this._rafPending){this._rafPending=true;requestAnimationFrame(()=>{this._rafPending=false;this._sparkRender(mx)})}});
    canvas.addEventListener('mouseleave',function(){this._sparkRender(null)});
    canvas.addEventListener('touchstart',function(e){const t=e.touches[0];const r=this.getBoundingClientRect();this._sparkRender(t.clientX-r.left);const tip=document.getElementById('spark-tip');if(tip&&this._lastTip){tip.textContent=this._lastTip;tip.style.display='block';const xPx=t.clientX-r.left;const wrapW=r.width;const tipW=tip.offsetWidth;let left=xPx;if(left-tipW/2<4)left=tipW/2+4;if(left+tipW/2>wrapW-4)left=wrapW-tipW/2-4;tip.style.left=left+'px';tip.style.transform='translateX(-50%)'}});
    canvas.addEventListener('touchmove',function(e){const t=e.touches[0];const r=this.getBoundingClientRect();const mx=t.clientX-r.left;if(!this._rafPending){this._rafPending=true;requestAnimationFrame(()=>{this._rafPending=false;this._sparkRender(mx);const tip=document.getElementById('spark-tip');if(tip&&this._lastTip){tip.textContent=this._lastTip;tip.style.display='block';const wrapW=r.width;const tipW=tip.offsetWidth;let left=mx;if(left-tipW/2<4)left=tipW/2+4;if(left+tipW/2>wrapW-4)left=wrapW-tipW/2-4;tip.style.left=left+'px';tip.style.transform='translateX(-50%)'}})}});
    canvas.addEventListener('touchend',function(){this._sparkRender(null);const tip=document.getElementById('spark-tip');if(tip)setTimeout(()=>{tip.style.display='none'},1500)});
  }
}
document.querySelectorAll('.sp-btn').forEach(btn=>{btn.addEventListener('click',()=>{sparkDays=parseInt(btn.dataset.days);document.querySelectorAll('.sp-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');drawSpark()})});
const copyBtn=document.querySelector('.lk-gem-detail');
if(copyBtn){
  const RARITY_MAP={'SAR':1,'SR':1,'AR':1,'RR':1,'RRR':1,'UR':1,'HR':1,'SSR':1,'S':1,'MA':1,'MUR':1,'CHR':1,'CSR':1,'K':1,'P':1,'PR':1,'C':1,'U':1,'R':1,'TR':1,'FA':1,'GX':1,'EX':1,'V':1,'VMAX':1,'VSTAR':1,'ex':1};
  copyBtn.addEventListener('click',function(){
    const enName=this.dataset.en||'';
    const setM=enName.match(/\[([A-Za-z0-9-]+)\s+(\d+)(?:\/\d+)?\]/);
    const beforeBracket=enName.replace(/\[.*$/,'').trim();
    let pokeName=beforeBracket;
    const words=pokeName.split(/\s+/);
    for(let i=words.length-1;i>=1;i--){
      if(RARITY_MAP[words[i]]){pokeName=words.slice(0,i).join(' ');break;}
    }
    const cardNo=setM?setM[2]:'';
    const text=['Pokemon Japanese',pokeName,cardNo].filter(p=>p).join(' ');
    const ta=document.createElement('textarea');
    ta.value=text;ta.style.cssText='position:fixed;left:-9999px;top:-9999px';
    document.body.appendChild(ta);ta.select();
    document.execCommand('copy');document.body.removeChild(ta);
    if(confirm('検索用テキストをコピーしました！\nOKを押すとGemRateが開きます。\n貼り付けて検索してください。')){
      window.open('https://www.gemrate.com/search','_blank');
    }
  });
}
drawSpark();
</script>
<script>document.addEventListener('click',function(e){var a=e.target.closest('.lk-tw-share');if(a&&a.dataset.tw){window.open('htt'+'ps://'+['x','com'].join('.')+'/inte'+'nt/tw'+'eet?text='+a.dataset.tw,'_blank');e.preventDefault();}});</script>
</body>
</html>"""


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
__GTAG__
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
<title>ポケカるっく - ポケカ PSA10 相場比較</title>
<meta name="description" content="ポケカるっく - ポケモンカードの美品とPSA10の価格差・倍率を毎日更新。相場推移チャート、お気に入り、ポートフォリオ管理機能付き。">
__META_KEYWORDS__
<link rel="canonical" href="https://pokecalook.com/">
<style>
a{color:#3b82f6;text-decoration:none}a:hover{text-decoration:underline}
.desc{color:#374151;font-size:.8rem;margin-top:12px;line-height:1.6;max-width:700px;margin-left:auto;margin-right:auto;background:rgba(255,255,255,.92);padding:12px 16px;border-radius:10px;border:1px solid #e5e7eb}
.desc a{color:#d97706;text-decoration:none;font-weight:600}
.desc a:hover{text-decoration:underline}
.sticky-toolbar{position:sticky;top:0;z-index:100;background:#fffbf0;padding:8px 0 6px;border-bottom:2px solid #e5e7eb;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.toolbar{display:flex;gap:8px;justify-content:center;align-items:center;flex-wrap:wrap;padding:0 8px}
.sort-select{background:#fff;border:2px solid #d1d5db;color:#374151;padding:7px 12px;border-radius:8px;font-size:.85rem;font-weight:600;cursor:pointer;font-family:inherit}
.sort-select:focus{border-color:#3b82f6;outline:none}
.dir-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;transition:all .15s;font-family:inherit}
.dir-btn:hover{border-color:#3b82f6;color:#1d4ed8;background:#eff6ff}
.fav-btn{background:#fff;border:2px solid #fbbf24;color:#92400e;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;transition:all .15s;font-family:inherit}
.fav-btn:hover{border-color:#f59e0b;background:#fefce8}
.fav-btn.active{background:#fbbf24;border-color:#f59e0b;color:#fff}
.filter-toggle-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;transition:all .15s;font-family:inherit}
.filter-toggle-btn:hover{border-color:#3b82f6;color:#1d4ed8;background:#eff6ff}
.filter-toggle-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.toolbar-row2{display:contents}
.fav-star{cursor:pointer;font-size:1.2rem;transition:transform .15s;user-select:none;color:#fbbf24;text-shadow:0 0 1px rgba(0,0,0,.2);display:inline-flex;align-items:center;justify-content:center;min-width:32px;min-height:32px;padding:4px;border-radius:6px}
.fav-star:hover{transform:scale(1.3);background:rgba(251,191,36,.1)}
.fav-star:active{transform:scale(.9)}
.own-btn{cursor:pointer;font-size:.65rem;padding:3px 8px;border-radius:6px;border:1px solid #d1d5db;font-weight:600;font-family:inherit;background:#fff;color:#374151;transition:all .15s}
.own-btn:hover{border-color:#10b981;background:#ecfdf5}
.own-btn.owned{background:#10b981;border-color:#059669;color:#fff}
.own-qty{display:inline-flex;align-items:center;gap:2px;margin-left:2px}
.own-qty button{width:20px;height:20px;border-radius:4px;border:1px solid #d1d5db;background:#fff;cursor:pointer;font-size:.75rem;font-weight:700;color:#374151;display:flex;align-items:center;justify-content:center;padding:0}
.own-qty button:hover{background:#ecfdf5;border-color:#10b981}
.own-qty span{font-size:.7rem;font-weight:700;min-width:16px;text-align:center}
.own-wrap{display:inline-flex;align-items:center;gap:4px;font-size:.65rem;font-weight:600;color:#059669;border:1px solid #a7f3d0;background:#ecfdf5;padding:2px 8px;border-radius:6px}
.portfolio-bar{background:linear-gradient(135deg,#ecfdf5,#d1fae5);border:2px solid #6ee7b7;border-radius:12px;padding:12px 20px;margin-bottom:16px;display:none;max-width:900px;margin-left:auto;margin-right:auto}
.portfolio-bar.show{display:flex;gap:20px;align-items:center;justify-content:center;flex-wrap:wrap}
.pf-item{text-align:center}
.pf-item .pf-v{font-size:1.2rem;font-weight:800;color:#065f46}
.pf-item .pf-l{font-size:.7rem;color:#047857;font-weight:600}
.filter-panel{display:none;max-width:900px;margin:0 auto 12px;padding:12px 16px;background:linear-gradient(135deg,#dbeafe,#eff6ff);border:2px solid #93c5fd;border-radius:10px}
.filter-panel.open{display:block}
.fp-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.fp-row:last-child{margin-bottom:0}
.filter-label{color:#1e40af;font-size:.8rem;margin-right:4px;white-space:nowrap;font-weight:700}
.filter-select{background:#fff;border:2px solid #d1d5db;color:#374151;padding:6px 10px;border-radius:8px;font-size:.85rem;cursor:pointer;font-weight:600;font-family:inherit}
.filter-select:focus{border-color:#3b82f6;outline:none}
.fp-input{background:#fff;border:2px solid #d1d5db;color:#374151;padding:6px 10px;border-radius:8px;font-size:.85rem;font-weight:600;width:100px;font-family:inherit}
.fp-input:focus{border-color:#3b82f6;outline:none}
.fp-check{display:flex;align-items:center;gap:6px;font-size:.85rem;color:#374151;font-weight:600;cursor:pointer}
.fp-check input{width:16px;height:16px;cursor:pointer}
.filter-reset{background:#fff;border:2px solid #ef4444;color:#b91c1c;padding:6px 14px;border-radius:8px;font-size:.8rem;font-weight:700;cursor:pointer;font-family:inherit;margin-left:auto}
.filter-reset:hover{background:#fef2f2}
.sp-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:3px 10px;border-radius:6px;cursor:pointer;font-size:.78rem;margin-left:3px;font-weight:600;font-family:inherit}
.sp-btn:hover{border-color:#3b82f6;color:#1d4ed8}
.sp-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.badge{display:inline-block;padding:3px 10px;border-radius:16px;font-size:.78rem;font-weight:700}
.b-r{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}.b-o{background:#fff7ed;color:#ea580c;border:1px solid #fed7aa}
.b-b{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}.b-t{background:#f0fdfa;color:#0d9488;border:1px solid #99f6e4}
.b-g{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}.b-x{background:#f3f4f6;color:#6b7280;border:1px solid #d1d5db}
.trend-label{font-size:.6rem;color:#4b5563;vertical-align:middle}
.search-box{position:relative;flex:1;min-width:160px;max-width:400px}
.search-box input{width:100%;background:#fff;border:2px solid #d1d5db;color:#111827;padding:8px 60px 8px 12px;border-radius:10px;font-size:.9rem;outline:none;transition:border-color .15s;font-weight:500}
.search-box input:focus{border-color:#3b82f6}
.search-box input::placeholder{color:#6b7280}
.search-count{position:absolute;right:36px;top:50%;transform:translateY(-50%);font-size:.78rem;color:#6b7280;font-weight:600}
.search-clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);background:none;border:none;color:#6b7280;cursor:pointer;font-size:1rem;padding:4px}
.search-clear:hover{color:#111827}
.no-results{text-align:center;padding:40px;color:#6b7280;font-size:.95rem}
.legend{display:flex;gap:14px;justify-content:center;margin-bottom:14px;font-size:.9rem;color:#374151;font-weight:600}
.ldot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:5px;vertical-align:middle}
.pager{display:flex;gap:6px;align-items:center;margin:20px auto;justify-content:center;flex-wrap:wrap}
.pager-sticky{position:sticky;bottom:0;background:rgba(255,251,240,.95);backdrop-filter:blur(6px);padding:10px 8px;z-index:90;border-top:1px solid #e5e7eb;box-shadow:0 -2px 8px rgba(0,0,0,.05);margin:20px -16px 0}
.pg-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:6px 14px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600}
.pg-btn:hover{border-color:#3b82f6;color:#1d4ed8}
.pg-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.pg-btn:disabled{opacity:.3;cursor:default}
.pg-info{color:#6b7280;font-size:.85rem;margin:0 8px;font-weight:600}
.cards{display:flex;flex-direction:column;gap:16px;max-width:1400px;margin:0 auto}
.main-content{flex:1;min-width:0}
}
.card{background:#fff;border-radius:14px;overflow:hidden;border:2px solid #e5e7eb;box-shadow:0 2px 8px rgba(0,0,0,.06);transition:transform .15s,box-shadow .15s,border-color .15s;position:relative}
.card:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(0,0,0,.1);border-color:#fbbf24}
.card-detail-hint{position:absolute;top:8px;right:8px;background:rgba(251,191,36,.95);color:#78350f;font-size:.65rem;font-weight:700;padding:3px 10px;border-radius:12px;opacity:0;transition:opacity .15s;z-index:2;text-decoration:none;pointer-events:auto}
.card-detail-hint:hover{background:rgba(245,158,11,1)}
.card:hover .card-detail-hint{opacity:1}
.card-h{display:flex;align-items:center;gap:10px;padding:12px 16px;background:#fafafa;border-bottom:2px solid #e5e7eb}
.card-rk{font-size:1.1rem;font-weight:800;color:#6b7280;min-width:36px}
.card-nm{flex:1;font-size:.9rem;color:#1a1a2e;font-weight:600}
.card-nm a{color:#1a1a2e;text-decoration:none}
.card-nm a:hover{text-decoration:underline;color:#dc2626}
.card-links{display:flex;gap:6px;margin-top:4px}
.card-links a{font-size:.7rem;padding:3px 8px;border-radius:6px;text-decoration:none;border:1px solid #d1d5db;font-weight:600}
.card-links a.lk-snkr{color:#2563eb;border-color:#93c5fd;background:#eff6ff}
.card-links a.lk-snkr:hover{background:#dbeafe}
.card-links a.lk-mer{color:#dc2626;border-color:#fca5a5;background:#fef2f2}
.card-links a.lk-mer:hover{background:#fee2e2}
.card-links a.lk-cr{color:#059669;border-color:#6ee7b7;background:#ecfdf5}
.card-links a.lk-cr:hover{background:#d1fae5}
.card-links button.lk-gem{color:#b45309;border-color:#fcd34d;background:#fefce8;cursor:pointer;font-family:inherit;font-weight:600;font-size:.7rem;padding:3px 8px;border-radius:6px;border:1px solid #fcd34d}
.card-links button.lk-gem:hover{background:#fef3c7}
.card-links button.lk-gem.copied{background:#d1fae5;color:#047857;border-color:#a7f3d0}
.card-tr{flex-shrink:0}
.card-b{display:flex;gap:0;padding:0}
.card-img-wrap{flex-shrink:0;width:200px;display:flex;align-items:center;justify-content:center;background:#f9fafb;padding:8px;border-right:2px solid #e5e7eb}
.card-img{width:100%;border-radius:6px;object-fit:cover;aspect-ratio:3/4;transition:transform .2s}
.card-img:hover{transform:scale(1.03)}
.card-data{flex:1;min-width:0;padding:16px}
.stats{display:flex;gap:16px;margin-bottom:14px}
.st{flex:1;text-align:center;background:#f9fafb;border-radius:10px;padding:8px 4px;border:1px solid #e5e7eb}
.st-l{font-size:.8rem;color:#374151;letter-spacing:.3px;margin-bottom:4px;font-weight:700;white-space:nowrap}
.st-v{font-size:1.5rem;font-weight:800;color:#111827}
.st-p{color:#d97706}
.st-s{font-size:.8rem;color:#4b5563;margin-top:3px;font-weight:600}
.r-hot{color:#059669}.r-warm{color:#d97706}.r-cool{color:#6b7280}
.spark-wrap{margin:10px 0;background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:8px;min-height:110px;position:relative}
.trade-period{font-size:.7rem;color:#4b5563;text-align:center;margin-bottom:8px;padding:4px 8px;background:#f9fafb;border-radius:6px;border:1px solid #e5e7eb}
.spark-tip{display:none;position:absolute;top:-4px;left:50%;transform:translateX(-50%);background:rgba(17,24,39,.92);color:#fff;font-size:.7rem;font-weight:700;padding:5px 10px;border-radius:6px;white-space:nowrap;z-index:10;pointer-events:none}
.spark-tip::after{content:'';position:absolute;bottom:-5px;left:50%;transform:translateX(-50%);border-left:5px solid transparent;border-right:5px solid transparent;border-top:5px solid rgba(17,24,39,.92)}
.spark-wrap canvas{width:100%;height:110px;display:block}
@media(max-width:768px){
  body{padding:8px}
  .hdr h1{font-size:1.3rem}
  .hdr .sub{font-size:.7rem}
  .card-detail-hint{display:none}
  .desc{font-size:.7rem;padding:10px 12px}
  .sticky-toolbar{padding:6px 0 4px}
  .toolbar{flex-direction:column;align-items:stretch;gap:6px;padding:0 8px}
  .search-box{max-width:100%;min-width:0}
  .search-box input{font-size:.85rem;padding:8px 60px 8px 12px}
  .toolbar-row2{display:flex;gap:6px;flex-wrap:wrap;justify-content:center}
  .sort-select{font-size:.75rem;padding:5px 8px}
  .dir-btn{font-size:.75rem;padding:5px 8px}
  .fav-btn{font-size:.7rem;padding:5px 10px}
  .filter-toggle-btn{font-size:.7rem;padding:5px 10px}
  .cards{gap:10px}
  .card-h{flex-direction:row;flex-wrap:wrap;gap:6px;padding:8px 10px;align-items:center}
  .card-rk{font-size:.8rem;min-width:auto;flex-shrink:0}
  .card-nm{font-size:.8rem;word-break:normal;overflow-wrap:break-word;min-width:0;flex:1 1 100%;order:3;width:100%;line-height:1.3}
  .card-nm a{display:block;white-space:normal;word-break:break-all}
  .card-links{flex-wrap:wrap;gap:4px;margin-top:4px}
  .card-links a,.card-links button{font-size:.6rem;padding:2px 6px}
  .card-tr{margin-left:auto;flex-shrink:0}
  .badge{padding:2px 6px;font-size:.6rem}
  .trend-label{display:none}
  .fav-star{font-size:1.05rem;min-width:32px;min-height:32px;padding:4px;flex-shrink:0}
  .card-b{flex-direction:column;padding:0}
  .card-img-wrap{width:100%;padding:10px;border-right:none;border-bottom:1px solid #e2e8f0;display:flex;justify-content:center;flex-shrink:0}
  .card-img{width:auto;max-width:100%;height:140px;max-height:140px;margin:0 auto;display:block;object-fit:contain}
  .card-data{padding:8px 10px;min-width:0;flex:1}
  .stats{gap:4px;display:grid;grid-template-columns:1fr 1fr 1fr;flex-wrap:unset}
  .st{flex:none;min-width:0;padding:5px 2px}
  .st-v{font-size:.85rem}
  .st-l{font-size:.5rem}
  .st-s{font-size:.5rem}
  .trade-period{font-size:.55rem}
  .spark-wrap{min-height:80px}
  .spark-wrap canvas{height:80px}
  .filter-panel{padding:8px 10px}
  .fp-row{gap:6px}
  .filter-label{font-size:.7rem}
  .fp-input{width:70px;font-size:.75rem;padding:4px 6px}
  .sp-btn{font-size:.65rem;padding:3px 8px}
  .filter-select{font-size:.75rem}
  .pager{flex-wrap:wrap;gap:4px}
  .pg-btn{padding:4px 8px;font-size:.7rem}
  .pg-info{font-size:.65rem}
  .own-btn{font-size:.6rem;padding:2px 6px}
  .own-qty button{width:18px;height:18px;font-size:.65rem}
  .own-qty span{font-size:.6rem}
  .portfolio-bar.show{flex-direction:row;gap:10px;padding:8px 12px}
  .pf-item .pf-v{font-size:.9rem}
  .pf-item .pf-l{font-size:.6rem}
}
@keyframes hint-blink{0%,100%{box-shadow:0 0 0 0 rgba(59,130,246,0)}50%{box-shadow:0 0 14px 8px rgba(59,130,246,.6),0 0 4px 2px rgba(59,130,246,.8)}}
.hint-blink{animation:hint-blink 2s ease-in-out infinite}
@keyframes star-glow{0%,100%{transform:scale(1)}50%{transform:scale(1.5)}}
.star-glow{animation:star-glow 1.5s ease-in-out infinite}
</style>
</head>
<body>
__HEADER__
__NAV__
<p style="text-align:center;font-size:.75rem;color:#9ca3af;margin:8px 0 4px">最終更新: __NOW__ JST</p>
<div class="sticky-toolbar">
<div class="toolbar">
  <div class="search-box">
    <input type="text" id="search" placeholder="🔍 ポケモン名・パック名等で検索..." autocomplete="off">
    <span id="search-count" class="search-count"></span>
    <button id="search-clear" class="search-clear" style="display:none">✕</button>
  </div>
  <div class="toolbar-row2">
  <select id="sort-select" class="sort-select">
    <option value="sc" selected>取引件数</option>
    <option value="r">倍率（PSA10÷美品）</option>
    <option value="a">美品価格</option>
    <option value="p">PSA10価格</option>
    <option value="t">PSA10 週間変動額</option>
    <option value="at">美品 週間変動額</option>
    <option value="pmt">PSA10 1ヶ月変動額</option>
    <option value="mt">美品 1ヶ月変動額</option>
    <option value="d">差額（PSA10−美品）</option>
  </select>
  <button class="dir-btn" id="dir-btn" title="昇順/降順切り替え">▼ 降順</button>
  <button class="fav-btn" id="fav-filter" title="お気に入りのカードだけ表示">☆ お気に入り</button>
  <button class="filter-toggle-btn" id="filter-toggle">フィルタ</button>
  </div>
</div>
<div class="filter-panel" id="filter-panel">
  <div class="fp-row">
    <span class="filter-label">取引件数</span>
    <select id="min-trades" class="filter-select">
      <option value="0" selected>全件</option>
      <option value="10">10件以上</option>
      <option value="20">20件以上</option>
      <option value="30">30件以上</option>
      <option value="40">40件以上</option>
      <option value="50">50件以上</option>
      <option value="100">100件以上</option>
      <option value="200">200件以上</option>
    </select>
  </div>
  <div class="fp-row">
    <span class="filter-label">期間</span>
    <button class="sp-btn" data-days="7">1週間</button>
    <button class="sp-btn" data-days="14">2週間</button>
    <button class="sp-btn" data-days="21">3週間</button>
    <button class="sp-btn" data-days="30">1ヶ月</button>
    <button class="sp-btn" data-days="60">2ヶ月</button>
    <button class="sp-btn" data-days="90">3ヶ月</button>
    <button class="sp-btn" data-days="180">6ヶ月</button>
    <button class="sp-btn" data-days="365">1年</button>
    <button class="sp-btn active" data-days="0">全期間</button>
  </div>
  <div class="fp-row">
    <span class="filter-label">美品価格帯</span>
    <input type="number" id="price-a-min" class="fp-input" placeholder="最小">
    <span style="color:#6b7280;font-size:.8rem">〜</span>
    <input type="number" id="price-a-max" class="fp-input" placeholder="最大">
    <span class="filter-label" style="margin-left:12px">PSA10価格帯</span>
    <input type="number" id="price-p-min" class="fp-input" placeholder="最小">
    <span style="color:#6b7280;font-size:.8rem">〜</span>
    <input type="number" id="price-p-max" class="fp-input" placeholder="最大">
  </div>
  <div class="fp-row">
    <label class="fp-check"><input type="checkbox" id="exclude-no-psa">PSA10取引なし除外</label>
    <button class="filter-reset" onclick="resetFilter()">リセット</button>
  </div>
</div>
<div class="portfolio-bar" id="portfolio-bar">
  <div class="pf-item"><div class="pf-v" id="pf-count">0</div><div class="pf-l">所持カード</div></div>
  <div class="pf-item"><div class="pf-v" id="pf-a-total">¥0</div><div class="pf-l">総合計</div></div>
  <div class="pf-item"><div class="pf-v" id="pf-p-total">¥0</div><div class="pf-l">PSA10 合計</div></div>
  <div class="pf-item"><div class="pf-v" id="pf-diff">¥0</div><div class="pf-l">PSA10化 利益</div></div>
  <div class="pf-item"><a href="portfolio.html" style="color:#065f46;font-weight:700;font-size:.8rem;text-decoration:none;border:2px solid #6ee7b7;padding:6px 14px;border-radius:8px;background:#fff">📋 リスト管理</a></div>
  <div class="pf-item"><button onclick="if(confirm('持ってるカードを全て削除しますか？')){localStorage.removeItem('pokecalook_owned');location.reload()}" style="color:#dc2626;font-weight:700;font-size:.8rem;border:2px solid #fca5a5;padding:6px 14px;border-radius:8px;background:#fff;cursor:pointer">🗑 一括削除</button></div>
</div>
</div>
<div class="pager" id="pager-top"></div>
<div class="main-content">
<div class="cards" id="cards"></div>
<div class="pager pager-sticky" id="pager-bottom"></div>
</div>
</div>

<script>
const ALL=__CARDS_JSON__;
const BOX_SUMMARY=__BOX_SUMMARY_JSON__;
const PER=30;
let filtered=[...ALL];
let sorted=[...ALL];
let curPage=1;
let curKey='sc',curDir='desc';
let searchQuery='';
let minTrades=0;
let favOnly=false;

// お気に入り管理（localStorage）
function loadFavs(){try{return new Set(JSON.parse(localStorage.getItem('pokecalook_favs'))||[])}catch(e){return new Set()}}
function saveFavs(s){localStorage.setItem('pokecalook_favs',JSON.stringify([...s]))}
let favSet=loadFavs();
function isFav(id){return favSet.has(id)}
function toggleFav(id){if(favSet.has(id)){favSet.delete(id)}else{favSet.add(id)}saveFavs(favSet)}

// ポートフォリオ管理（localStorage）— {id: 枚数} のMap
function loadOwned(){try{return new Map(Object.entries(JSON.parse(localStorage.getItem('pokecalook_owned'))||{}))}catch(e){return new Map()}}
function saveOwned(m){const o={};m.forEach((v,k)=>{o[k]=v});localStorage.setItem('pokecalook_owned',JSON.stringify(o))}
let ownedMap=loadOwned();
function getOwnedQty(id){return ownedMap.get(id)||0}
function setOwnedQty(id,qty){if(qty<=0){ownedMap.delete(id)}else{ownedMap.set(id,qty)}saveOwned(ownedMap);updatePortfolio()}
function updatePortfolio(){
  const bar=document.getElementById('portfolio-bar');
  if(!ownedMap.size){bar.classList.remove('show');return}
  bar.classList.add('show');
  let aTotal=0,pTotal=0,cnt=0,boxCnt=0,boxTotal=0;
  ALL.forEach(c=>{const q=getOwnedQty(c.id);if(q>0){aTotal+=c.a*q;pTotal+=c.p*q;cnt+=q}});
  // BOXも集計（box_プレフィックス付きキー）
  const boxMap={};BOX_SUMMARY.forEach(b=>{boxMap[b.id]=b});
  ownedMap.forEach((v,k)=>{if(k.startsWith('box_')&&v>0){boxCnt+=v;const bid=k.replace('box_','');if(boxMap[bid])boxTotal+=v*(boxMap[bid].cur||boxMap[bid].med)}});
  const grandTotal=aTotal+boxTotal;
  const label=cnt+'枚'+(boxCnt>0?' + BOX'+boxCnt+'個':'');
  document.getElementById('pf-count').textContent=label;
  document.getElementById('pf-a-total').textContent='¥'+grandTotal.toLocaleString();
  document.getElementById('pf-p-total').textContent='¥'+pTotal.toLocaleString();
  document.getElementById('pf-diff').textContent='¥'+(pTotal-aTotal).toLocaleString();
}

function tBadge(t){
  if(t==null)return'<span class="badge b-x">データなし</span> <span class="trend-label">PSA10 週間変動額</span>';
  const s=t>=0?'+':'';const v='¥'+Math.abs(t).toLocaleString();
  if(t>5000)return`<span class="badge b-r">🔥 ${s}${v}</span> <span class="trend-label">PSA10 週間変動額</span>`;
  if(t>1000)return`<span class="badge b-o">📈 ${s}${v}</span> <span class="trend-label">PSA10 週間変動額</span>`;
  if(t>-1000)return`<span class="badge b-b">→ ${s}${v}</span> <span class="trend-label">PSA10 週間変動額</span>`;
  if(t>-5000)return`<span class="badge b-t">📉 ${s}${v}</span> <span class="trend-label">PSA10 週間変動額</span>`;
  return`<span class="badge b-g">⬇ ${s}${v}</span> <span class="trend-label">PSA10 週間変動額</span>`;
}
function fmtDelta(v){
  if(v==null)return'<span style="color:#6b7280">ー</span>';
  const s=v>0?'+':v<0?'-':'±';const col=v>0?'#0d9488':v<0?'#dc2626':'#2563eb';
  return`<span style="color:${col};font-weight:700">${s}¥${Math.abs(v).toLocaleString()}</span>`;
}
function fmt(v){return v==null?'-':'¥'+v.toLocaleString()}
function escH(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

function renderPage(){
  const start=(curPage-1)*PER,end=Math.min(start+PER,sorted.length);
  const page=sorted.slice(start,end);
  const el=document.getElementById('cards');
  if(!sorted.length){
    el.innerHTML='<div class="no-results">該当するカードが見つかりません</div>';
    renderPagers();
    return;
  }
  el.innerHTML=page.map((c,i)=>{
    const rank=start+i+1;
    const rc=c.r>=4?'r-hot':c.r>=3?'r-warm':'r-cool';
    const cardHtml=`<div class="card" data-pid="${c.id}">
      <a href="cards/${c.id}.html" class="card-detail-hint">📄 詳細を見る →</a>
      <div class="card-h">
        <span class="fav-star" data-fid="${c.id}" onclick="onFavClick(this)" title="お気に入り">${isFav(c.id)?'★':'☆'}</span>
        <div class="card-rk">#${rank}</div>
        <div class="card-nm">
          <a href="cards/${c.id}.html" style="color:#1a1a2e;text-decoration:none">${escH(c.n)}</a>
          <div class="card-links">
            <a class="lk-snkr" href="${c.u}" target="_blank">📦 スニダン</a>
            ${c.sn?`<a class="lk-mer" href="https://jp.mercari.com/search?keyword=${encodeURIComponent(c.sn)}&category_id=1289" target="_blank">🛒 メルカリ</a>`:''}
            ${c.sn?`<a class="lk-cr" href="https://www.cardrush-pokemon.jp/product-list?keyword=${encodeURIComponent(c.cn?c.sn+' '+c.cn:c.sn)}" target="_blank">🃏 カードラッシュ</a>`:''}
            ${c.en?`<button class="lk-gem" data-en="${escH(c.en)}" data-yr="${c.yr||''}">🎯 PSA10鑑定率チェック</button>`:''}
            <a class="lk-snkr lk-tw-share" href="javascript:void(0)" data-tw="${encodeURIComponent(c.n+'\n'+(c.a?'美品: ¥'+c.a.toLocaleString():'')+(c.p?' / PSA10: ¥'+c.p.toLocaleString():'')+'\nhttps://pokecalook.com/cards/'+c.id+'.html\n#ポケカるっく')}" style="color:#111827;border-color:#d1d5db;background:#f9fafb;white-space:nowrap;flex-shrink:0">𝕏 共有</a>
            <span class="own-wrap">📥持ってる <span class="own-qty" data-oid="${c.id}"><button onclick="onOwnDelta(this,-1)">−</button><span>${getOwnedQty(c.id)}</span><button onclick="onOwnDelta(this,1)">+</button></span></span>
          </div>
        </div>
        <div class="card-tr"></div>
      </div>
      <div class="card-b">
        ${c.img?`<div class="card-img-wrap"><a href="cards/${c.id}.html"><img class="card-img" src="${c.img}" alt="" loading="lazy"></a></div>`:''}
        <div class="card-data">
        <div class="stats">
          <div class="st"><div class="st-l">💎 美品（直近7日 中央値）</div><div class="st-v">${fmt(c.a)}</div><div class="st-s">本日最安出品 ${c.mla?fmt(c.mla):'ー'}</div></div>
          <div class="st"><div class="st-l">🏆 PSA10（直近7日 中央値）</div><div class="st-v st-p">${fmt(c.p)}</div><div class="st-s">本日最安出品 ${c.mlp?fmt(c.mlp):'ー'}</div></div>
          <div class="st"><div class="st-l">⚡ 倍率</div><div class="st-v ${rc}">${c.r.toFixed(1)}x</div><div class="st-s">PSA10との差額 ${fmt(c.d)}</div></div>
          <div class="st"><div class="st-l">📊 取引件数</div><div class="st-v" style="color:#a78bfa">${c.ac+c.pc}</div><div class="st-s">美品${c.ac} PSA10 ${c.pc}</div></div>
          <div class="st"><div class="st-l">📈 週間変動額</div><div class="st-v" style="font-size:.85rem;line-height:1.5">美品 ${fmtDelta(c.at)}<br>PSA10 ${fmtDelta(c.t)}</div></div>
          <div class="st"><div class="st-l">📊 1ヶ月変動額</div><div class="st-v" style="font-size:.85rem;line-height:1.5">美品 ${fmtDelta(c.mt)}<br>PSA10 ${fmtDelta(c.pmt)}</div></div>
        </div>
        <div class="trade-period">📅 美品: ${c.af||'ー'} 〜 ${c.al||'ー'} ｜ PSA10: ${c.pf||'ー'} 〜 ${c.pl||'ー'}</div>
        <div class="spark-wrap"><div class="spark-tip"></div><canvas data-spark="${c.id}"></canvas></div>
        </div>
      </div>
    </div>`;
    return cardHtml;
  }).join('');
  renderPagers();
  setupObserver();
  // GemRateボタンのイベント登録
  document.querySelectorAll('.lk-gem[data-en]').forEach(btn=>{
    btn.addEventListener('click',function(e){
      copyGemRate(this,this.dataset.en,this.dataset.yr||'');
    });
  });
  window.scrollTo({top:0,behavior:'smooth'});
  applyStarGlow();
}

function onFavClick(el){
  const id=el.dataset.fid;
  toggleFav(id);
  el.textContent=isFav(id)?'★':'☆';
  if(favOnly)applySearch();
  updateFavBtn();
}
function updateFavBtn(){
  const btn=document.getElementById('fav-filter');
  const cnt=ALL.filter(c=>isFav(c.id)).length;
  const label=favOnly?'★ お気に入り':'☆ お気に入り';
  btn.textContent=cnt>0?label+' ('+cnt+')':label;
  if(favOnly)btn.classList.add('active');else btn.classList.remove('active');
}

function onOwnDelta(btn,delta){
  const wrap=btn.closest('.own-qty');
  const id=wrap.dataset.oid;
  const qty=Math.max(0,getOwnedQty(id)+delta);
  setOwnedQty(id,qty);
  wrap.querySelector('span').textContent=qty;
}

function renderPagers(){
  const total=Math.ceil(sorted.length/PER);
  function pg(containerId){
    const el=document.getElementById(containerId);
    if(total<=1){el.innerHTML='';return}
    let h=`<button class="pg-btn" onclick="goPage(1)" ${curPage===1?'disabled':''}>«</button>`;
    h+=`<button class="pg-btn" onclick="goPage(${curPage-1})" ${curPage===1?'disabled':''}>‹</button>`;
    const range=2;
    let s=Math.max(1,curPage-range),e=Math.min(total,curPage+range);
    if(s>1)h+=`<span class="pg-info">...</span>`;
    for(let p=s;p<=e;p++){
      h+=`<button class="pg-btn ${p===curPage?'active':''}" onclick="goPage(${p})">${p}</button>`;
    }
    if(e<total)h+=`<span class="pg-info">...</span>`;
    h+=`<button class="pg-btn" onclick="goPage(${curPage+1})" ${curPage===total?'disabled':''}>›</button>`;
    h+=`<button class="pg-btn" onclick="goPage(${total})" ${curPage===total?'disabled':''}>»</button>`;
    h+=`<span class="pg-info">${curPage}/${total} (${sorted.length}件)</span>`;
    el.innerHTML=h;
  }
  pg('pager-top');pg('pager-bottom');
}
function goPage(p){
  const total=Math.ceil(sorted.length/PER);
  curPage=Math.max(1,Math.min(p,total));
  renderPage();
  updateURL();
}

// Sparkline lazy draw via IntersectionObserver
let observer;
function setupObserver(){
  if(observer)observer.disconnect();
  observer=new IntersectionObserver((entries)=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        const cv=e.target;
        const pid=cv.dataset.spark;
        if(pid&&!cv.dataset.drawn){
          drawSpark(cv,pid);
          cv.dataset.drawn='1';
        }
        observer.unobserve(cv);
      }
    });
  },{rootMargin:'200px'});
  document.querySelectorAll('canvas[data-spark]').forEach(cv=>observer.observe(cv));
}

const sparkCache={};
ALL.forEach(c=>{sparkCache[c.id]={a:c.as,p:c.ps}});
let sparkDays=0;

function filterByDays(data,days){
  if(!days||days<=0)return data;
  const cutoff=new Date();cutoff.setDate(cutoff.getDate()-days);
  const cs=cutoff.toISOString().slice(0,10);
  return data.filter(p=>p[0]>=cs);
}

function drawSpark(canvas,pid){
  const d=sparkCache[pid];
  if(!d)return;
  const ctx=canvas.getContext('2d');
  const dpr=window.devicePixelRatio||1;
  const rect=canvas.getBoundingClientRect();
  canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;
  ctx.scale(dpr,dpr);
  const W=rect.width,H=rect.height;
  const aD=filterByDays(d.a,sparkDays),pD=filterByDays(d.p,sparkDays);
  if(!aD.length&&!pD.length)return;
  const allD=[...aD.map(x=>x[0]),...pD.map(x=>x[0])].sort();
  const minD=allD[0],maxD=allD[allD.length-1];
  const allV=[...aD.map(x=>x[1]),...pD.map(x=>x[1])];
  const minV=Math.min(...allV)*.9,maxV=Math.max(...allV)*1.05;
  const pad={l:45,r:8,t:8,b:16};
  const cw=W-pad.l-pad.r,ch=H-pad.t-pad.b;
  function xFn(ds){const t0=new Date(minD),t1=new Date(maxD),t=new Date(ds);return pad.l+(t1-t0>0?(t-t0)/(t1-t0)*cw:cw/2)}
  function yFn(v){return pad.t+ch-(maxV>minV?(v-minV)/(maxV-minV)*ch:ch/2)}
  canvas._sparkData={aD,pD,xFn,yFn,pad,W,H,cw,ch,minD,maxD,minV,maxV,dpr};
  function render(hoverX){
    ctx.clearRect(0,0,W,H);
    ctx.strokeStyle='#e2e8f0';ctx.lineWidth=.5;
    for(let i=0;i<=3;i++){
      const yy=pad.t+ch*i/3;
      ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(W-pad.r,yy);ctx.stroke();
      ctx.fillStyle='#6b7280';ctx.font='9px sans-serif';ctx.textAlign='right';
      ctx.fillText('¥'+Math.round(maxV-(maxV-minV)*i/3).toLocaleString(),pad.l-4,yy+3);
    }
    function line(data,color){
      if(data.length<2)return;
      ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=1.8;ctx.lineJoin='round';
      data.forEach((p,i)=>{const px=xFn(p[0]),py=yFn(p[1]);i===0?ctx.moveTo(px,py):ctx.lineTo(px,py)});
      ctx.stroke();
      ctx.globalAlpha=.07;ctx.lineTo(xFn(data[data.length-1][0]),pad.t+ch);ctx.lineTo(xFn(data[0][0]),pad.t+ch);ctx.closePath();ctx.fillStyle=color;ctx.fill();ctx.globalAlpha=1;
      const last=data[data.length-1];
      ctx.beginPath();ctx.arc(xFn(last[0]),yFn(last[1]),3,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();
    }
    line(aD,'#3b82f6');line(pD,'#ef4444');
    if(hoverX!=null&&hoverX>=pad.l&&hoverX<=W-pad.r){
      ctx.beginPath();ctx.strokeStyle='rgba(0,0,0,.2)';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.moveTo(hoverX,pad.t);ctx.lineTo(hoverX,pad.t+ch);ctx.stroke();ctx.setLineDash([]);
      const all=[...aD.map(p=>({d:p[0],v:p[1],c:'#3b82f6',l:'美品'})),...pD.map(p=>({d:p[0],v:p[1],c:'#ef4444',l:'PSA10'}))];
      if(all.length){
        let closest=all[0],minDist=Math.abs(xFn(all[0].d)-hoverX);
        all.forEach(p=>{const dist=Math.abs(xFn(p.d)-hoverX);if(dist<minDist){minDist=dist;closest=p}});
        const cx=xFn(closest.d),cy=yFn(closest.v);
        const aVal=aD.find(p=>p[0]===closest.d);
        const pVal=pD.find(p=>p[0]===closest.d);
        if(aVal){ctx.beginPath();ctx.arc(xFn(aVal[0]),yFn(aVal[1]),4,0,Math.PI*2);ctx.fillStyle='#3b82f6';ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.stroke()}
        if(pVal){ctx.beginPath();ctx.arc(xFn(pVal[0]),yFn(pVal[1]),4,0,Math.PI*2);ctx.fillStyle='#ef4444';ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.stroke()}
        let txt=closest.d;
        if(pVal)txt+='\nPSA10: ¥'+pVal[1].toLocaleString();
        if(aVal)txt+='\n美品: ¥'+aVal[1].toLocaleString();
        canvas._lastTip=txt.replace(/\n/g,' ｜ ');
        const lines=txt.split('\n');
        ctx.font='bold 10px sans-serif';
        const tw=Math.max(...lines.map(l=>ctx.measureText(l).width))+12;
        const th=lines.length*14+8;
        let tx=cx+8,ty=pad.t+4;
        if(tx+tw>W-pad.r)tx=cx-tw-8;
        // スマホではCanvas内ツールチップを非表示（trade-periodに表示するため）
        const isMobile='ontouchstart' in window;
        if(!isMobile){
        ctx.fillStyle='rgba(30,41,59,.9)';ctx.beginPath();
        const br=4;ctx.moveTo(tx+br,ty);ctx.lineTo(tx+tw-br,ty);ctx.quadraticCurveTo(tx+tw,ty,tx+tw,ty+br);ctx.lineTo(tx+tw,ty+th-br);ctx.quadraticCurveTo(tx+tw,ty+th,tx+tw-br,ty+th);ctx.lineTo(tx+br,ty+th);ctx.quadraticCurveTo(tx,ty+th,tx,ty+th-br);ctx.lineTo(tx,ty+br);ctx.quadraticCurveTo(tx,ty,tx+br,ty);ctx.fill();
        ctx.fillStyle='#fff';ctx.textAlign='left';
        lines.forEach((l,i)=>{ctx.fillText(l,tx+6,ty+14+i*14)});
        }
      }
    }
  }
  render(null);
  canvas._sparkRender=render;
  if(!canvas._sparkHover){
    canvas._sparkHover=true;
    canvas._rafPending=false;
    canvas.style.cursor='crosshair';
    canvas.addEventListener('mousemove',function(e){
      const r=this.getBoundingClientRect();
      const mx=e.clientX-r.left;
      if(!this._rafPending){this._rafPending=true;requestAnimationFrame(()=>{this._rafPending=false;if(this._sparkRender)this._sparkRender(mx)})}
    });
    canvas.addEventListener('mouseleave',function(){
      if(this._sparkRender)this._sparkRender(null);
    });
    canvas.addEventListener('touchstart',function(e){
      const t=e.touches[0];const r=this.getBoundingClientRect();
      if(this._sparkRender)this._sparkRender(t.clientX-r.left);
      const tip=this.closest('.spark-wrap')?.querySelector('.spark-tip');
      if(tip&&this._lastTip){tip.textContent=this._lastTip;tip.style.display='block';const xPx=t.clientX-r.left;const wrapW=r.width;const tipW=tip.offsetWidth;let left=xPx;if(left-tipW/2<4)left=tipW/2+4;if(left+tipW/2>wrapW-4)left=wrapW-tipW/2-4;tip.style.left=left+'px';tip.style.transform='translateX(-50%)'}
    });
    canvas.addEventListener('touchmove',function(e){
      const t=e.touches[0];const r=this.getBoundingClientRect();const mx=t.clientX-r.left;
      if(!this._rafPending){this._rafPending=true;requestAnimationFrame(()=>{this._rafPending=false;if(this._sparkRender)this._sparkRender(mx);const tip=this.closest('.spark-wrap')?.querySelector('.spark-tip');if(tip&&this._lastTip){tip.textContent=this._lastTip;tip.style.display='block';const wrapW=r.width;const tipW=tip.offsetWidth;let left=mx;if(left-tipW/2<4)left=tipW/2+4;if(left+tipW/2>wrapW-4)left=wrapW-tipW/2-4;tip.style.left=left+'px';tip.style.transform='translateX(-50%)'}})}
    });
    canvas.addEventListener('touchend',function(){
      if(this._sparkRender)this._sparkRender(null);
      const tip=this.closest('.spark-wrap')?.querySelector('.spark-tip');
      if(tip)setTimeout(()=>{tip.style.display='none'},1500);
    });
  }
}

// Sort
function applySort(){
  sorted=[...filtered].sort((a,b)=>{
    let va=a[curKey],vb=b[curKey];
    if(curKey==='al'){
      // 最終取引日: 文字列比較
      va=va||'';vb=vb||'';
      if(curDir==='desc')return vb<va?-1:vb>va?1:0;
      return va<vb?-1:va>vb?1:0;
    }
    if(va==null)va=-9999;if(vb==null)vb=-9999;
    return curDir==='desc'?vb-va:va-vb;
  });
}

// Sort dropdown
const sortSelect=document.getElementById('sort-select');
const dirBtn=document.getElementById('dir-btn');

sortSelect.addEventListener('change',function(){
  curKey=this.value;
  applySort();
  curPage=1;
  renderPage();
  updateURL();
});

dirBtn.addEventListener('click',function(){
  curDir=curDir==='desc'?'asc':'desc';
  this.textContent=curDir==='desc'?'▼ 降順':'▲ 昇順';
  applySort();
  curPage=1;
  renderPage();
  updateURL();
});

// Search
const searchInput=document.getElementById('search');
const searchCount=document.getElementById('search-count');
const searchClear=document.getElementById('search-clear');
let searchTimer=null;

function applySearch(keepPage){
  const toKatakana=s=>s.replace(/[\u3041-\u3096]/g,c=>String.fromCharCode(c.charCodeAt(0)+0x60));
  const q=toKatakana(searchQuery.toLowerCase().trim());
  if(!q){
    filtered=[...ALL];
  }else{
    const terms=q.split(/\s+/).filter(t=>t);
    filtered=ALL.filter(c=>{
      const name=toKatakana(c.n.toLowerCase());
      return terms.every(t=>name.includes(t));
    });
  }
  // お気に入りフィルタ
  if(favOnly){
    filtered=filtered.filter(c=>favSet.has(c.id));
  }
  // 取引件数フィルタ
  if(minTrades>0){
    filtered=filtered.filter(c=>{
      const d=sparkCache[c.id];
      if(!d)return false;
      const aInPeriod=filterByDays(d.a,sparkDays).length;
      const pInPeriod=filterByDays(d.p,sparkDays).length;
      return (aInPeriod+pInPeriod)>=minTrades;
    });
  }
  // 価格帯フィルタ
  const aMin=parseInt(document.getElementById('price-a-min').value)||0;
  const aMax=parseInt(document.getElementById('price-a-max').value)||0;
  const pMin=parseInt(document.getElementById('price-p-min').value)||0;
  const pMax=parseInt(document.getElementById('price-p-max').value)||0;
  if(aMin>0)filtered=filtered.filter(c=>c.a>=aMin);
  if(aMax>0)filtered=filtered.filter(c=>c.a<=aMax);
  if(pMin>0)filtered=filtered.filter(c=>c.p>=pMin);
  if(pMax>0)filtered=filtered.filter(c=>c.p<=pMax);
  // PSA10取引なし除外
  if(document.getElementById('exclude-no-psa').checked){
    filtered=filtered.filter(c=>c.pc>0);
  }
  if(q||favOnly){
    searchCount.textContent=`${filtered.length}件`;
    searchClear.style.display=q?'block':'none';
  }else{
    const hasFilter=minTrades>0||aMin>0||aMax>0||pMin>0||pMax>0||document.getElementById('exclude-no-psa').checked;
    searchCount.textContent=hasFilter?`${filtered.length}件`:'';
    searchClear.style.display='none';
  }
  applySort();
  if(!keepPage)curPage=1;
  renderPage();
  updateURL();
}

searchInput.addEventListener('input',()=>{
  searchQuery=searchInput.value;
  clearTimeout(searchTimer);
  searchTimer=setTimeout(applySearch,150);
});

searchClear.addEventListener('click',()=>{
  searchInput.value='';
  searchQuery='';
  applySearch();
  searchInput.focus();
});

// Ctrl+F でフォーカス
document.addEventListener('keydown',(e)=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='f'){
    e.preventDefault();
    searchInput.focus();
    searchInput.select();
  }
});

// お気に入りフィルタ
document.getElementById('fav-filter').addEventListener('click',()=>{
  favOnly=!favOnly;
  updateFavBtn();
  applySearch();
});

// Trades filter
document.getElementById('min-trades').addEventListener('change',function(){
  minTrades=parseInt(this.value);
  applySearch();
});

// 価格帯フィルタ
['price-a-min','price-a-max','price-p-min','price-p-max'].forEach(id=>{
  document.getElementById(id).addEventListener('change',applySearch);
});
document.getElementById('exclude-no-psa').addEventListener('change',applySearch);

// Filter panel toggle
document.getElementById('filter-toggle').addEventListener('click',function(){
  const panel=document.getElementById('filter-panel');
  panel.classList.toggle('open');
  this.classList.toggle('active');
});

// Sparkline period toggle
document.querySelectorAll('.sp-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    sparkDays=parseInt(btn.dataset.days);
    document.querySelectorAll('.sp-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    applySearch();
    document.querySelectorAll('canvas[data-spark]').forEach(cv=>{
      cv.dataset.drawn='';
      const pid=cv.dataset.spark;
      if(pid)drawSpark(cv,pid);
      cv.dataset.drawn='1';
    });
  });
});

// GemRate copy + open helper
const RARITY_MAP={
  'SAR':'Special Art Rare','SR':'Super Rare','AR':'Art Rare',
  'RR':'Double Rare','RRR':'Triple Rare','UR':'Ultra Rare',
  'HR':'Hyper Rare','SSR':'Shiny Super Rare','S':'Shiny',
  'MA':'Master','MUR':'Master Ultra Rare',
  'CHR':'Character Rare','CSR':'Character Super Rare',
  'K':'K Rare','P':'Promo','PR':'Promo','C':'Common','U':'Uncommon','R':'Rare',
  'TR':'Trainer Rare','FA':'Full Art','GX':'GX','EX':'EX','V':'V',
  'VMAX':'VMAX','VSTAR':'VSTAR',
};
function copyGemRate(el,enName,year){
  const setM=enName.match(/\[([A-Za-z0-9-]+)\s+(\d+)(?:\/\d+)?\]/);
  const beforeBracket=enName.replace(/\[.*$/, '').trim();
  let pokeName=beforeBracket;
  const words=pokeName.split(/\s+/);
  for(let i=words.length-1;i>=1;i--){
    if(RARITY_MAP[words[i]]){
      pokeName=words.slice(0,i).join(' ');
      break;
    }
  }
  const cardNo=setM?setM[2]:'';
  const parts=['Pokemon Japanese',pokeName,cardNo].filter(p=>p);
  const text=parts.join(' ');

  const ta=document.createElement('textarea');
  ta.value=text;
  ta.style.cssText='position:fixed;left:-9999px;top:-9999px';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);

  if(confirm("検索用テキストをコピーしました！\nOKを押すとGemRateが開きます。\n貼り付けて検索してください。")){
    window.open("https://www.gemrate.com/search","_blank");
  }
}

// resetFilter — フィルタパネル内リセット（フィルタのみ。検索・ソート・お気に入りは維持）
function resetFilter(){
  sparkDays=0;
  document.querySelectorAll('.sp-btn').forEach(b=>{
    b.classList.toggle('active',parseInt(b.dataset.days)===0);
  });
  minTrades=0;
  document.getElementById('min-trades').value='0';
  document.getElementById('price-a-min').value='';
  document.getElementById('price-a-max').value='';
  document.getElementById('price-p-min').value='';
  document.getElementById('price-p-max').value='';
  document.getElementById('exclude-no-psa').checked=false;
  curPage=1;
  applySearch();
}

// resetAll — ヘッダークリックで全リセット（favSet, ownedMapは保持）
function resetAll(){
  // 検索クリア
  searchInput.value='';
  searchQuery='';
  // ソートを取引件数descに戻す
  curKey='sc';curDir='desc';
  sortSelect.value='sc';
  dirBtn.textContent='▼ 降順';
  // フィルタ全リセット
  sparkDays=0;
  document.querySelectorAll('.sp-btn').forEach(b=>{
    b.classList.toggle('active',parseInt(b.dataset.days)===0);
  });
  minTrades=0;
  document.getElementById('min-trades').value='0';
  document.getElementById('price-a-min').value='';
  document.getElementById('price-a-max').value='';
  document.getElementById('price-p-min').value='';
  document.getElementById('price-p-max').value='';
  document.getElementById('exclude-no-psa').checked=false;
  // フィルタパネル閉じる
  document.getElementById('filter-panel').classList.remove('open');
  document.getElementById('filter-toggle').classList.remove('active');
  // お気に入りフィルタOFF
  favOnly=false;
  updateFavBtn();
  // ページ1に戻す
  curPage=1;
  applySearch();
}

// URL状態管理
// デフォルト値の定義（URLから省略されていればこれを採用／URLにもこの値は書かない）
const DEFAULTS={q:'',sort:'sc',dir:'desc',page:1,fav:false,days:0,mt:0,aMin:'',aMax:'',pMin:'',pMax:'',noP:false};
function getStateFromURL(){
  const p=new URLSearchParams(location.search);
  return{
    q:p.get('q')||DEFAULTS.q,
    sort:p.get('sort')||DEFAULTS.sort,
    dir:p.get('dir')||DEFAULTS.dir,
    page:parseInt(p.get('page'))||DEFAULTS.page,
    fav:p.get('fav')==='1',
    days:parseInt(p.get('days'))||DEFAULTS.days,
    mt:(p.get('mt')!==null?parseInt(p.get('mt')):DEFAULTS.mt),
    aMin:p.get('aMin')||DEFAULTS.aMin,
    aMax:p.get('aMax')||DEFAULTS.aMax,
    pMin:p.get('pMin')||DEFAULTS.pMin,
    pMax:p.get('pMax')||DEFAULTS.pMax,
    noP:p.get('noP')==='1',
  };
}
function updateURL(){
  const p=new URLSearchParams();
  if(searchQuery!==DEFAULTS.q)p.set('q',searchQuery);
  if(curKey!==DEFAULTS.sort)p.set('sort',curKey);
  if(curDir!==DEFAULTS.dir)p.set('dir',curDir);
  if(curPage!==DEFAULTS.page)p.set('page',curPage);
  if(favOnly!==DEFAULTS.fav)p.set('fav','1');
  if(sparkDays!==DEFAULTS.days)p.set('days',sparkDays);
  if(minTrades!==DEFAULTS.mt)p.set('mt',minTrades);
  const aMin=document.getElementById('price-a-min').value;if(aMin!==DEFAULTS.aMin)p.set('aMin',aMin);
  const aMax=document.getElementById('price-a-max').value;if(aMax!==DEFAULTS.aMax)p.set('aMax',aMax);
  const pMin=document.getElementById('price-p-min').value;if(pMin!==DEFAULTS.pMin)p.set('pMin',pMin);
  const pMax=document.getElementById('price-p-max').value;if(pMax!==DEFAULTS.pMax)p.set('pMax',pMax);
  if(document.getElementById('exclude-no-psa').checked!==DEFAULTS.noP)p.set('noP','1');
  const qs=p.toString();
  history.replaceState(null,'',qs?'?'+qs:location.pathname);
}

// Init: URLから状態復元
(function initFromURL(){
  const s=getStateFromURL();
  searchQuery=s.q;searchInput.value=s.q;
  curKey=s.sort;sortSelect.value=s.sort;
  curDir=s.dir;dirBtn.textContent=s.dir==='desc'?'▼ 降順':'▲ 昇順';
  favOnly=s.fav;updateFavBtn();
  sparkDays=s.days;
  document.querySelectorAll('.sp-btn').forEach(b=>{b.classList.toggle('active',parseInt(b.dataset.days)===s.days)});
  minTrades=s.mt;document.getElementById('min-trades').value=String(s.mt);
  document.getElementById('price-a-min').value=s.aMin;
  document.getElementById('price-a-max').value=s.aMax;
  document.getElementById('price-p-min').value=s.pMin;
  document.getElementById('price-p-max').value=s.pMax;
  document.getElementById('exclude-no-psa').checked=s.noP;
  curPage=s.page;
})();

updatePortfolio();
applySearch(true); // 初期化時はURLのpageを維持

// ソート・フィルタ・☆を点滅（各自クリック/タップで独立して消える）
(function(){
  setTimeout(function(){
    var ss=document.getElementById('sort-select');
    var ft=document.getElementById('filter-toggle');
    if(ss){ss.classList.add('hint-blink');ss.addEventListener('click',function(){ss.classList.remove('hint-blink')},{once:true});ss.addEventListener('touchstart',function(){ss.classList.remove('hint-blink')},{once:true})}
    if(ft){ft.classList.add('hint-blink');ft.addEventListener('click',function(){ft.classList.remove('hint-blink')},{once:true});ft.addEventListener('touchstart',function(){ft.classList.remove('hint-blink')},{once:true})}
  },800);
})();
// ☆点滅はページ描画後に適用（ページネーションで再生成されるため）
var _starGlowActive=true;
function applyStarGlow(){
  if(!_starGlowActive)return;
  document.querySelectorAll('.fav-star').forEach(function(s){
    if(!s.classList.contains('star-glow')){
      s.classList.add('star-glow');
      s.addEventListener('click',function(){s.classList.remove('star-glow');},false);
      s.addEventListener('touchstart',function(){s.classList.remove('star-glow');},false);
    }
  });
}

// bfcache対応: 戻ってきた時にURL状態を再読込
window.addEventListener('pageshow',function(e){
  if(e.persisted){
    location.reload();
  }
});
</script>
<p style="font-size:.72rem;color:#9ca3af;text-align:center;margin:12px 0">※ 取引件数10件以上のカードのみ掲載しています（__TOTAL__枚）</p>
__FOOTER__
<script>document.addEventListener('click',function(e){var a=e.target.closest('.lk-tw-share');if(a&&a.dataset.tw){window.open('htt'+'ps://'+['x','com'].join('.')+'/inte'+'nt/tw'+'eet?text='+a.dataset.tw,'_blank');e.preventDefault();}});</script>
</body>
</html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTMLレポート生成")
    parser.add_argument("--top", type=int, default=0, help="上位N件のみ (0=全件)")
    parser.add_argument("--no-cards", action="store_true", help="個別カードページ生成をスキップ")
    args = parser.parse_args()

    cache = load_price_cache()
    cards = build_card_data(cache, args.top)
    generate_html(cards)
    if not args.no_cards:
        generate_card_pages(cards)
        # BOX詳細ページのIDリストを取得してサイトマップに含める
        box_ids = []
        try:
            import glob
            box_ids = [os.path.splitext(os.path.basename(f))[0] for f in glob.glob("box/*.html")]
        except Exception:
            pass
        generate_sitemap(cards, box_ids)
        generate_portfolio_page(cards)
