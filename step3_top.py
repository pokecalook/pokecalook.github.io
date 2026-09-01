"""
Step 3 (TOP): ランディングページ (index.html) 生成
使い方: python step3_top.py

price_data_api.json + box_price_data.json → index.html
- PSA10 高騰/下落ランキング（上位10件）
- 美品 高騰/下落ランキング（上位10件）
- BOX 高騰/下落ランキング（上位10件）
- 直近1週間の合計取引件数20件以上のみ対象
- 週間変動額（直近7日中央値 - 前週7日中央値）でソート
- タブ切替 + 横スクロール表示
"""

import json
import os
import re
import sys
import statistics
import html as htmllib
from datetime import datetime, timedelta, timezone
from common_html import get_header, get_nav, get_footer, get_gtag, get_meta_keywords

JST = timezone(timedelta(hours=9))

CARD_DATA_FILE = "price_data_api.json"
BOX_DATA_FILE = "box_price_data.json"
OUTPUT_HTML = "index.html"

RANKING_SIZE = 10
MIN_WEEKLY_TRADES = 20

# BOX名短縮用
_BOX_SERIES = [
    'MEGA', 'ソード&シールド', 'ソード＆シールド',
    'スカーレット&バイオレット', 'スカーレット＆バイオレット',
    'サン&ムーン', 'サン＆ムーン',
    'XY BREAK', 'XY', 'BW', 'DP', 'ADV', 'PCG', 'VS', 'neo', 'e',
]
_BOX_NAME_RE = re.compile(
    r'^ポケモンカードゲーム\s*(?:' + '|'.join(re.escape(s) for s in _BOX_SERIES) + r')?\s*'
)


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def parse_card_name(raw_name):
    """カード名を短縮表示用に整形。"""
    card_num_m = re.search(r'\[([^\]]+)\]', raw_name)
    card_num = card_num_m.group(1) if card_num_m else ""
    short_name = re.sub(r'\s*\[.*', '', raw_name).strip()
    parts = short_name.rsplit(' ', 1) if ' ' in short_name else [short_name]
    rarity_codes = {
        "C", "U", "R", "RR", "RRR", "SR", "SAR", "UR", "HR", "AR", "S",
        "P", "MA", "MUR", "CSR", "CHR", "SSR", "TR", "PR", "K", "A", "H", "FA",
    }
    has_rarity = len(parts) > 1 and parts[-1].replace(':', '').replace('仕様', '').strip() in rarity_codes
    if not has_rarity and card_num:
        short_name = f"{short_name} [{card_num}]"
    return short_name


def shorten_box_name(name):
    """BOX名から「ポケモンカードゲーム」+シリーズ名を削除"""
    short = _BOX_NAME_RE.sub('', name).strip()
    return short if short else name


# ---------------------------------------------------------------------------
# データ読み込み・ランキング計算
# ---------------------------------------------------------------------------

def load_card_data():
    if not os.path.exists(CARD_DATA_FILE):
        print(f"エラー: {CARD_DATA_FILE} が見つかりません。")
        sys.exit(1)
    with open(CARD_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_box_data():
    if not os.path.exists(BOX_DATA_FILE):
        print(f"エラー: {BOX_DATA_FILE} が見つかりません。")
        sys.exit(1)
    with open(BOX_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_card_rankings(cache):
    """カードデータからPSA10/美品のランキング候補を計算"""
    now = datetime.now()
    one_week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    two_weeks_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    psa10_items = []
    bihin_items = []

    for pid, data in cache.items():
        if not data.get("is_single_card"):
            continue

        name = htmllib.unescape(data.get("name", pid))
        short_name = parse_card_name(name)

        sold_data = data.get("sold_data", [])
        if not sold_data:
            continue

        sold_a = [(s["date"], s["price"]) for s in sold_data if s["condition"] == "A"]
        sold_psa10 = [(s["date"], s["price"]) for s in sold_data if s["condition"] == "PSA10"]

        psa10_1w = [p for d, p in sold_psa10 if d >= one_week_ago]
        psa10_2w = [p for d, p in sold_psa10 if d >= two_weeks_ago and d < one_week_ago]
        a_1w = [p for d, p in sold_a if d >= one_week_ago]
        a_2w = [p for d, p in sold_a if d >= two_weeks_ago and d < one_week_ago]

        total_trades = len(psa10_1w) + len(psa10_2w) + len(a_1w) + len(a_2w)
        if total_trades < MIN_WEEKLY_TRADES:
            continue

        if psa10_1w and psa10_2w:
            med_1w = int(statistics.median(psa10_1w))
            med_2w = int(statistics.median(psa10_2w))
            change = med_1w - med_2w
            psa10_items.append({
                "id": pid,
                "name": short_name,
                "img": f"images/{pid}.webp",
                "link": f"cards/{pid}.html",
                "price": med_1w,
                "change": change,
            })

        if a_1w and a_2w:
            med_1w = int(statistics.median(a_1w))
            med_2w = int(statistics.median(a_2w))
            change = med_1w - med_2w
            bihin_items.append({
                "id": pid,
                "name": short_name,
                "img": f"images/{pid}.webp",
                "link": f"cards/{pid}.html",
                "price": med_1w,
                "change": change,
            })

    return psa10_items, bihin_items


def compute_box_rankings(cache):
    """BOXデータからランキング候補を計算"""
    now = datetime.now()
    one_week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    two_weeks_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    box_items = []

    for pid, data in cache.items():
        if not data.get("is_box") or data.get("skipped"):
            continue

        name = data.get("name", "")
        short_name = shorten_box_name(name)
        prices = data.get("prices", [])
        dates = data.get("dates", [])

        if not prices or not dates:
            continue

        w1_prices = [p for d, p in zip(dates, prices) if d >= one_week_ago]
        w2_prices = [p for d, p in zip(dates, prices) if two_weeks_ago <= d < one_week_ago]

        if len(w1_prices) + len(w2_prices) < MIN_WEEKLY_TRADES:
            continue
        if not w1_prices or not w2_prices:
            continue

        med_1w = int(statistics.median(w1_prices))
        med_2w = int(statistics.median(w2_prices))
        change = med_1w - med_2w

        box_items.append({
            "id": pid,
            "name": short_name,
            "img": f"images/box_{pid}.webp",
            "link": f"box/{pid}.html",
            "price": med_1w,
            "change": change,
        })

    return box_items


def get_rankings(items):
    """アイテムリストから高騰/下落ランキングを生成"""
    rising = sorted([i for i in items if i["change"] > 0], key=lambda x: x["change"], reverse=True)
    falling = sorted([i for i in items if i["change"] < 0], key=lambda x: x["change"])
    return rising[:RANKING_SIZE], falling[:RANKING_SIZE]


# ---------------------------------------------------------------------------
# HTML生成
# ---------------------------------------------------------------------------

def render_card_html(item, rank):
    """ランキングカード1枚分のHTML"""
    img_path = item["img"]
    if os.path.exists(img_path):
        img_html = (
            f'<img src="{img_path}" alt="{htmllib.escape(item["name"])}" class="card-img" loading="lazy">'
        )
    else:
        icon = "📦" if "box_" in img_path else "🃏"
        img_html = f'<div class="card-img-placeholder">{icon}</div>'

    if item["change"] > 0:
        change_class = "change-up"
        change_text = f'+¥{item["change"]:,}'
    else:
        change_class = "change-down"
        change_text = f'-¥{abs(item["change"]):,}'

    rank_class = f"rank-{rank}" if rank <= 5 else "rank-other"

    return f'''      <a href="{item["link"]}" class="card">
        <span class="rank-badge {rank_class}">{rank}位</span>
        {img_html}
        <div class="card-name">{htmllib.escape(item["name"])}</div>
        <div class="card-price">¥{item["price"]:,}</div>
        <div class="card-change {change_class}">{change_text}</div>
      </a>'''


def render_tab_content(items, tab_id):
    """タブ1つ分のHTML"""
    if not items:
        cards_html = '      <p style="color:#9ca3af;font-size:.85rem;padding:12px">該当データなし</p>'
    else:
        cards_html = "\n".join(render_card_html(item, i + 1) for i, item in enumerate(items))
    return f'    <div class="tab-content" id="{tab_id}">\n{cards_html}\n    </div>'


def generate_html(psa10_rising, psa10_falling, bihin_rising, bihin_falling, box_rising, box_falling):
    """index.html を生成"""
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    # 各タブコンテンツ生成
    rising_psa10 = render_tab_content(psa10_rising, "rising-psa10").replace('class="tab-content"', 'class="tab-content active"')
    rising_bihin = render_tab_content(bihin_rising, "rising-bihin")
    rising_box = render_tab_content(box_rising, "rising-box")

    falling_psa10 = render_tab_content(psa10_falling, "falling-psa10").replace('class="tab-content"', 'class="tab-content active"')
    falling_bihin = render_tab_content(bihin_falling, "falling-bihin")
    falling_box = render_tab_content(box_falling, "falling-box")

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{get_gtag()}
<title>ポケカるっく - ポケモンカード相場チェッカー</title>
<meta name="description" content="ポケモンカードの相場をリアルタイムでチェック。PSA10・美品・未開封BOXの価格推移と週間ランキングを毎日更新。">
{get_meta_keywords()}
<link rel="canonical" href="https://pokecalook.com/">
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
<meta property="og:title" content="ポケカるっく - ポケモンカード相場チェッカー">
<meta property="og:description" content="ポケモンカードの相場をリアルタイムでチェック。PSA10・美品・未開封BOXの価格推移と週間ランキングを毎日更新。">
<meta property="og:image" content="https://pokecalook.com/images/logo.png">
<meta property="og:url" content="https://pokecalook.com/">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<style>
.container{{max-width:1100px;margin:0 auto}}
body{{padding:20px 16px;line-height:1.6}}
.hdr .desc{{color:#374151;font-size:.8rem;margin-top:12px;line-height:1.6;max-width:700px;margin-left:auto;margin-right:auto;background:rgba(255,255,255,.92);padding:12px 16px;border-radius:10px;border:1px solid #e5e7eb}}
.hdr .desc a{{color:#d97706;text-decoration:none;font-weight:600}}
.promo-note{{text-align:center;font-size:.7rem;color:#9ca3af;margin-bottom:20px}}
.updated{{text-align:center;font-size:.75rem;color:#9ca3af;margin-bottom:28px}}
.ranking-block{{margin-bottom:40px}}
.ranking-block h2{{font-size:1.3rem;font-weight:800;margin-bottom:14px;padding:10px 16px;background:#fff3e0;border-left:5px solid #ea580c;border-radius:0 8px 8px 0;color:#1a1a2e}}
.tabs{{display:flex;gap:6px;margin-bottom:16px}}
.tab-btn{{
  padding:8px 18px;border-radius:8px;font-size:.85rem;font-weight:700;
  border:2px solid #e5e7eb;background:#fff;color:#6b7280;cursor:pointer;transition:all .2s;
}}
.tab-btn.active{{border-color:#ea580c;background:#ea580c;color:#fff}}
.tab-btn:hover:not(.active){{border-color:#d1d5db;background:#f9fafb}}
.tab-content{{
  display:none;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;
  padding:4px 0 12px;-webkit-overflow-scrolling:touch;
}}
.tab-content.active{{display:flex}}
.tab-content::-webkit-scrollbar{{height:5px}}
.tab-content::-webkit-scrollbar-track{{background:#f3f4f6;border-radius:3px}}
.tab-content::-webkit-scrollbar-thumb{{background:#d1d5db;border-radius:3px}}
.card{{
  position:relative;min-width:180px;max-width:180px;scroll-snap-align:start;
  background:rgba(255,255,255,0.95);backdrop-filter:blur(8px);
  border-radius:14px;padding:14px 10px 14px;text-align:center;
  text-decoration:none;color:inherit;
  box-shadow:0 2px 8px rgba(0,0,0,.06);border:1px solid rgba(0,0,0,.04);
  transition:transform .2s,box-shadow .2s;
  display:flex;flex-direction:column;align-items:center;flex-shrink:0;
}}
.card:hover{{transform:translateY(-4px);box-shadow:0 8px 24px rgba(0,0,0,.1)}}
.rank-badge{{
  position:absolute;top:8px;left:8px;
  padding:3px 10px;border-radius:6px;
  font-size:.75rem;font-weight:900;color:#fff;
}}
.rank-1{{background:linear-gradient(135deg,#f59e0b,#d97706)}}
.rank-2{{background:linear-gradient(135deg,#9ca3af,#6b7280)}}
.rank-3{{background:linear-gradient(135deg,#d97706,#92400e)}}
.rank-4,.rank-5,.rank-other{{background:#e5e7eb;color:#374151}}
.card-img{{
  width:150px;height:200px;object-fit:contain;border-radius:8px;margin:8px 0;
  background:#f9fafb;
}}
.card-img-placeholder{{
  width:150px;height:200px;border-radius:8px;margin:8px 0;
  background:linear-gradient(135deg,#f3f4f6,#e5e7eb);
  display:flex;align-items:center;justify-content:center;font-size:2.5rem;color:#9ca3af;
}}
.card-name{{
  font-size:.82rem;font-weight:700;margin-top:8px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%;
}}
.card-price{{font-size:.9rem;color:#111827;margin-top:4px;font-weight:800}}
.card-change{{font-size:.9rem;font-weight:800;margin-top:6px;padding:3px 10px;border-radius:6px}}
.change-up{{color:#0d9488;background:#f0fdfa}}
.change-down{{color:#dc2626;background:#fef2f2}}
.note{{font-size:.72rem;color:#9ca3af;margin-top:12px;text-align:center}}
.footer{{
  text-align:center;padding:24px;margin-top:24px;
  font-size:.75rem;color:#6b7280;border-top:1px solid #f3f4f6;
}}
.footer a{{color:#6b7280;text-decoration:none;margin:0 8px}}
.footer a:hover{{color:#374151}}
@media(max-width:480px){{
  .card{{min-width:150px;max-width:150px}}
  .card-img,.card-img-placeholder{{width:120px;height:160px}}
}}
</style>
</head>
<body>
{get_header()}
<div class="container">
  {get_nav(active="top")}
  <p class="promo-note">※ 本サイトにはプロモーションが含まれています。</p>
  <p class="updated">最終更新: {now_str} JST</p>

  <!-- 高騰ランキング -->
  <div class="ranking-block" id="block-rising">
    <h2>🔥 高騰ランキング</h2>
    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('rising','psa10',this)">PSA10</button>
      <button class="tab-btn" onclick="switchTab('rising','bihin',this)">美品</button>
      <button class="tab-btn" onclick="switchTab('rising','box',this)">BOX</button>
    </div>
{rising_psa10}
{rising_bihin}
{rising_box}
  </div>

  <!-- 下落ランキング -->
  <div class="ranking-block" id="block-falling">
    <h2>📉 下落ランキング</h2>
    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('falling','psa10',this)">PSA10</button>
      <button class="tab-btn" onclick="switchTab('falling','bihin',this)">美品</button>
      <button class="tab-btn" onclick="switchTab('falling','box',this)">BOX</button>
    </div>
{falling_psa10}
{falling_bihin}
{falling_box}
  </div>

  <p class="note">※ 直近1週間の取引件数が20件以上のカード/BOXのみを対象としています</p>
</div>

{get_footer()}
<script>
function switchTab(section,type,btn){{
  var block=document.getElementById('block-'+section);
  block.querySelectorAll('.tab-content').forEach(function(el){{el.classList.remove('active')}});
  block.querySelectorAll('.tab-btn').forEach(function(el){{el.classList.remove('active')}});
  document.getElementById(section+'-'+type).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body>
</html>'''

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ {OUTPUT_HTML} を生成しました（{len(html):,} bytes）")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("Step 3 (TOP): ランディングページ生成")
    print("=" * 50)

    print("📂 カードデータ読み込み中...")
    card_cache = load_card_data()
    print(f"   → {len(card_cache):,} 件")

    print("📂 BOXデータ読み込み中...")
    box_cache = load_box_data()
    print(f"   → {len(box_cache):,} 件")

    print("📊 ランキング計算中...")
    psa10_items, bihin_items = compute_card_rankings(card_cache)
    box_items = compute_box_rankings(box_cache)

    psa10_rising, psa10_falling = get_rankings(psa10_items)
    bihin_rising, bihin_falling = get_rankings(bihin_items)
    box_rising, box_falling = get_rankings(box_items)

    print(f"   PSA10: 高騰{len(psa10_rising)}件 / 下落{len(psa10_falling)}件")
    print(f"   美品:  高騰{len(bihin_rising)}件 / 下落{len(bihin_falling)}件")
    print(f"   BOX:   高騰{len(box_rising)}件 / 下落{len(box_falling)}件")

    print("📝 HTML生成中...")
    generate_html(psa10_rising, psa10_falling, bihin_rising, bihin_falling, box_rising, box_falling)
    print("🎉 完了!")


if __name__ == "__main__":
    main()
