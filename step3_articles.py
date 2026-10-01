"""
Step 3 (Articles): データドリブン記事ページ生成（アーカイブ対応）
使い方: python step3_articles.py

price_data_api.json + box_price_data.json を元に、独自の解説記事を生成。
- articles/YYYY-MM-DD-rising.html : 高騰カードTOP10（日付付きアーカイブ）
- articles/YYYY-MM-DD-falling.html : 下落カードTOP10（日付付きアーカイブ）
- articles/YYYY-MM-DD-box.html : BOX相場トレンド（日付付きアーカイブ）
- articles/weekly-rising.html : 最新版コピー（既存URL維持）
- articles/weekly-falling.html : 最新版コピー
- articles/box-trends.html : 最新版コピー
- articles/index.html : 記事一覧（過去アーカイブ含む）
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
ARTICLES_DIR = "articles"
SITE_URL = "https://pokecalook.com"

TOP_N = 10
MIN_WEEKLY_TRADES = 20

_BOX_SERIES = [
    'MEGA', 'ソード&シールド', 'ソード＆シールド',
    'スカーレット&バイオレット', 'スカーレット＆バイオレット',
    'サン&ムーン', 'サン＆ムーン',
    'XY BREAK', 'XY', 'BW', 'DP', 'ADV', 'PCG', 'VS', 'neo', 'e',
]
_BOX_NAME_RE = re.compile(
    r'^ポケモンカードゲーム\s*(?:' + '|'.join(re.escape(s) for s in _BOX_SERIES) + r')?\s*'
)


def _esc(s):
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def parse_card_name(raw_name):
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
    short = _BOX_NAME_RE.sub('', name).strip()
    return short if short else name


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


def compute_card_movements(cache):
    """カードデータから美品/PSA10それぞれの週間変動データを計算"""
    now = datetime.now()
    one_week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    two_weeks_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    items = []  # 美品とPSA10のどちらか変動額が大きい方を採用
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

        a_1w = [p for d, p in sold_a if d >= one_week_ago]
        a_2w = [p for d, p in sold_a if d >= two_weeks_ago and d < one_week_ago]
        psa10_1w = [p for d, p in sold_psa10 if d >= one_week_ago]
        psa10_2w = [p for d, p in sold_psa10 if d >= two_weeks_ago and d < one_week_ago]

        total = len(a_1w) + len(a_2w) + len(psa10_1w) + len(psa10_2w)
        if total < MIN_WEEKLY_TRADES:
            continue

        a_change = None
        a_med = None
        if a_1w and a_2w:
            a_med = int(statistics.median(a_1w))
            a_change = a_med - int(statistics.median(a_2w))
        psa_change = None
        psa_med = None
        if psa10_1w and psa10_2w:
            psa_med = int(statistics.median(psa10_1w))
            psa_change = psa_med - int(statistics.median(psa10_2w))

        # 変動額が大きい方を採用
        candidates = []
        if a_change is not None:
            candidates.append(("美品", a_change, a_med, len(a_1w) + len(a_2w)))
        if psa_change is not None:
            candidates.append(("PSA10", psa_change, psa_med, len(psa10_1w) + len(psa10_2w)))
        if not candidates:
            continue
        cond, change, med, trades = max(candidates, key=lambda x: abs(x[1]))

        items.append({
            "id": pid,
            "name": short_name,
            "condition": cond,
            "change": change,
            "median": med,
            "trades": trades,
            "total_trades": total,
            "img": f"../images/{pid}.webp",
            "link": f"../cards/{pid}.html",
        })
    return items


def compute_box_movements(cache):
    """BOXデータから週間変動データを計算"""
    now = datetime.now()
    one_week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    two_weeks_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    items = []
    for pid, data in cache.items():
        if not data.get("is_box") or data.get("skipped"):
            continue
        name = data.get("name", "")
        short_name = shorten_box_name(name)
        prices = data.get("prices", [])
        dates = data.get("dates", [])
        if not prices or not dates:
            continue

        w1 = [p for d, p in zip(dates, prices) if d >= one_week_ago]
        w2 = [p for d, p in zip(dates, prices) if two_weeks_ago <= d < one_week_ago]
        if len(w1) + len(w2) < MIN_WEEKLY_TRADES:
            continue
        if not w1 or not w2:
            continue
        med = int(statistics.median(w1))
        change = med - int(statistics.median(w2))
        items.append({
            "id": pid,
            "name": short_name,
            "change": change,
            "median": med,
            "trades": len(w1) + len(w2),
            "img": f"../images/box_{pid}.webp",
            "link": f"../box/{pid}.html",
        })
    return items


# ---------------------------------------------------------------------------
# 解説文生成
# ---------------------------------------------------------------------------

def comment_for_card(item, rank):
    """1枚のカードに対する個別コメント文を生成（10位まで被りなし）"""
    from datetime import date
    name_esc = _esc(item["name"])
    cond = item["condition"]
    change = item["change"]
    med = item["median"]
    trades = item["trades"]

    abs_change = abs(change)
    sign = "+" if change > 0 else "-"

    # 日付+rankでパターンを決定（毎日違う組み合わせ、同日内で被りなし）
    day_seed = date.today().toordinal()
    pattern_idx = (day_seed + rank) % 10

    # 上昇パターン10種
    up_comments = [
        f"週間{trades}件の取引があり、中央値は¥{med:,}まで上がっています。1週間で{sign}¥{abs_change:,}の変動です。",
        f"取引件数は週{trades}件。先週と比べて{sign}¥{abs_change:,}動いています。買いたい人が増えている印象です。",
        f"中央値¥{med:,}で、先週から{sign}¥{abs_change:,}の上昇。週間{trades}件取引されており、注目度が高い状態です。",
        f"先週比{sign}¥{abs_change:,}。週{trades}件ペースで取引されています。この価格帯で安定するか、さらに上がるか注目です。",
        f"¥{med:,}まで上昇（{sign}¥{abs_change:,}）。取引は週{trades}件あり、実需を伴った値動きと言えます。",
        f"週間の取引件数は{trades}件で、中央値は{sign}¥{abs_change:,}の変動。じわじわと価格が切り上がっています。",
        f"中央値¥{med:,}（{sign}¥{abs_change:,}）。週{trades}件の取引があり、コンスタントに売れている状況です。",
        f"先週から{sign}¥{abs_change:,}上がって¥{med:,}に。取引ペースは週{trades}件で、需要は衰えていません。",
        f"¥{med:,}で推移中。週間{trades}件取引、{sign}¥{abs_change:,}の上昇。出品があればすぐ売れる状態が続いています。",
        f"取引{trades}件/週。{sign}¥{abs_change:,}の上昇で¥{med:,}に到達。先週より明確に買われています。",
    ]

    # 下落パターン10種
    down_comments = [
        f"週間{trades}件の取引があり、中央値は¥{med:,}まで下がっています。1週間で{sign}¥{abs_change:,}の変動です。",
        f"取引件数は週{trades}件。先週と比べて{sign}¥{abs_change:,}動いています。売りたい人が増えている印象です。",
        f"中央値¥{med:,}で、先週から{sign}¥{abs_change:,}の下落。週間{trades}件取引されており、出品数が多い状態です。",
        f"先週比{sign}¥{abs_change:,}。週{trades}件ペースで取引されています。この価格帯で下げ止まるか注目です。",
        f"¥{med:,}まで下落（{sign}¥{abs_change:,}）。取引は週{trades}件あり、売り圧が続いています。",
        f"週間の取引件数は{trades}件で、中央値は{sign}¥{abs_change:,}の変動。じわじわと価格が下がっています。",
        f"中央値¥{med:,}（{sign}¥{abs_change:,}）。週{trades}件の取引があり、値下がりが続いている状況です。",
        f"先週から{sign}¥{abs_change:,}下がって¥{med:,}に。取引ペースは週{trades}件で、まだ底が見えません。",
        f"¥{med:,}で推移中。週間{trades}件取引、{sign}¥{abs_change:,}の下落。出品が増えて価格が押されています。",
        f"取引{trades}件/週。{sign}¥{abs_change:,}の下落で¥{med:,}に。先週より明確に売られています。",
    ]

    comments = up_comments if change > 0 else down_comments
    comment = comments[pattern_idx]

    return f'''      <div class="article-card">
        <div class="article-rank">{rank}</div>
        <a href="{item["link"]}" class="article-card-link">
          <img src="{item["img"]}" alt="{name_esc}" class="article-thumb" loading="lazy">
        </a>
        <div class="article-card-body">
          <h3><a href="{item["link"]}">{name_esc}</a></h3>
          <p class="article-stats">
            <strong>{cond}</strong> 中央値 ¥{med:,} ／
            週間変動 <span class="{'up' if change > 0 else 'down'}">{sign}¥{abs_change:,}</span> ／
            取引 {trades}件
          </p>
          <p class="article-comment">{comment}</p>
        </div>
      </div>'''


def comment_for_box(item, rank):
    """BOXの個別コメント文を生成（10位まで被りなし）"""
    from datetime import date
    name_esc = _esc(item["name"])
    change = item["change"]
    med = item["median"]
    trades = item["trades"]
    abs_change = abs(change)
    sign = "+" if change > 0 else "-"

    # 日付+rankでパターンを決定
    day_seed = date.today().toordinal()
    pattern_idx = (day_seed + rank + 5) % 10  # +5でカードとずらす

    up_comments = [
        f"週間{trades}個の取引があり、中央値は¥{med:,}まで上がっています。先週から{sign}¥{abs_change:,}の変動です。",
        f"取引件数は週{trades}個。先週と比べて{sign}¥{abs_change:,}動いています。買いたい人が増えている印象です。",
        f"中央値¥{med:,}で、先週から{sign}¥{abs_change:,}の上昇。週間{trades}個取引されており、注目度が高い状態です。",
        f"先週比{sign}¥{abs_change:,}。週{trades}個ペースで取引されています。この価格帯で安定するか注目です。",
        f"¥{med:,}まで上昇（{sign}¥{abs_change:,}）。取引は週{trades}個あり、実需を伴った値動きです。",
        f"週間の取引件数は{trades}個で、中央値は{sign}¥{abs_change:,}の変動。じわじわと価格が切り上がっています。",
        f"中央値¥{med:,}（{sign}¥{abs_change:,}）。週{trades}個の取引があり、コンスタントに売れています。",
        f"先週から{sign}¥{abs_change:,}上がって¥{med:,}に。取引ペースは週{trades}個で、需要は衰えていません。",
        f"¥{med:,}で推移中。週間{trades}個取引、{sign}¥{abs_change:,}の上昇。出品があればすぐ売れる状態です。",
        f"取引{trades}個/週。{sign}¥{abs_change:,}の上昇で¥{med:,}に到達。先週より明確に買われています。",
    ]

    down_comments = [
        f"週間{trades}個の取引があり、中央値は¥{med:,}まで下がっています。先週から{sign}¥{abs_change:,}の変動です。",
        f"取引件数は週{trades}個。先週と比べて{sign}¥{abs_change:,}動いています。売りたい人が増えている印象です。",
        f"中央値¥{med:,}で、先週から{sign}¥{abs_change:,}の下落。週間{trades}個取引されており、出品数が多い状態です。",
        f"先週比{sign}¥{abs_change:,}。週{trades}個ペースで取引されています。この価格帯で下げ止まるか注目です。",
        f"¥{med:,}まで下落（{sign}¥{abs_change:,}）。取引は週{trades}個あり、売り圧が続いています。",
        f"週間の取引件数は{trades}個で、中央値は{sign}¥{abs_change:,}の変動。じわじわと価格が下がっています。",
        f"中央値¥{med:,}（{sign}¥{abs_change:,}）。週{trades}個の取引があり、値下がりが続いている状況です。",
        f"先週から{sign}¥{abs_change:,}下がって¥{med:,}に。取引ペースは週{trades}個で、まだ底が見えません。",
        f"¥{med:,}で推移中。週間{trades}個取引、{sign}¥{abs_change:,}の下落。出品が増えて価格が押されています。",
        f"取引{trades}個/週。{sign}¥{abs_change:,}の下落で¥{med:,}に。先週より明確に売られています。",
    ]

    comments = up_comments if change > 0 else down_comments
    comment = comments[pattern_idx]

    return f'''      <div class="article-card">
        <div class="article-rank">{rank}</div>
        <a href="{item["link"]}" class="article-card-link">
          <img src="{item["img"]}" alt="{name_esc}" class="article-thumb" loading="lazy">
        </a>
        <div class="article-card-body">
          <h3><a href="{item["link"]}">{name_esc}</a></h3>
          <p class="article-stats">
            中央値 ¥{med:,} ／ 週間変動 <span class="{'up' if change > 0 else 'down'}">{sign}¥{abs_change:,}</span> ／ 取引 {trades}件
          </p>
          <p class="article-comment">{comment}</p>
        </div>
      </div>'''


# ---------------------------------------------------------------------------
# 共通テンプレート
# ---------------------------------------------------------------------------

ARTICLE_CSS = """.main-content{max-width:900px;margin:0 auto}
.back{display:inline-block;margin-bottom:16px;color:#3b82f6;text-decoration:none;font-weight:600;font-size:.9rem}
.back:hover{text-decoration:underline}
h2{font-size:1.25rem;color:#1e40af;margin:28px 0 12px;padding-bottom:8px;border-bottom:3px solid #dbeafe}
h3{font-size:1.05rem;color:#1a1a2e;margin:0 0 8px}
h3 a{color:#1a1a2e;text-decoration:none}
h3 a:hover{color:#dc2626;text-decoration:underline}
p{margin:8px 0;color:#374151}
.intro{background:#fff;border:2px solid #e5e7eb;border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.updated{color:#6b7280;font-size:.85rem;text-align:center;margin-bottom:20px}
.toc{background:#eff6ff;border:2px solid #93c5fd;border-radius:10px;padding:14px 18px;margin:16px 0}
.toc h3{color:#1e40af;font-size:.95rem;margin-bottom:8px}
.toc ul{list-style:none;padding:0}
.toc li{margin:4px 0;font-size:.9rem}
.toc a{color:#2563eb;text-decoration:none}
.toc a:hover{text-decoration:underline}
.article-list{display:flex;flex-direction:column;gap:14px;margin:16px 0}
.article-card{display:flex;gap:14px;background:#fff;border:2px solid #e5e7eb;border-radius:12px;padding:14px;box-shadow:0 2px 6px rgba(0,0,0,.04);position:relative}
.article-rank{position:absolute;top:-8px;left:-8px;width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#f59e0b,#d97706);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:.95rem;box-shadow:0 2px 6px rgba(0,0,0,.15)}
.article-card-link{flex-shrink:0}
.article-thumb{width:90px;height:120px;object-fit:contain;border-radius:8px;background:#f9fafb;display:block}
.article-card-body{flex:1;min-width:0}
.article-card-body h3{font-size:1rem;font-weight:700;margin-bottom:6px;line-height:1.4}
.article-stats{font-size:.82rem;color:#6b7280;margin:4px 0;line-height:1.5}
.article-stats strong{color:#374151}
.article-comment{font-size:.85rem;color:#374151;margin-top:6px;line-height:1.7}
.up{color:#0d9488;font-weight:700}
.down{color:#dc2626;font-weight:700}
.summary{background:#fefce8;border:2px solid #fcd34d;border-radius:12px;padding:16px 20px;margin:20px 0}
.summary h3{color:#92400e;margin-bottom:8px}
.summary p{font-size:.9rem;color:#78350f}
.disclaimer{font-size:.75rem;color:#9ca3af;text-align:center;margin-top:20px;padding:12px}
.footer{text-align:center;padding:20px;margin-top:24px;font-size:.75rem;color:#6b7280;border-top:1px solid #f3f4f6}
.footer a{color:#6b7280;text-decoration:none;margin:0 8px}
.footer a:hover{color:#374151}
@media(max-width:768px){
  body{padding:8px}
  .hdr h1{font-size:1.2rem}
  .article-thumb{width:70px;height:95px}
  .article-rank{width:28px;height:28px;font-size:.8rem;top:-6px;left:-6px}
  h3{font-size:.95rem}
}"""

FOOTER = get_footer(prefix="../")


def render_page(title, description, slug, body_html, extra_css=""):
    """共通テンプレートでページを生成"""
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    extra_style = f"\n<style>{extra_css}</style>" if extra_css else ""
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{get_gtag()}
<title>{title} - ポケカるっく</title>
<meta name="description" content="{description}">
{get_meta_keywords()}
<link rel="canonical" href="{SITE_URL}/articles/{slug}.html">
<link rel="icon" type="image/png" href="../images/logo.png">
<link rel="stylesheet" href="../common.css">
<meta property="og:title" content="{title} - ポケカるっく">
<meta property="og:description" content="{description}">
<meta property="og:type" content="article">
<meta property="og:url" content="{SITE_URL}/articles/{slug}.html">
<meta property="og:image" content="{SITE_URL}/images/logo.png">
<style>{ARTICLE_CSS}</style>{extra_style}
</head>
<body>
{get_header(prefix="../")}
{get_nav(prefix="../", active="articles")}
<div class="main-content">
{body_html}
<p class="disclaimer">※ 本記事の数値は本サイト集計データから生成しています。最終更新: {now_str} JST</p>
</div>
{FOOTER}
</body>
</html>'''


# ---------------------------------------------------------------------------
# 各記事の生成
# ---------------------------------------------------------------------------

def generate_weekly_rising(card_items):
    """今週の高騰カードTOP10解説"""
    rising = sorted([i for i in card_items if i["change"] > 0], key=lambda x: x["change"], reverse=True)[:TOP_N]
    if not rising:
        return None

    now = datetime.now(JST)
    week_end = now
    week_start = now - timedelta(days=6)
    date_range = f"{week_start.strftime('%Y年%m月%d日')}〜{week_end.strftime('%m月%d日')}"
    week_label = date_range
    cards_html = "\n".join(comment_for_card(item, i + 1) for i, item in enumerate(rising))

    total_up = sum(i["change"] for i in rising)
    avg_up = total_up // len(rising)
    top1 = rising[0]

    body = f'''<div class="hdr"><h1>🔥 高騰ポケモンカードTOP{len(rising)}【{date_range}】</h1></div>
<p class="updated">{week_label} 集計</p>

<div class="intro">
  <h2 style="border:none;margin:0 0 10px;padding:0">この記事の概要</h2>
  <p>本記事は、ポケカるっくが集計した国内取引データをもとに、直近1週間で<strong>もっとも値上がり幅が大きかったポケモンカードTOP{len(rising)}</strong>を独自にピックアップして解説するレポートです。</p>
  <p>選定基準は「直近1週間の取引中央値」と「前週の取引中央値」の差額（変動額）で、美品・PSA10のうち変動が大きい方の数値を採用しています。取引件数が直近2週間で{MIN_WEEKLY_TRADES}件以上のカードのみを対象とすることで、サンプル不足による誤判定を避けています。</p>
  <p>毎週更新されますので、ブックマークいただくと相場感の把握に便利です。</p>
</div>

<div class="summary">
  <h3>📊 今週の総括</h3>
  <p>今週の高騰TOP{len(rising)}の合計変動額は <strong>+¥{total_up:,}</strong>、平均すると1枚あたり <strong>+¥{avg_up:,}</strong> の上昇です。
  特に首位の <strong>{_esc(top1["name"])}（{top1["condition"]}）</strong> は <strong>+¥{top1["change"]:,}</strong> と突出した動きを見せています。</p>
</div>

<h2>🏆 高騰ランキング詳細</h2>
<div class="article-list">
{cards_html}
</div>

<h2>🔍 ランキングをどう読み解くか</h2>
<div class="intro">
  <p>変動額が大きいからといって、必ずしも「今が買い時」または「売り時」とは限りません。以下の3つの観点で見極めることをおすすめします。</p>
  <ul style="margin-left:20px;color:#374151">
    <li><strong>取引件数</strong>: サンプル数が少ないカードは中央値が外れ値の影響を受けやすく、変動額が誇張されることがあります。</li>
    <li><strong>美品とPSA10の連動</strong>: 両方が同方向に動いている場合は本物のトレンド、片方だけが動いている場合はグレード別の需給変動の可能性があります。</li>
    <li><strong>1ヶ月変動との比較</strong>: 週間で急騰しても1ヶ月で見るとマイナスというケースもあるため、より長い期間の動きも併せて確認しましょう。</li>
  </ul>
  <p>個別カードの詳細データ（取引期間・最高値・最安値・1ヶ月変動）は、各カード名のリンクから個別ページに遷移して確認できます。</p>
</div>

<h2>🛒 関連リンク</h2>
<div class="intro">
  <ul style="margin-left:20px;color:#374151">
    <li><a href="../report.html" style="color:#3b82f6">シングル相場一覧</a> - 全カードの相場を倍率順・変動順でソート</li>
    <li><a href="../index.html" style="color:#3b82f6">トップページ</a> - 高騰／下落ランキングをタブ切替で確認</li>
    <li><a href="../about.html" style="color:#3b82f6">このサイトについて</a> - データ集計方法の詳細</li>
  </ul>
</div>'''

    return render_page(
        title="今週の高騰ポケモンカードTOP10",
        description=f"ポケカるっくが集計した取引データから、直近1週間で値上がりした人気ポケモンカードTOP{TOP_N}を独自解説。{week_label}更新。",
        slug="weekly-rising",
        body_html=body,
    )


def generate_weekly_falling(card_items):
    """今週の下落カードTOP10解説"""
    falling = sorted([i for i in card_items if i["change"] < 0], key=lambda x: x["change"])[:TOP_N]
    if not falling:
        return None

    now = datetime.now(JST)
    week_end = now
    week_start = now - timedelta(days=6)
    date_range = f"{week_start.strftime('%Y年%m月%d日')}〜{week_end.strftime('%m月%d日')}"
    week_label = date_range
    cards_html = "\n".join(comment_for_card(item, i + 1) for i, item in enumerate(falling))

    total_down = sum(i["change"] for i in falling)
    avg_down = total_down // len(falling)
    top1 = falling[0]

    body = f'''<div class="hdr"><h1>📉 下落ポケモンカードTOP{len(falling)}【{date_range}】</h1></div>
<p class="updated">{week_label} 集計</p>

<div class="intro">
  <h2 style="border:none;margin:0 0 10px;padding:0">この記事の概要</h2>
  <p>本記事は、ポケカるっくが集計した国内取引データから、直近1週間で<strong>もっとも値下がり幅が大きかったポケモンカードTOP{len(falling)}</strong>を独自にピックアップしてレポートしています。</p>
  <p>下落カードを把握することは、買い増しのタイミングを計る上でも、保有資産の評価額を把握する上でも重要です。「下げ止まり」のサインを見極めるには、変動額だけでなく取引件数の推移も併せて見ることがポイントです。</p>
</div>

<div class="summary">
  <h3>📊 今週の総括</h3>
  <p>今週の下落TOP{len(falling)}の合計変動額は <strong>-¥{abs(total_down):,}</strong>、平均すると1枚あたり <strong>-¥{abs(avg_down):,}</strong> の下落です。
  なかでも首位の <strong>{_esc(top1["name"])}（{top1["condition"]}）</strong> は <strong>-¥{abs(top1["change"]):,}</strong> ともっとも大きく値を下げています。</p>
</div>

<h2>📉 下落ランキング詳細</h2>
<div class="article-list">
{cards_html}
</div>

<h2>🔍 下落カードを買うべきか</h2>
<div class="intro">
  <p>「下がっているから買い」と単純には判断できないのが、ポケカ相場の難しいところです。次のチェックポイントを参考にしてください。</p>
  <ul style="margin-left:20px;color:#374151">
    <li><strong>需要の根本要因</strong>: 一時的な調整なのか、人気の長期的な低下なのかで判断は変わります。大会で禁止になった、新弾で類似カードが登場した、などの背景があれば下落は続く傾向があります。</li>
    <li><strong>取引件数の推移</strong>: 価格は下がっているが取引件数が減っていない場合、需要は維持されているサインです。逆に取引件数も減っているなら、人気そのものが冷えている可能性があります。</li>
    <li><strong>過去の底値水準</strong>: 個別カードページで過去の最安値・最高値を確認し、現在価格がどの位置にあるかを把握すると、底値接近かどうかを判断しやすくなります。</li>
  </ul>
</div>

<h2>🛒 関連リンク</h2>
<div class="intro">
  <ul style="margin-left:20px;color:#374151">
    <li><a href="weekly-rising.html" style="color:#3b82f6">今週の高騰ポケモンカードTOP10</a></li>
    <li><a href="../report.html" style="color:#3b82f6">シングル相場一覧</a></li>
    <li><a href="../about.html" style="color:#3b82f6">このサイトについて</a></li>
  </ul>
</div>'''

    return render_page(
        title="今週の下落ポケモンカードTOP10",
        description=f"ポケカるっくが集計した取引データから、直近1週間で値下がりしたポケモンカードTOP{TOP_N}を独自解説。{week_label}更新。",
        slug="weekly-falling",
        body_html=body,
    )


def generate_box_trends(box_items):
    """未開封BOX相場トレンド解説"""
    rising = sorted([i for i in box_items if i["change"] > 0], key=lambda x: x["change"], reverse=True)[:5]
    falling = sorted([i for i in box_items if i["change"] < 0], key=lambda x: x["change"])[:5]
    if not rising and not falling:
        return None

    now = datetime.now(JST)
    week_end = now
    week_start = now - timedelta(days=6)
    date_range = f"{week_start.strftime('%Y年%m月%d日')}〜{week_end.strftime('%m月%d日')}"
    week_label = date_range
    rising_html = "\n".join(comment_for_box(item, i + 1) for i, item in enumerate(rising)) if rising else "<p>該当データなし</p>"
    falling_html = "\n".join(comment_for_box(item, i + 1) for i, item in enumerate(falling)) if falling else "<p>該当データなし</p>"

    body = f'''<div class="hdr"><h1>📦 未開封BOX相場トレンド【{date_range}】</h1></div>
<p class="updated">{week_label} 集計</p>

<div class="intro">
  <h2 style="border:none;margin:0 0 10px;padding:0">この記事の概要</h2>
  <p>未開封BOXは、シングルカードよりも長期保管・投資対象として注目されることが多いアイテムです。本記事では、ポケカるっくが集計した国内取引データから、直近1週間で値動きが大きかった未開封BOXを上昇・下落それぞれ上位5タイトルピックアップして解説します。</p>
  <p>BOXの相場は新弾の発売・再販の有無・人気カードの収録状況などに大きく影響されます。シングル相場と組み合わせて見ることで、市場全体の温度感が見えてきます。</p>
</div>

<h2>🔥 値上がりBOX TOP5</h2>
<div class="article-list">
{rising_html}
</div>

<h2>📉 値下がりBOX TOP5</h2>
<div class="article-list">
{falling_html}
</div>

<h2>🎯 BOX購入時のチェックポイント</h2>
<div class="intro">
  <ul style="margin-left:20px;color:#374151">
    <li><strong>シュリンクの有無</strong>: 中古BOXはシュリンク有無で価格が大きく変わります。長期保管目的ならシュリンク付きが鉄則です。</li>
    <li><strong>再販の可能性</strong>: 公式から再販がアナウンスされると相場は急落することがあります。購入前に最新情報を確認しましょう。</li>
    <li><strong>収録カードの相場</strong>: BOX価格は中身のシングルカード相場に大きく依存します。<a href="../report.html" style="color:#3b82f6">シングル相場一覧</a>で収録カードの動向もあわせて確認することをおすすめします。</li>
  </ul>
</div>

<h2>🛒 関連リンク</h2>
<div class="intro">
  <ul style="margin-left:20px;color:#374151">
    <li><a href="../box.html" style="color:#3b82f6">未開封BOX相場一覧</a></li>
    <li><a href="weekly-rising.html" style="color:#3b82f6">今週の高騰ポケモンカードTOP10</a></li>
    <li><a href="weekly-falling.html" style="color:#3b82f6">今週の下落ポケモンカードTOP10</a></li>
  </ul>
</div>'''

    return render_page(
        title="今週の未開封BOX相場トレンド",
        description=f"ポケカるっくが集計した取引データから、直近1週間で値動きが大きかった未開封BOXを独自解説。{week_label}更新。",
        slug="box-trends",
        body_html=body,
    )


def generate_index():
    """記事一覧ページ（カテゴリ別タブ表示）"""
    # articles/ ディレクトリから日付付きファイルを検出
    rising_entries = []
    falling_entries = []
    box_entries = []

    if os.path.exists(ARTICLES_DIR):
        for fname in os.listdir(ARTICLES_DIR):
            m = re.match(r'^(\d{4}-\d{2}-\d{2})-(rising|falling|box)\.html$', fname)
            if m:
                date_str = m.group(1)
                article_type = m.group(2)
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    continue
                week_start = dt - timedelta(days=6)
                date_range = f"{week_start.strftime('%m/%d')}〜{dt.strftime('%m/%d')}"
                entry = (date_str, fname, date_range)
                if article_type == "rising":
                    rising_entries.append(entry)
                elif article_type == "falling":
                    falling_entries.append(entry)
                else:
                    box_entries.append(entry)

    # 日付降順でソート
    rising_entries.sort(key=lambda x: x[0], reverse=True)
    falling_entries.sort(key=lambda x: x[0], reverse=True)
    box_entries.sort(key=lambda x: x[0], reverse=True)

    def make_list_html(entries, emoji, label):
        if not entries:
            return f'<p style="color:#6b7280;text-align:center;padding:20px">まだ記事がありません。</p>'
        html = ""
        for date_str, fname, date_range in entries[:30]:  # 最新30件
            html += f'''  <a href="{fname}" class="archive-item">
    <span class="archive-emoji">{emoji}</span>
    <span class="archive-title">{label}【{date_range}】</span>
    <span class="archive-date">{date_str}</span>
  </a>\n'''
        return html

    rising_html = make_list_html(rising_entries, "🔥", "高騰カードTOP10")
    falling_html = make_list_html(falling_entries, "📉", "下落カードTOP10")
    box_html = make_list_html(box_entries, "📦", "BOX相場トレンド")

    body = f'''<div class="hdr"><h1>📰 ポケカるっく 記事アーカイブ</h1></div>

<div class="intro">
  <p>ポケカるっくが集計したデータをもとに、ポケモンカード相場のトレンドをレポートしています。すべての記事は実取引データから自動生成されており、毎日更新・蓄積されます。</p>
</div>

<h2>📌 最新の記事</h2>
<div class="latest-cards">
  <a href="weekly-rising.html" class="latest-card latest-rising">
    <span class="latest-emoji">🔥</span>
    <span class="latest-title">今週の高騰カードTOP10</span>
    <span class="latest-desc">直近1週間でもっとも値上がりしたカード</span>
  </a>
  <a href="weekly-falling.html" class="latest-card latest-falling">
    <span class="latest-emoji">📉</span>
    <span class="latest-title">今週の下落カードTOP10</span>
    <span class="latest-desc">直近1週間でもっとも値下がりしたカード</span>
  </a>
  <a href="box-trends.html" class="latest-card latest-box">
    <span class="latest-emoji">📦</span>
    <span class="latest-title">今週のBOX相場トレンド</span>
    <span class="latest-desc">未開封BOXの値上がり・値下がりTOP5</span>
  </a>
</div>

<h2>📂 過去の記事</h2>
<div class="tab-container">
  <div class="tab-buttons">
    <button class="tab-btn active" onclick="switchTab('rising')">🔥 高騰カード</button>
    <button class="tab-btn" onclick="switchTab('falling')">📉 下落カード</button>
    <button class="tab-btn" onclick="switchTab('box')">📦 BOX相場</button>
  </div>
  <div class="tab-content" id="tab-rising">{rising_html}</div>
  <div class="tab-content" id="tab-falling" style="display:none">{falling_html}</div>
  <div class="tab-content" id="tab-box" style="display:none">{box_html}</div>
</div>

<script>
function switchTab(t){{
  document.querySelectorAll('.tab-content').forEach(el=>el.style.display='none');
  document.querySelectorAll('.tab-btn').forEach(el=>el.classList.remove('active'));
  document.getElementById('tab-'+t).style.display='block';
  event.target.classList.add('active');
}}
</script>

<div class="summary">
  <h3>💡 ポケカ相場の見方を学びたい方へ</h3>
  <p>サイトの分析手法・指標の意味について詳しく知りたい方は <a href="../about.html" style="color:#92400e;text-decoration:underline">このサイトについて</a> もあわせてご覧ください。</p>
</div>'''

    # 追加CSS
    extra_css = '''
.latest-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin-bottom:24px}
.latest-card{display:flex;flex-direction:column;align-items:center;padding:20px 16px;border-radius:12px;text-decoration:none;transition:transform .15s,box-shadow .15s}
.latest-card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.1)}
.latest-rising{background:linear-gradient(135deg,#fef2f2,#fff1f2);border:2px solid #fecaca}
.latest-falling{background:linear-gradient(135deg,#eff6ff,#f0f9ff);border:2px solid #bfdbfe}
.latest-box{background:linear-gradient(135deg,#f0fdf4,#ecfdf5);border:2px solid #bbf7d0}
.latest-emoji{font-size:2rem;margin-bottom:8px}
.latest-title{font-size:1rem;font-weight:700;color:#111827;margin-bottom:4px}
.latest-desc{font-size:.8rem;color:#6b7280;text-align:center}
.tab-container{margin-bottom:24px}
.tab-buttons{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.tab-btn{padding:8px 16px;border:2px solid #d1d5db;border-radius:8px;background:#fff;font-size:.85rem;font-weight:600;cursor:pointer;transition:all .15s}
.tab-btn:hover{border-color:#3b82f6;color:#1d4ed8}
.tab-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.tab-content{display:flex;flex-direction:column;gap:4px}
.archive-item{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:8px;text-decoration:none;color:#111827;transition:background .1s}
.archive-item:hover{background:#f3f4f6}
.archive-emoji{font-size:1.1rem}
.archive-title{flex:1;font-size:.9rem;font-weight:600}
.archive-date{font-size:.75rem;color:#6b7280}
@media(max-width:600px){.latest-cards{grid-template-columns:1fr}.tab-buttons{gap:4px}.tab-btn{padding:6px 10px;font-size:.78rem}}
'''

    return render_page(
        title="記事アーカイブ",
        description="ポケカるっくが集計データをもとにレポートする記事アーカイブ。週次の高騰/下落ランキング、未開封BOXトレンドなど。",
        slug="index",
        body_html=body,
        extra_css=extra_css,
    )


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("Step 3 (Articles): 解説記事ページ生成")
    print("=" * 50)

    os.makedirs(ARTICLES_DIR, exist_ok=True)

    print("📂 カードデータ読み込み中...")
    card_cache = load_card_data()
    print(f"   → {len(card_cache):,} 件")

    print("📂 BOXデータ読み込み中...")
    box_cache = load_box_data()
    print(f"   → {len(box_cache):,} 件")

    print("📊 変動データ計算中...")
    card_items = compute_card_movements(card_cache)
    box_items = compute_box_movements(box_cache)
    print(f"   カード: {len(card_items)}件、BOX: {len(box_items)}件")

    print("📝 記事生成中...")

    # 今日の日付でアーカイブファイル名を決定
    today_str = datetime.now(JST).strftime("%Y-%m-%d")

    # 各記事を生成
    articles = [
        ("rising", generate_weekly_rising(card_items)),
        ("falling", generate_weekly_falling(card_items)),
        ("box", generate_box_trends(box_items)),
    ]

    # 既存URL名とアーカイブ名のマッピング
    legacy_names = {
        "rising": "weekly-rising.html",
        "falling": "weekly-falling.html",
        "box": "box-trends.html",
    }

    for article_type, content in articles:
        if content is None:
            print(f"   ⚠️ {article_type}: スキップ（データ不足）")
            continue

        # アーカイブファイル（日付付き）
        archive_name = f"{today_str}-{article_type}.html"
        archive_path = os.path.join(ARTICLES_DIR, archive_name)
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"   ✅ {archive_path} ({len(content):,} bytes)")

        # 既存URL（最新版コピー）
        legacy_path = os.path.join(ARTICLES_DIR, legacy_names[article_type])
        with open(legacy_path, "w", encoding="utf-8") as f:
            f.write(content)

    # 記事一覧（アーカイブ検出して生成）
    index_content = generate_index()
    index_path = os.path.join(ARTICLES_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_content)
    print(f"   ✅ {index_path} ({len(index_content):,} bytes)")

    print("🎉 完了!")


if __name__ == "__main__":
    main()
