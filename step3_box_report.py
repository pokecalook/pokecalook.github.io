"""
Step 3 (BOX版): 未開封BOX相場ページ生成
使い方: python step3_box_report.py

box_price_data.json → box.html
- 定価/現在価格（新品最安出品価格）/プレミア率
- ソート（プレミア率/現在価格/出品数/発売日）
- 検索フィルタ

※ BOX商品はsales-chart API（取引履歴）が利用不可のため、
   出品価格ベースで相場を表示する。
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
import urllib.parse
from common_html import get_header, get_nav, get_footer, get_gtag, get_meta_keywords, get_brand_bar

JST = timezone(timedelta(hours=9))

PRICE_CACHE_FILE = "box_price_data.json"
OUTPUT_HTML = "box.html"


def load_price_cache():
    if not os.path.exists(PRICE_CACHE_FILE):
        print(f"エラー: {PRICE_CACHE_FILE} が見つかりません。先に step2_box_api.py を実行してください。")
        sys.exit(1)
    with open(PRICE_CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_box_data(cache):
    """キャッシュからBOXデータを構築（過去3ヶ月取引あり+現在出品中のみ掲載）"""
    from datetime import datetime as dt_, timedelta as td_
    import statistics

    # 3ヶ月前の日付（JSTベースだが日付だけ使うので問題なし）
    three_mo_ago = (dt_.now() - td_(days=90)).strftime("%Y-%m-%d")

    boxes = []
    for pid, data in cache.items():
        if not data.get("is_box") or data.get("skipped"):
            continue

        name = data.get("name", "")
        msrp = data.get("msrp", 0)
        current = data.get("current_price", 0)
        premium = data.get("premium", 0)
        listing = data.get("listing_count", 0)
        released = data.get("released_at", "")
        prices = data.get("prices", [])
        dates = data.get("dates", [])

        # 現在出品中チェック
        if current <= 0:
            continue

        # 過去3ヶ月の取引のみ抽出
        recent_prices = []
        recent_dates = []
        for d, p in zip(dates, prices):
            if d >= three_mo_ago:
                recent_prices.append(p)
                recent_dates.append(d)

        # 過去3ヶ月に10件未満の取引しかなければ掲載しない（中央値の信頼性担保）
        if len(recent_prices) < 10:
            continue

        # 3ヶ月中央値
        median_3mo = int(statistics.median(recent_prices))

        # 画像パス
        img_path = f"images/box_{pid}.webp"
        if not os.path.exists(img_path):
            img_path = data.get("image_url", "")

        # 日別中央値（チャート用）全期間
        by_date = {}
        for d, p in zip(dates, prices):
            by_date.setdefault(d, []).append(p)
        daily = [[d, int(statistics.median(v))] for d, v in sorted(by_date.items())]

        # 3ヶ月中央値を基準にプレミア率を再計算（現在出品価格ベースではなく取引実勢ベース）
        median_premium = round((median_3mo / msrp - 1) * 100, 1) if msrp > 0 else 0

        # 1ヶ月変動額: 4週前の週間中央値 vs 直近1週間の中央値
        from datetime import datetime as _dt, timedelta as _td
        _now = _dt.now()
        _4w_ago = (_now - _td(days=28)).strftime("%Y-%m-%d")
        _3w_ago = (_now - _td(days=21)).strftime("%Y-%m-%d")
        _1w_ago = (_now - _td(days=7)).strftime("%Y-%m-%d")
        _2w_ago = (_now - _td(days=14)).strftime("%Y-%m-%d")
        _old_prices = [p for d, p in zip(recent_dates, recent_prices) if _4w_ago <= d < _3w_ago]
        _new_prices = [p for d, p in zip(recent_dates, recent_prices) if d >= _1w_ago]
        box_mt = None
        if _old_prices and _new_prices:
            _old_med = statistics.median(_old_prices)
            _new_med = statistics.median(_new_prices)
            box_mt = int(_new_med - _old_med)

        # 1週間変動額: 2週前の週間中央値 vs 直近1週間の中央値
        _2w_prices = [p for d, p in zip(recent_dates, recent_prices) if _2w_ago <= d < _1w_ago]
        box_wt = None
        if _2w_prices and _new_prices:
            _2w_med = statistics.median(_2w_prices)
            _1w_med = statistics.median(_new_prices)
            box_wt = int(_1w_med - _2w_med)

        # 直近7日中央値
        med_7d = int(statistics.median(_new_prices)) if _new_prices else None

        boxes.append({
            "id": pid,
            "n": name,
            "img": img_path,
            "msrp": msrp,
            "cur": current,           # 現在の最安出品価格
            "med": median_3mo,         # 過去3ヶ月取引中央値
            "med7": med_7d,            # 直近7日中央値
            "prem": premium,           # 現在出品価格ベースのプレミア率
            "mprem": median_premium,   # 3ヶ月中央値ベースのプレミア率
            "lc": listing,
            "rel": released,
            "tc": len(recent_prices),
            "wc": len(_new_prices),    # 週間取引個数
            "mt": box_mt,             # 1ヶ月変動額
            "wt": box_wt,             # 1週間変動額
            "chart": daily,
            "u": f"https://snkrdunk.com/apparels/{pid}",
        })

    # プレミア率（現在価格ベース）降順
    boxes.sort(key=lambda x: x["prem"], reverse=True)
    return boxes


def generate_html(boxes):
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    boxes_json = json.dumps(boxes, ensure_ascii=False, separators=(',', ':'))

    # カードサマリーデータ（ID+美品価格）を埋め込む
    import statistics as _stats
    card_summary = []
    try:
        price_cache_file = "price_data_api.json"
        if os.path.exists(price_cache_file):
            with open(price_cache_file, "r", encoding="utf-8") as cf:
                card_cache = json.load(cf)
            for pid, data in card_cache.items():
                if not data.get("is_single_card"):
                    continue
                sold_data = data.get("sold_data", [])
                sold_a = [s["price"] for s in sold_data if s.get("condition") == "A"]
                if not sold_a:
                    continue
                a_med = int(_stats.median(sold_a[-5:]))
                if a_med <= 0:
                    continue
                card_summary.append({"id": pid, "a": a_med})
    except Exception:
        pass
    card_summary_json = json.dumps(card_summary, ensure_ascii=False, separators=(',', ':'))

    html_content = BOX_HTML_TEMPLATE.replace("__BOXES_JSON__", boxes_json)
    html_content = html_content.replace("__CARD_SUMMARY_JSON__", card_summary_json)
    html_content = html_content.replace("__NOW__", now_str)
    html_content = html_content.replace("__TOTAL__", str(len(boxes)))
    html_content = html_content.replace("__GTAG__", get_gtag())
    html_content = html_content.replace("__META_KEYWORDS__", get_meta_keywords())
    html_content = html_content.replace("__HEADER__", get_header())
    html_content = html_content.replace("__NAV__", get_nav(active="box"))
    html_content = html_content.replace("__BOX_FOOTER__", get_footer())

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"box.html 生成完了: {len(boxes)}件")


SITE_URL = "https://pokecalook.com"
BOX_DETAIL_DIR = "box"


def _esc_box(s):
    """HTML属性用エスケープ"""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_box_price(v):
    if not v or v <= 0:
        return "データなし"
    return f"¥{v:,}"


def generate_box_detail_pages(boxes):
    """各BOXの個別HTMLページを box/ ディレクトリに生成"""
    os.makedirs(BOX_DETAIL_DIR, exist_ok=True)
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    for b in boxes:
        pid = b["id"]
        name = b["n"]
        title = f"{_esc_box(name)} 相場・価格推移 | ポケカるっく"
        desc = f"{name} の未開封BOX相場を毎日更新。本日最安 {fmt_box_price(b['cur'])} / 3ヶ月中央値 {fmt_box_price(b['med'])}"

        # トレンド表示
        mt = b.get("mt")
        wt = b.get("wt")
        mt_html = _trend_html(mt, "1ヶ月")
        wt_html = _trend_html(wt, "1週間")

        # Xシェア用テキスト
        med7_text = f"\n直近7日中央値: {fmt_box_price(b.get('med7'))}" if b.get("med7") else ""
        tweet_text = f"{name}{med7_text}\n{SITE_URL}/box/{pid}.html\n#ポケカるっく"

        chart_json = json.dumps(b.get("chart", []), ensure_ascii=False, separators=(',', ':'))

        # 画像パス（詳細ページからの相対パス）
        img_src = f"../images/box_{pid}.webp"
        if not os.path.exists(f"images/box_{pid}.webp"):
            img_src = b.get("img", "")
            if img_src and not img_src.startswith("http"):
                img_src = f"../{img_src}"

        # OGP画像（フルURL）
        og_img = f"{SITE_URL}/images/box_{pid}.webp"
        if not os.path.exists(f"images/box_{pid}.webp"):
            og_img = b.get("img", "")

        html = _BOX_DETAIL_TEMPLATE
        html = html.replace("__GTAG_BOX__", get_gtag())
        html = html.replace("__BOX_DETAIL_BRAND_BAR__", get_brand_bar())
        html = html.replace("__BOX_DETAIL_HEADER__", get_header(prefix="../"))
        html = html.replace("__BOX_DETAIL_NAV__", get_nav(prefix="../", active="box"))
        html = html.replace("__BOX_DETAIL_FOOTER__", get_footer(prefix="../"))
        html = html.replace("__TITLE__", _esc_box(title))
        html = html.replace("__DESC__", _esc_box(desc))
        html = html.replace("__URL__", f"{SITE_URL}/box/{pid}.html")
        html = html.replace("__OG_IMG__", og_img)
        html = html.replace("__BOX_NAME__", _esc_box(name))
        html = html.replace("__IMG__", img_src)
        html = html.replace("__NOW__", now_str)
        html = html.replace("__CUR__", fmt_box_price(b["cur"]))
        html = html.replace("__MED__", fmt_box_price(b["med"]))
        html = html.replace("__MED7__", fmt_box_price(b.get("med7")))
        html = html.replace("__MSRP__", fmt_box_price(b["msrp"]))
        html = html.replace("__MT__", mt_html)
        html = html.replace("__WT__", wt_html)
        html = html.replace("__LC__", str(b["lc"]))
        html = html.replace("__WC__", str(b.get("wc", 0)))
        html = html.replace("__TC__", str(b["tc"]))
        html = html.replace("__REL__", b.get("rel", ""))
        html = html.replace("__CHART_JSON__", chart_json)
        html = html.replace("__SNKR_URL__", b["u"])
        html = html.replace("__MERCARI_URL__", f"https://jp.mercari.com/search?keyword={urllib.parse.quote(name)}")
        html = html.replace("__TWEET_TEXT__", tweet_text)
        html = html.replace("__TWEET_ENC__", urllib.parse.quote(tweet_text))

        filepath = os.path.join(BOX_DETAIL_DIR, f"{pid}.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

    print(f"BOX詳細ページ生成完了: {len(boxes)}件 → {BOX_DETAIL_DIR}/")


def _trend_html(val, label):
    if val is None:
        return f'<span style="color:#6b7280">データなし</span>'
    sign = "+" if val > 0 else "-" if val < 0 else "±"
    abs_v = f"¥{abs(val):,}"
    if val > 3000:
        return f'<span style="color:#0d9488;font-weight:700">🔥 {sign}{abs_v}</span>'
    elif val > 500:
        return f'<span style="color:#0d9488;font-weight:700">📈 {sign}{abs_v}</span>'
    elif val > -500:
        return f'<span style="color:#2563eb;font-weight:700">→ {sign}{abs_v}</span>'
    elif val > -3000:
        return f'<span style="color:#dc2626;font-weight:700">📉 {sign}{abs_v}</span>'
    else:
        return f'<span style="color:#dc2626;font-weight:700">📉 {sign}{abs_v}</span>'


_BOX_DETAIL_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/png" href="../images/logo.png">
<link rel="stylesheet" href="../common.css">
__GTAG_BOX__
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:type" content="website">
<meta property="og:url" content="__URL__">
<meta property="og:image" content="__OG_IMG__">
<meta property="og:site_name" content="ポケカるっく">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="__URL__">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#fffbf0;color:#1a1a2e;padding:16px}
a{color:#3b82f6;text-decoration:none}a:hover{text-decoration:underline}
.back{display:inline-block;margin-bottom:16px;font-size:.85rem;font-weight:600}
h1{font-size:1.3rem;margin-bottom:4px;color:#1a1a2e;font-weight:800;line-height:1.4}
.meta{color:#6b7280;font-size:.8rem;margin-bottom:16px}
.detail{background:#fff;border-radius:14px;border:2px solid #e5e7eb;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.detail-top{display:flex;gap:0}
.img-wrap{flex-shrink:0;width:320px;text-align:center;padding:16px;background:#f9fafb;border-right:2px solid #e5e7eb;display:flex;align-items:center;justify-content:center}
.img-wrap img{max-width:100%;max-height:300px;object-fit:contain;border-radius:8px}
.side{flex:1;padding:20px;min-width:0}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}
.st{text-align:center;background:#f9fafb;border-radius:10px;padding:12px 6px;border:1px solid #e5e7eb}
.st .l{font-size:.75rem;color:#374151;margin-bottom:3px;font-weight:700}
.st .v{font-size:1.2rem;font-weight:800;color:#111827}
.trends{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}
.trend-box{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px;text-align:center}
.trend-box .lbl{font-size:.75rem;color:#374151;font-weight:700}
.trend-box .val{font-size:1rem;margin-top:4px}
.info{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px}
.info-item{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:8px;text-align:center}
.info-item .lbl{font-size:.7rem;color:#6b7280;font-weight:600}
.info-item .val{font-size:.85rem;font-weight:700;color:#111827;margin-top:2px}
.chart-section{padding:20px}
.chart-wrap{background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:12px;height:250px;position:relative}
.sp-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:.8rem;font-weight:600;font-family:inherit}
.sp-btn:hover{border-color:#3b82f6;color:#1d4ed8}
.sp-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.links{display:flex;gap:8px;margin:16px 20px;flex-wrap:wrap}
.links a,.links button{font-size:.8rem;padding:8px 16px;border-radius:8px;text-decoration:none;font-weight:600;border:2px solid #d1d5db;cursor:pointer;font-family:inherit}
.lk-snkr{color:#2563eb;border-color:#93c5fd!important;background:#eff6ff}
.lk-mer{color:#dc2626;border-color:#fca5a5!important;background:#fef2f2}
.lk-tw{color:#111827;border-color:#d1d5db!important;background:#f9fafb}
.lk-top{color:#374151;border-color:#d1d5db!important;background:#fff}
.footer{text-align:center;padding:20px;margin-top:20px;font-size:.75rem;color:#6b7280}
.footer a{color:#3b82f6;text-decoration:none;margin:0 8px}
.main-content{flex:1;min-width:0;max-width:800px;margin:0 auto}
@media(max-width:768px){
  body{padding:8px}
  h1{font-size:1.1rem}
  .detail-top{flex-direction:column}
  .img-wrap{width:100%;border-right:none;border-bottom:2px solid #e5e7eb;padding:12px}
  .img-wrap img{max-height:200px}
  .side{padding:12px}
  .stats{grid-template-columns:1fr 1fr}
  .st .v{font-size:1rem}
  .info{grid-template-columns:1fr 1fr}
  .chart-wrap{height:200px}
  .links{margin:12px;gap:6px}
  .links a,.links button{font-size:.75rem;padding:6px 12px}
}
</style>
</head>
<body>
__BOX_DETAIL_BRAND_BAR__
__BOX_DETAIL_HEADER__
__BOX_DETAIL_NAV__
<a class="back" href="../box.html">← BOX一覧に戻る</a>
<div class="main-content">
<h1>📦 __BOX_NAME__</h1>
<p class="meta">最終更新: __NOW__</p>
<div class="detail">
  <div class="detail-top">
    <div class="img-wrap"><img src="__IMG__" alt="__BOX_NAME__" loading="lazy"></div>
    <div class="side">
      <div class="stats">
        <div class="st"><div class="l">📦 本日最安出品</div><div class="v">__CUR__</div></div>
        <div class="st"><div class="l">📊 3ヶ月中央値</div><div class="v">__MED__</div></div>
        <div class="st"><div class="l">📈 直近7日中央値</div><div class="v">__MED7__</div></div>
        <div class="st"><div class="l">💰 定価</div><div class="v">__MSRP__</div></div>
      </div>
      <div class="trends">
        <div class="trend-box"><div class="lbl">📈 1ヶ月変動額</div><div class="val">__MT__</div></div>
        <div class="trend-box"><div class="lbl">📊 1週間変動額</div><div class="val">__WT__</div></div>
      </div>
      <div class="info">
        <div class="info-item"><div class="lbl">現在の出品数</div><div class="val">__LC__ 件</div></div>
        <div class="info-item"><div class="lbl">週間取引</div><div class="val">__WC__ 個</div></div>
        <div class="info-item"><div class="lbl">3ヶ月取引</div><div class="val">__TC__ 件</div></div>
      </div>
      <div style="font-size:.8rem;color:#6b7280;text-align:center">発売日: __REL__</div>
    </div>
  </div>
  <div class="chart-section">
    <div style="font-size:.85rem;font-weight:700;color:#374151;margin-bottom:8px;text-align:center">📈 価格推移（日別中央値）</div>
    <div class="sp-btns" style="display:flex;gap:6px;justify-content:center;margin-bottom:10px">
      <button class="sp-btn" data-days="30">1ヶ月</button>
      <button class="sp-btn" data-days="90">3ヶ月</button>
      <button class="sp-btn" data-days="180">6ヶ月</button>
      <button class="sp-btn" data-days="365">1年</button>
      <button class="sp-btn active" data-days="0">全期間</button>
    </div>
    <div class="chart-wrap"><canvas id="box-chart"></canvas></div>
  </div>
  <div class="links">
    <a class="lk-snkr" href="__SNKR_URL__" target="_blank">📦 スニダンで見る</a>
    <a class="lk-mer" href="__MERCARI_URL__" target="_blank">🛒 メルカリで探す</a>
    <a class="lk-tw lk-tw-share" href="javascript:void(0)" data-tw="__TWEET_ENC__" style="color:#111827;border-color:#d1d5db;background:#f9fafb">𝕏 共有</a>
    <a class="lk-top" href="../box.html">📋 BOX一覧に戻る</a>
  </div>
</div>
</div><!-- main-content -->
__BOX_DETAIL_FOOTER__
<script>
const CHART_DATA=__CHART_JSON__;
let boxChart=null;
let chartDays=0;

function filterByDays(data,days){
  if(!days||days<=0)return data;
  const cutoff=new Date();cutoff.setDate(cutoff.getDate()-days);
  const cs=cutoff.toISOString().slice(0,10);
  return data.filter(p=>p[0]>=cs);
}

function drawBoxChart(){
  const filtered=filterByDays(CHART_DATA,chartDays);
  if(!filtered||filtered.length<2)return;
  if(boxChart){boxChart.destroy();boxChart=null;}
  const ctx=document.getElementById('box-chart').getContext('2d');
  boxChart=new Chart(ctx,{
    type:'line',
    data:{datasets:[{data:filtered.map(p=>({x:p[0],y:p[1]})),borderColor:'#3b82f6',backgroundColor:'rgba(59,130,246,.08)',fill:true,borderWidth:2,pointRadius:0,tension:.3}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{title:function(items){const d=new Date(items[0].parsed.x);return d.getFullYear()+'/'+(d.getMonth()+1)+'/'+d.getDate()},label:function(c){return '\u00a5'+c.parsed.y.toLocaleString()}}}},scales:{x:{type:'time',time:{unit:filtered.length>60?'month':'week',displayFormats:{week:'M/d',month:'yyyy/M'}},grid:{display:false}},y:{ticks:{callback:v=>'\u00a5'+(v>=10000?(v/10000).toFixed(0)+'\u4e07':v.toLocaleString())},grid:{color:'#f3f4f6'}}},interaction:{intersect:false,mode:'index'}}
  });
}

document.querySelectorAll('.sp-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    chartDays=parseInt(btn.dataset.days);
    document.querySelectorAll('.sp-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    drawBoxChart();
  });
});

if(CHART_DATA&&CHART_DATA.length>=2){drawBoxChart();}
</script>
<script>document.addEventListener('click',function(e){var a=e.target.closest('.lk-tw-share');if(a&&a.dataset.tw){window.open('htt'+'ps://'+['x','com'].join('.')+'/inte'+'nt/tw'+'eet?text='+a.dataset.tw,'_blank');e.preventDefault();}});</script>
</body>
</html>"""


BOX_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
__GTAG__
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
__META_KEYWORDS__
<title>未開封BOX相場一覧 - ポケカるっく</title>
<meta name="description" content="ポケモンカード未開封BOXの相場を毎日更新。現在最安・過去3ヶ月取引中央値を一覧で比較。取引実績ありのBOXのみ掲載。">
<meta name="keywords" content="ポケカ,未開封BOX,相場,取引中央値,ポケモンカード,BOX価格,ポケカるっく">
<meta property="og:title" content="未開封BOX相場一覧 - ポケカるっく">
<meta property="og:description" content="ポケモンカード未開封BOXの相場を毎日更新。現在最安・過去3ヶ月取引中央値を比較。">
<meta property="og:type" content="website">
<meta property="og:url" content="https://pokecalook.com/box.html">
<meta property="og:site_name" content="ポケカるっく">
<link rel="canonical" href="https://pokecalook.com/box.html">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
a{color:#3b82f6;text-decoration:none}a:hover{text-decoration:underline}
.main-content{flex:1;min-width:0;max-width:1000px;margin:0 auto}
.toolbar{display:flex;gap:8px;justify-content:center;align-items:center;flex-wrap:wrap;margin-bottom:16px;padding:10px;background:#fff;border:2px solid #e5e7eb;border-radius:10px}
.sort-select,.search-input{background:#fff;border:2px solid #d1d5db;color:#374151;padding:7px 12px;border-radius:8px;font-size:.85rem;font-weight:600;font-family:inherit}
.sort-select:focus,.search-input:focus{border-color:#3b82f6;outline:none}
.search-input{flex:1;min-width:160px;max-width:300px}
.dir-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;font-family:inherit}
.dir-btn:hover{border-color:#3b82f6;color:#1d4ed8;background:#eff6ff}
.count{font-size:.8rem;color:#6b7280;text-align:center;margin-bottom:12px}
.toolbar-sticky{position:sticky;top:0;z-index:95;background:rgba(255,251,240,.95);backdrop-filter:blur(6px);padding:10px 8px 8px;border-bottom:1px solid #e5e7eb;margin:0 -16px 12px;box-shadow:0 2px 6px rgba(0,0,0,.05)}
.box-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.box-grid-ad{grid-column:1 / -1;text-align:center;padding:12px 0;margin:4px 0}
.box-grid-ad img{max-width:100%;height:auto}
.pager-sticky{position:sticky;bottom:0;background:rgba(255,251,240,.95);backdrop-filter:blur(6px);padding:10px 8px;z-index:90;border-top:1px solid #e5e7eb;box-shadow:0 -2px 8px rgba(0,0,0,.05);margin:20px -16px 0}
.pager{display:flex;gap:6px;justify-content:center;align-items:center;flex-wrap:wrap}
.pager-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:6px 12px;border-radius:8px;font-size:.85rem;font-weight:700;cursor:pointer;min-width:36px;font-family:inherit}
.pager-btn:hover{border-color:#3b82f6;color:#1d4ed8;background:#eff6ff}
.pager-btn.active{background:#ea580c;border-color:#ea580c;color:#fff}
.pager-btn:disabled{opacity:.4;cursor:not-allowed}
.pager-info{font-size:.75rem;color:#6b7280;margin:0 8px;font-weight:600}
.portfolio-bar{background:linear-gradient(135deg,#ecfdf5,#d1fae5);border:2px solid #6ee7b7;border-radius:12px;padding:12px 20px;margin-bottom:16px;display:none;max-width:900px;margin-left:auto;margin-right:auto}
.portfolio-bar.show{display:flex;gap:20px;align-items:center;justify-content:center;flex-wrap:wrap}
.pf-item{text-align:center}
.pf-v{font-size:1.1rem;font-weight:800;color:#065f46}
.pf-l{font-size:.7rem;color:#6b7280;font-weight:600}
.box-card{background:#fff;border:2px solid #e5e7eb;border-radius:14px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.04);transition:transform .15s,box-shadow .15s}
.box-card:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.08)}
.box-img-wrap{height:180px;background:#f9fafb;display:flex;align-items:center;justify-content:center;overflow:hidden;border-bottom:2px solid #e5e7eb}
.box-img{max-width:100%;max-height:100%;object-fit:contain}
.box-body{padding:14px}
.box-name{font-size:.8rem;font-weight:700;color:#1a1a2e;margin-bottom:10px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.2em}
.box-name a{color:#1a1a2e;text-decoration:none}
.box-name a:hover{color:#ea580c;text-decoration:underline}
.box-stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:10px}
.box-st{text-align:center;background:#f9fafb;border-radius:8px;padding:8px 4px;border:1px solid #e5e7eb}
.box-st .l{font-size:.6rem;color:#6b7280;font-weight:600;margin-bottom:2px;white-space:nowrap}
.box-st .v{font-size:.85rem;font-weight:800;color:#111827;white-space:nowrap}
.prem-hot{color:#dc2626!important}
.prem-warm{color:#ea580c!important}
.prem-cool{color:#2563eb!important}
.prem-neg{color:#059669!important}
.box-meta{font-size:.7rem;color:#6b7280;text-align:center;margin-bottom:8px;display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap}
.own-wrap{font-size:.7rem;color:#065f46;font-weight:600}
.own-qty{display:inline-flex;align-items:center;gap:2px;margin-left:4px}
.own-qty button{width:22px;height:22px;border:1.5px solid #6ee7b7;border-radius:6px;background:#ecfdf5;color:#065f46;font-size:.85rem;font-weight:700;cursor:pointer;line-height:1;padding:0}
.own-qty button:hover{background:#d1fae5;border-color:#34d399}
.own-qty span{min-width:18px;text-align:center;font-weight:800;font-size:.8rem;color:#065f46}
.box-meta span{margin:0 6px}
.box-chart-tip{display:none;position:absolute;top:-4px;left:50%;transform:translateX(-50%);background:rgba(17,24,39,.92);color:#fff;font-size:.72rem;font-weight:700;padding:5px 10px;border-radius:6px;white-space:nowrap;z-index:10;pointer-events:none}
.box-chart-tip::after{content:'';position:absolute;bottom:-5px;left:50%;transform:translateX(-50%);border-left:5px solid transparent;border-right:5px solid transparent;border-top:5px solid rgba(17,24,39,.92)}
.box-chart-wrap{height:100px;margin-bottom:8px;position:relative}
.box-link{display:block;text-align:center;font-size:.78rem;padding:7px 4px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;color:#1d4ed8;font-weight:600;transition:background .15s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.box-link:hover{background:#dbeafe;text-decoration:none}
.box-links{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px}
.box-link-mercari{background:#fef2f2;border-color:#fecaca;color:#b91c1c}
.box-link-mercari:hover{background:#fee2e2}
.filter-toggle-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;transition:all .15s;font-family:inherit}
.filter-toggle-btn:hover{border-color:#3b82f6;color:#1d4ed8;background:#eff6ff}
.filter-toggle-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.fav-btn{background:#fff;border:2px solid #fbbf24;color:#d97706;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;transition:all .15s;font-family:inherit}
.fav-btn:hover{border-color:#f59e0b;color:#b45309;background:#fffbeb}
.fav-btn.active{background:#f59e0b;border-color:#f59e0b;color:#fff}
.filter-panel{display:none;max-width:900px;margin:0 auto 12px;padding:12px 16px;background:linear-gradient(135deg,#dbeafe,#eff6ff);border:2px solid #93c5fd;border-radius:10px}
.filter-panel.open{display:block}
.filter-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.filter-row:last-child{margin-bottom:0}
.filter-label{color:#1e40af;font-size:.8rem;margin-right:4px;white-space:nowrap;font-weight:700;min-width:110px}
.filter-select,.filter-input{background:#fff;border:2px solid #d1d5db;color:#374151;padding:6px 10px;border-radius:8px;font-size:.85rem;cursor:pointer;font-weight:600;font-family:inherit;width:110px}
.filter-input{cursor:text}
.filter-select:focus,.filter-input:focus{border-color:#3b82f6;outline:none}
.filter-sep{color:#6b7280;font-weight:700}
.filter-reset{background:#fff;border:2px solid #ef4444;color:#b91c1c;padding:6px 14px;border-radius:8px;font-size:.8rem;font-weight:700;cursor:pointer;font-family:inherit}
.filter-reset:hover{background:#fef2f2}
@media(max-width:768px){
  body{padding:8px}
  .hdr h1{font-size:1.4rem}
  .box-grid{grid-template-columns:1fr 1fr}
  .box-img-wrap{height:120px}
  .box-name{font-size:.7rem}
  .box-st .v{font-size:.75rem}
  .box-st .l{font-size:.55rem}
}
@media(max-width:480px){
  .box-grid{grid-template-columns:1fr}
}</style>
</head>
<body>
__HEADER__
__NAV__

<p style="text-align:center;font-size:.75rem;color:#9ca3af;margin:8px 0 4px">最終更新: __NOW__ JST</p>

<div class="portfolio-bar" id="box-portfolio-bar">
  <div class="pf-item"><div class="pf-v" id="bpf-count">0</div><div class="pf-l">所持BOX</div></div>
  <div class="pf-item"><div class="pf-v" id="bpf-total">¥0</div><div class="pf-l">総合計</div></div>
  <div class="pf-item"><a href="portfolio.html" style="color:#065f46;font-weight:700;font-size:.8rem;text-decoration:none;border:2px solid #6ee7b7;padding:6px 14px;border-radius:8px;background:#fff">📋 リスト管理</a></div>
  <div class="pf-item"><button onclick="if(confirm('持ってるBOXを全て削除しますか？')){var o=loadOwned();Object.keys(o).filter(k=>k.startsWith('box_')).forEach(k=>delete o[k]);saveOwned(o);location.reload()}" style="color:#dc2626;font-weight:700;font-size:.8rem;border:2px solid #fca5a5;padding:6px 14px;border-radius:8px;background:#fff;cursor:pointer">🗑 BOX一括削除</button></div>
</div>

<div class="main-content">
<div class="toolbar-sticky">
<div class="toolbar">
  <select class="sort-select" id="sort-select" onchange="applySort()">
    <option value="tc">取引件数</option>
    <option value="lc">出品数</option>
    <option value="cur">出品価格</option>
    <option value="med">過去3ヶ月中央値</option>
    <option value="mt">1ヶ月変動額</option>
    <option value="wt">週間変動額</option>
  </select>
  <button class="dir-btn" id="dir-btn" onclick="toggleDir()">▼ 降順</button>
  <button class="fav-btn" id="fav-filter" onclick="toggleFavFilter()">☆ お気に入り</button>
  <button class="filter-toggle-btn" id="filter-toggle" onclick="toggleFilter()">フィルタ</button>
  <div style="position:relative;flex:1;min-width:160px;max-width:300px"><input class="search-input" id="search-input" type="text" placeholder="🔍 BOX名で検索..." oninput="applySearch()" style="width:100%;padding-right:30px;max-width:none">
  <button id="search-clear" style="display:none;position:absolute;right:8px;top:50%;transform:translateY(-50%);background:none;border:none;font-size:1.1rem;color:#9ca3af;cursor:pointer" onclick="document.getElementById('search-input').value='';this.style.display='none';applySearch()">✕</button></div>
</div>
<div class="filter-panel" id="filter-panel">
  <div class="filter-row">
    <span class="filter-label">最小取引件数</span>
    <select class="filter-select" id="min-trades" onchange="applyFilter()">
      <option value="0">制限なし</option>
      <option value="3">3件以上</option>
      <option value="5">5件以上</option>
      <option value="10" selected>10件以上</option>
      <option value="20">20件以上</option>
      <option value="50">50件以上</option>
    </select>
  </div>
  <div class="filter-row">
    <span class="filter-label">出品価格</span>
    <input class="filter-input" id="price-cur-min" type="number" placeholder="最小 ¥" min="0" step="100" oninput="applyFilter()">
    <span class="filter-sep">〜</span>
    <input class="filter-input" id="price-cur-max" type="number" placeholder="最大 ¥" min="0" step="100" oninput="applyFilter()">
  </div>
  <div class="filter-row">
    <span class="filter-label">📈 3ヶ月中央値</span>
    <input class="filter-input" id="price-med-min" type="number" placeholder="最小 ¥" min="0" step="100" oninput="applyFilter()">
    <span class="filter-sep">〜</span>
    <input class="filter-input" id="price-med-max" type="number" placeholder="最大 ¥" min="0" step="100" oninput="applyFilter()">
    <button class="filter-reset" onclick="resetFilter()">リセット</button>
  </div>
</div>
</div><!-- toolbar-sticky -->
<div class="count" id="count-display">__TOTAL__件表示中</div>
<div class="box-grid" id="box-grid"></div>
<div class="pager-sticky"><div class="pager" id="pager"></div></div>
</div><!-- main-content -->

<p style="font-size:.72rem;color:#9ca3af;text-align:center;margin:12px 0">※ 過去3ヶ月の取引10件以上のBOXのみ掲載しています（__TOTAL__件）</p>

__BOX_FOOTER__

<script>
const BOXES=__BOXES_JSON__;
const CARD_SUMMARY=__CARD_SUMMARY_JSON__;
const PAGE_SIZE=45;          // 3列×15行
const COLS=3;

const DEFAULTS={sort:'tc',dir:'desc',q:'',page:1,mt:0,cMin:'',cMax:'',mMin:'',mMax:''};

// 持ってる管理（カードと共通localStorage: pokecalook_owned）
function loadOwned(){try{return JSON.parse(localStorage.getItem('pokecalook_owned'))||{}}catch(e){return{}}}
function saveOwned(o){localStorage.setItem('pokecalook_owned',JSON.stringify(o))}
function getBoxOwned(id){return loadOwned()[id]||0}

// お気に入り管理（カードと共通localStorage: pokecalook_favs）
function loadFavs(){try{return new Set(JSON.parse(localStorage.getItem('pokecalook_favs'))||[])}catch(e){return new Set()}}
function saveFavs(s){localStorage.setItem('pokecalook_favs',JSON.stringify([...s]))}
let favSet=loadFavs();
let favOnly=false;
function isFav(id){return favSet.has('box_'+id)}
function toggleBoxFav(btn,id){
  const key='box_'+id;
  if(favSet.has(key)){favSet.delete(key)}else{favSet.add(key)}
  saveFavs(favSet);
  btn.textContent=favSet.has(key)?'★':'☆';
  btn.style.color=favSet.has(key)?'#f59e0b':'#9ca3af';
}
function toggleFavFilter(){
  favOnly=!favOnly;
  const btn=document.getElementById('fav-filter');
  btn.classList.toggle('active',favOnly);
  btn.textContent=favOnly?'★ お気に入り':'☆ お気に入り';
  curPage=1;render();
}
function onBoxOwn(btn,delta){
  const wrap=btn.closest('.own-qty');
  const id=wrap.dataset.oid;
  const owned=loadOwned();
  const qty=Math.max(0,(owned[id]||0)+delta);
  if(qty<=0){delete owned[id]}else{owned[id]=qty}
  saveOwned(owned);
  wrap.querySelector('span').textContent=qty;
  updateBoxPortfolio();
}

function updateBoxPortfolio(){
  const owned=loadOwned();
  const bar=document.getElementById('box-portfolio-bar');
  let boxCount=0,boxTotal=0,cardCount=0,cardTotal=0;
  const cardMap={};CARD_SUMMARY.forEach(c=>{cardMap[c.id]=c});
  Object.keys(owned).forEach(k=>{
    if(k.startsWith('box_')){
      const bid=k.replace('box_','');
      const b=BOXES.find(x=>x.id==bid);
      if(b){boxCount+=owned[k];boxTotal+=owned[k]*(b.cur||b.med||0);}
    }else{
      cardCount+=owned[k];
      if(cardMap[k])cardTotal+=owned[k]*cardMap[k].a;
    }
  });
  const total=boxCount+cardCount;
  if(total>0){bar.classList.add('show')}else{bar.classList.remove('show')}
  document.getElementById('bpf-count').textContent=boxCount+'個'+(cardCount>0?' + カード'+cardCount+'枚':'');
  const grandTotal=boxTotal+cardTotal;
  document.getElementById('bpf-total').textContent='¥'+grandTotal.toLocaleString();
}
let curSort=DEFAULTS.sort,curDir=DEFAULTS.dir,searchQuery=DEFAULTS.q,curPage=DEFAULTS.page;
let minTrades=DEFAULTS.mt;
const charts={};

function fmt(v){return v?'¥'+v.toLocaleString():'—'}
function fmtD(v){if(v==null)return'<span style="color:#6b7280">ー</span>';const s=v>0?'+':v<0?'-':'±';const col=v>0?'#0d9488':v<0?'#dc2626':'#2563eb';return'<span style="color:'+col+';font-weight:700">'+s+'¥'+Math.abs(v).toLocaleString()+'</span>';}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

function getFiltered(){
  let arr=[...BOXES];
  if(favOnly){arr=arr.filter(b=>isFav(b.id));}
  if(searchQuery){
    const toK=s=>s.replace(/[\u3041-\u3096]/g,c=>String.fromCharCode(c.charCodeAt(0)+0x60));
    const q=toK(searchQuery.toLowerCase());
    arr=arr.filter(b=>toK(b.n.toLowerCase()).includes(q));
  }
  if(minTrades>0){arr=arr.filter(b=>(b.tc||0)>=minTrades);}
  const cMin=parseInt(document.getElementById('price-cur-min').value)||0;
  const cMax=parseInt(document.getElementById('price-cur-max').value)||0;
  if(cMin>0)arr=arr.filter(b=>b.cur>=cMin);
  if(cMax>0)arr=arr.filter(b=>b.cur<=cMax);
  const mMin=parseInt(document.getElementById('price-med-min').value)||0;
  const mMax=parseInt(document.getElementById('price-med-max').value)||0;
  if(mMin>0)arr=arr.filter(b=>b.med>=mMin);
  if(mMax>0)arr=arr.filter(b=>b.med<=mMax);

  const dir=curDir==='desc'?1:-1;
  arr.sort((a,b)=>{
    let va,vb;
    switch(curSort){
      case'cur':va=a.cur;vb=b.cur;break;
      case'med':va=a.med;vb=b.med;break;
      case'lc':va=a.lc;vb=b.lc;break;
      case'tc':va=a.tc||0;vb=b.tc||0;break;
      case'mt':va=a.mt!=null?a.mt:-9999;vb=b.mt!=null?b.mt:-9999;break;
      case'wt':va=a.wt!=null?a.wt:-9999;vb=b.wt!=null?b.wt:-9999;break;
      case'n':return dir*(a.n.localeCompare(b.n,'ja'));
      default:va=a.tc||0;vb=b.tc||0;
    }
    return dir*(vb-va);
  });
  return arr;
}

function renderCard(b){
  return `
    <div class="box-card">
      <a href="box/${b.id}.html" class="box-img-wrap" style="text-decoration:none">
        ${b.img?`<img class="box-img" src="${b.img}" alt="${esc(b.n)}" loading="lazy">`:'<div style="color:#9ca3af;font-size:2rem">📦</div>'}
      </a>
      <div class="box-body">
        <div class="box-name"><a href="box/${b.id}.html">${esc(b.n)}</a></div>
        <div class="box-stats">
          <div class="box-st"><div class="l">価格</div><div class="v">${fmt(b.cur)}</div></div>
          <div class="box-st"><div class="l">3ヶ月中央値</div><div class="v">${fmt(b.med)}</div></div>
          <div class="box-st"><div class="l">3ヶ月取引</div><div class="v">${(b.tc||0)>=300?'300件↑':(b.tc||0)+'件'}</div></div>
          <div class="box-st"><div class="l">週間変動額</div><div class="v">${fmtD(b.wt)}</div></div>
          <div class="box-st"><div class="l">1ヶ月変動額</div><div class="v">${fmtD(b.mt)}</div></div>
        </div>
        <div class="box-meta"><span>📋 出品${b.lc}件</span><span class="own-wrap">📥持ってる <span class="own-qty" data-oid="box_${b.id}"><button onclick="onBoxOwn(this,-1)">−</button><span>${getBoxOwned('box_'+b.id)}</span><button onclick="onBoxOwn(this,1)">+</button></span></span><button onclick="toggleBoxFav(this,'${b.id}')" style="background:none;border:none;font-size:1.2rem;cursor:pointer;color:${isFav(b.id)?'#f59e0b':'#9ca3af'}">${isFav(b.id)?'★':'☆'}</button></div>
        ${b.chart&&b.chart.length>=2?`<div class="box-chart-wrap"><div class="box-chart-tip" id="tip-${b.id}"></div><canvas id="chart-${b.id}"></canvas></div>`:''}
        <div class="box-links">
          <a class="box-link box-link-snkr" href="${b.u}" target="_blank" rel="noopener">スニダンで見る</a>
          <a class="box-link box-link-mercari" href="https://jp.mercari.com/search?keyword=${encodeURIComponent(b.n)}" target="_blank" rel="noopener nofollow">メルカリで見る</a>
          <a class="box-link" href="box/${b.id}.html" style="background:#f0fdf4;border-color:#86efac;color:#065f46">📄 詳細</a>
          <a class="box-link lk-tw-share" href="javascript:void(0)" data-tw="${encodeURIComponent(b.n+(b.med7?'\n直近7日中央値: ¥'+b.med7.toLocaleString():'')+'\nhttps://pokecalook.com/box/'+b.id+'.html\n#ポケカるっく')}" style="background:#f9fafb;border-color:#d1d5db;color:#111827">𝕏 共有</a>
        </div>
      </div>
    </div>`;
}

function render(){
  const filtered=getFiltered();
  const totalPages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE));
  if(curPage>totalPages)curPage=totalPages;
  if(curPage<1)curPage=1;

  document.getElementById('count-display').textContent=filtered.length+'件（'+curPage+'/'+totalPages+'ページ）';
  const grid=document.getElementById('box-grid');

  // 既存チャート破棄
  Object.values(charts).forEach(c=>c.destroy());
  for(const k in charts)delete charts[k];

  const start=(curPage-1)*PAGE_SIZE;
  const pageItems=filtered.slice(start,start+PAGE_SIZE);

  // 3列ごとに行を構成
  const parts=[];
  for(let i=0;i<pageItems.length;i++){
    parts.push(renderCard(pageItems[i]));
  }
  grid.innerHTML=parts.join('');

  // チャート描画
  pageItems.forEach(b=>{
    if(!b.chart||b.chart.length<2)return;
    const canvas=document.getElementById('chart-'+b.id);
    if(!canvas)return;
    const ctx=canvas.getContext('2d');
    charts[b.id]=new Chart(ctx,{
      type:'line',
      data:{datasets:[{data:b.chart.map(p=>({x:p[0],y:p[1]})),borderColor:'#3b82f6',backgroundColor:'rgba(59,130,246,.08)',fill:true,borderWidth:1.5,pointRadius:0,tension:.3}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{enabled:false,external:function(context){const tipEl=document.getElementById('tip-'+b.id);if(!tipEl)return;if(context.tooltip.opacity===0){tipEl.style.display='none';return;}const dp=context.tooltip.dataPoints;if(!dp||!dp.length){tipEl.style.display='none';return;}const d=new Date(dp[0].parsed.x);const ds=d.getFullYear()+'/'+(d.getMonth()+1).toString().padStart(2,'0')+'/'+d.getDate().toString().padStart(2,'0');tipEl.innerHTML='<span style="color:#d1d5db;font-size:.65rem">'+ds+'</span> <span style="font-weight:700">\u00a5'+dp[0].parsed.y.toLocaleString()+'</span>';tipEl.style.display='block';const caretX=context.tooltip.caretX;const wrapW=context.chart.canvas.parentElement.offsetWidth;const tipW=tipEl.offsetWidth;let left=caretX;if(left-tipW/2<4)left=tipW/2+4;if(left+tipW/2>wrapW-4)left=wrapW-tipW/2-4;tipEl.style.left=left+'px';tipEl.style.transform='translateX(-50%)';}}},scales:{x:{type:'time',display:false,time:{unit:'day'}},y:{display:true,ticks:{callback:v=>'\u00a5'+(v>=10000?(v/10000).toFixed(0)+'\u4e07':v.toLocaleString()),font:{size:8},maxTicksLimit:3},grid:{color:'#f3f4f6'}}},interaction:{intersect:false,mode:'index'}}
    });
  });

  renderPager(totalPages);
  updateURL();
  updateBoxPortfolio();
}

function renderPager(total){
  const p=document.getElementById('pager');
  if(total<=1){p.innerHTML='';return;}
  const btns=[];
  btns.push(`<button class="pager-btn" onclick="goPage(1)" ${curPage===1?'disabled':''}>«</button>`);
  btns.push(`<button class="pager-btn" onclick="goPage(${curPage-1})" ${curPage===1?'disabled':''}>‹</button>`);
  // 前後2ページまで表示
  const s=Math.max(1,curPage-2),e=Math.min(total,curPage+2);
  if(s>1)btns.push(`<button class="pager-btn" onclick="goPage(1)">1</button>`);
  if(s>2)btns.push('<span class="pager-info">…</span>');
  for(let i=s;i<=e;i++){btns.push(`<button class="pager-btn ${i===curPage?'active':''}" onclick="goPage(${i})">${i}</button>`);}
  if(e<total-1)btns.push('<span class="pager-info">…</span>');
  if(e<total)btns.push(`<button class="pager-btn" onclick="goPage(${total})">${total}</button>`);
  btns.push(`<button class="pager-btn" onclick="goPage(${curPage+1})" ${curPage===total?'disabled':''}>›</button>`);
  btns.push(`<button class="pager-btn" onclick="goPage(${total})" ${curPage===total?'disabled':''}>»</button>`);
  p.innerHTML=btns.join('');
}

function goPage(n){curPage=n;render();window.scrollTo({top:0,behavior:'smooth'});}
function applySort(){curSort=document.getElementById('sort-select').value;curPage=1;render();}
function toggleDir(){curDir=curDir==='desc'?'asc':'desc';document.getElementById('dir-btn').textContent=curDir==='desc'?'▼ 降順':'▲ 昇順';curPage=1;render();}
function applySearch(){searchQuery=document.getElementById('search-input').value.trim();document.getElementById('search-clear').style.display=searchQuery?'block':'none';curPage=1;render();}
function applyFilter(){
  minTrades=parseInt(document.getElementById('min-trades').value)||0;
  curPage=1;render();
  document.getElementById('filter-toggle').classList.toggle('active',isFilterActive());
}
function isFilterActive(){
  return minTrades!==DEFAULTS.mt ||
    document.getElementById('price-cur-min').value!=='' ||
    document.getElementById('price-cur-max').value!=='' ||
    document.getElementById('price-med-min').value!=='' ||
    document.getElementById('price-med-max').value!=='';
}
function toggleFilter(){document.getElementById('filter-panel').classList.toggle('open');}
function resetFilter(){
  document.getElementById('min-trades').value=String(DEFAULTS.mt);
  document.getElementById('price-cur-min').value='';
  document.getElementById('price-cur-max').value='';
  document.getElementById('price-med-min').value='';
  document.getElementById('price-med-max').value='';
  applyFilter();
}

function updateURL(){
  const p=new URLSearchParams();
  if(curSort!==DEFAULTS.sort)p.set('sort',curSort);
  if(curDir!==DEFAULTS.dir)p.set('dir',curDir);
  if(searchQuery!==DEFAULTS.q)p.set('q',searchQuery);
  if(curPage!==DEFAULTS.page)p.set('page',curPage);
  if(minTrades!==DEFAULTS.mt)p.set('mt',minTrades);
  const cMin=document.getElementById('price-cur-min').value;if(cMin)p.set('cMin',cMin);
  const cMax=document.getElementById('price-cur-max').value;if(cMax)p.set('cMax',cMax);
  const mMin=document.getElementById('price-med-min').value;if(mMin)p.set('mMin',mMin);
  const mMax=document.getElementById('price-med-max').value;if(mMax)p.set('mMax',mMax);
  const qs=p.toString();
  history.replaceState(null,'',qs?'?'+qs:location.pathname);
}

// 初期化: URLから状態復元
(function initFromURL(){
  const p=new URLSearchParams(location.search);
  curSort=p.get('sort')||DEFAULTS.sort;
  curDir=p.get('dir')||DEFAULTS.dir;
  searchQuery=p.get('q')||DEFAULTS.q;
  curPage=parseInt(p.get('page'))||DEFAULTS.page;
  minTrades=(p.get('mt')!==null?parseInt(p.get('mt')):DEFAULTS.mt);
  document.getElementById('sort-select').value=curSort;
  document.getElementById('dir-btn').textContent=curDir==='desc'?'▼ 降順':'▲ 昇順';
  document.getElementById('search-input').value=searchQuery;
  document.getElementById('min-trades').value=String(minTrades);
  document.getElementById('price-cur-min').value=p.get('cMin')||'';
  document.getElementById('price-cur-max').value=p.get('cMax')||'';
  document.getElementById('price-med-min').value=p.get('mMin')||'';
  document.getElementById('price-med-max').value=p.get('mMax')||'';
  document.getElementById('filter-toggle').classList.toggle('active',isFilterActive());
})();

render();
</script>
<script>document.addEventListener('click',function(e){var a=e.target.closest('.lk-tw-share');if(a&&a.dataset.tw){window.open('htt'+'ps://'+['x','com'].join('.')+'/inte'+'nt/tw'+'eet?text='+a.dataset.tw,'_blank');e.preventDefault();}});</script>
</body>
</html>"""


if __name__ == "__main__":
    cache = load_price_cache()
    boxes = build_box_data(cache)
    generate_html(boxes)
    generate_box_detail_pages(boxes)
