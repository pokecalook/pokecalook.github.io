"""
Step 5: ポケカ指数（市場全体の相場指標）を計算し、チャート画像とHTMLページを生成。

入力: price_data_api.json
出力:
  - index_history.json        : 日次の美品指数・PSA10指数の履歴
  - index-chart.html          : 指数チャートのWebページ
  - images/index-chart.webp   : Webページ用チャート画像（幅広め）
  - images/tw_index.webp      : X投稿用チャート画像（1.91:1）

指数の定義:
  その日の取引プール方式。各日付 D について、D を含む直近 WINDOW 日間の
  全カードの取引価格を全部集めて中央値を取る。取引件数も日次合計。
"""
import json
import os
import sys
import statistics
import math
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from playwright.sync_api import sync_playwright
from PIL import Image
from common_html import get_header, get_nav, get_footer, get_gtag, get_meta_keywords, get_brand_bar

PRICE_CACHE = "price_data_api.json"
OUTPUT_HISTORY = "index_history.json"
OUTPUT_HTML = "index-chart.html"
OUTPUT_IMG_WEB = "images/index-chart.webp"
OUTPUT_IMG_TW = "images/tw_index.webp"

WINDOW_DAYS = 30       # その日を含む直近30日でプール
SITE_URL = "https://pokecalook.com"
JST = timezone(timedelta(hours=9))


def load_cache():
    with open(PRICE_CACHE, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_daily_indices(cache):
    """投資家向け日次指数を計算する

    フィルタ条件（各日付時点で動的判定）:
      - PSA10の直近7日中央値 >= 50,000円
      - 直近30日の取引件数（美品+PSA10） >= 50件

    各日付Dについて:
      1. D時点で条件を満たすカードを特定
      2. そのカード群のD含む直近WINDOW日の全取引価格プールの中央値を算出

    Returns:
      list of dict: [{"d": "YYYY-MM-DD", "a_idx": int, "a_cnt": int, "p_idx": int, "p_cnt": int, "cards": int}, ...]
    """
    # 全カードの日付別取引データを事前構築
    # card_trades[pid] = {"a": {date: [prices]}, "p": {date: [prices]}}
    card_trades = {}
    for pid, data in cache.items():
        if not data.get("is_single_card"):
            continue
        sold = data.get("sold_data", [])
        if not sold:
            continue
        a_by_date = {}
        p_by_date = {}
        for entry in sold:
            d = entry.get("date", "")
            p = entry.get("price", 0)
            cond = entry.get("condition", "")
            if not d or not p or p <= 0:
                continue
            if cond == "PSA10":
                p_by_date.setdefault(d, []).append(p)
            else:
                a_by_date.setdefault(d, []).append(p)
        if a_by_date or p_by_date:
            card_trades[pid] = {"a": a_by_date, "p": p_by_date}

    if not card_trades:
        return []

    # 全期間の日付リスト
    all_dates = set()
    for ct in card_trades.values():
        all_dates.update(ct["a"].keys())
        all_dates.update(ct["p"].keys())
    start = min(all_dates)
    end = max(all_dates)
    s_dt = datetime.strptime(start, "%Y-%m-%d")
    e_dt = datetime.strptime(end, "%Y-%m-%d")

    dates = []
    cur = s_dt
    while cur <= e_dt:
        dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)

    # 日次指数計算
    results = []
    MIN_PSA10_MED = 50000
    MIN_TRADES_30D = 50

    for di, d in enumerate(dates):
        d_dt = datetime.strptime(d, "%Y-%m-%d")
        # 直近7日・30日の範囲
        d7_start = (d_dt - timedelta(days=6)).strftime("%Y-%m-%d")
        d30_start = (d_dt - timedelta(days=29)).strftime("%Y-%m-%d")
        window_start = (d_dt - timedelta(days=WINDOW_DAYS - 1)).strftime("%Y-%m-%d")

        # 各カードが条件を満たすか判定 + プール構築
        a_pool = []
        p_pool = []
        qualified_cards = 0

        for pid, ct in card_trades.items():
            # PSA10直近7日の取引価格
            p7_prices = []
            for dd, prices in ct["p"].items():
                if d7_start <= dd <= d:
                    p7_prices.extend(prices)

            if not p7_prices:
                continue
            p7_med = statistics.median(p7_prices)
            if p7_med < MIN_PSA10_MED:
                continue

            # 直近30日の取引件数（美品+PSA10）
            trades_30d = 0
            for dd, prices in ct["a"].items():
                if d30_start <= dd <= d:
                    trades_30d += len(prices)
            for dd, prices in ct["p"].items():
                if d30_start <= dd <= d:
                    trades_30d += len(prices)

            if trades_30d < MIN_TRADES_30D:
                continue

            # 条件クリア → WINDOW日分の取引をプールに追加
            qualified_cards += 1
            for dd, prices in ct["a"].items():
                if window_start <= dd <= d:
                    a_pool.extend(prices)
            for dd, prices in ct["p"].items():
                if window_start <= dd <= d:
                    p_pool.extend(prices)

        a_idx = int(statistics.median(a_pool)) if a_pool else 0
        p_idx = int(statistics.median(p_pool)) if p_pool else 0
        a_avg = int(statistics.mean(a_pool)) if a_pool else 0
        p_avg = int(statistics.mean(p_pool)) if p_pool else 0

        # 当日の取引件数
        a_cnt = 0
        p_cnt = 0
        for pid, ct in card_trades.items():
            a_cnt += len(ct["a"].get(d, []))
            p_cnt += len(ct["p"].get(d, []))

        results.append({
            "d": d,
            "a_idx": a_idx,
            "a_cnt": a_cnt,
            "p_idx": p_idx,
            "p_cnt": p_cnt,
            "a_avg": a_avg,
            "p_avg": p_avg,
            "cards": qualified_cards,
        })

        # 進捗表示（100日ごと）
        if di % 100 == 0:
            print(f"  指数計算中... {di}/{len(dates)} ({d}, 対象{qualified_cards}枚)")

    return results


def save_images(history):
    """Playwright で index-chart.html を開き、中央値+平均値の2グラフを1枚に結合して保存。凡例付き。"""
    os.makedirs("images", exist_ok=True)

    html_path = os.path.abspath(OUTPUT_HTML)
    if not os.path.exists(html_path):
        print(f"HTML未生成のため画像スキップ: {OUTPUT_HTML}")
        return

    file_url = f"file://{html_path}"

    # フォントパス（M PLUS Rounded 1c Bold → Noto Sans CJK フォールバック）
    font_path = None
    for p in ["/usr/share/fonts/mplus/MPLUSRounded1c-Bold.ttf",
              "MPLUSRounded1c-Bold.ttf",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
              "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
              "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
              "/usr/share/fonts/noto/NotoSansCJK-Bold.ttc"]:
        if os.path.exists(p):
            font_path = p
            break

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(file_url, wait_until="networkidle")

        # フォント指定
        page.add_style_tag(content="*{font-family:'M PLUS Rounded 1c','Noto Sans CJK JP',-apple-system,sans-serif !important}")

        # --- 中央値チャート（chart1）: 両方・1年 ---
        page.evaluate("""() => {
            curSeries = "both";
            curDays = 365;
            document.querySelectorAll('.sp-btn[data-series]').forEach(b => b.classList.remove('active'));
            const bothBtn = document.querySelector('.sp-btn[data-series="both"]');
            if(bothBtn) bothBtn.classList.add('active');
            drawChart();
        }""")
        page.wait_for_timeout(500)

        chart1_el = page.query_selector("#chart")
        if not chart1_el:
            print("ERROR: #chart 要素が見つかりません")
            browser.close()
            return
        chart1_bytes = chart1_el.screenshot(type="png")

        browser.close()

    # --- Pillowで中央値チャート1枚 + 凡例追加 ---
    from PIL import ImageDraw, ImageFont
    import io

    img1 = Image.open(io.BytesIO(chart1_bytes))

    # フォント読み込み（M PLUS Rounded 1c Bold）
    try:
        font_legend = ImageFont.truetype(font_path, 32) if font_path else ImageFont.load_default()
        font_title = ImageFont.truetype(font_path, 24) if font_path else ImageFont.load_default()
    except Exception:
        font_legend = ImageFont.load_default()
        font_title = ImageFont.load_default()

    if not font_path:
        print("WARNING: 日本語フォントが見つかりません。画像の文字が化ける可能性があります。")
    else:
        print(f"フォント: {font_path}")

    # キャンバスサイズ: 縦長（幅1200, 高さ=タイトル+グラフ+凡例）
    w = 1200
    title_h = 100
    legend_h = 80
    gap = 30
    # グラフ画像をリサイズ（幅1200に合わせる）
    img1 = img1.resize((w, int(img1.height * w / img1.width)), Image.LANCZOS)
    h = title_h + img1.height + gap + legend_h

    canvas = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # タイトル1: 中央値チャート
    y_pos = 0
    # ロゴ挿入
    logo_path = os.path.join("images", "logo.png")
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo_size = 80
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        # タイトル左側に配置（上下中央）
        canvas.paste(logo, (20, y_pos + 10), logo)
    draw.text((110, y_pos + 38), "ポケカ指数｜ポケカるっく", fill=(20, 20, 50), font=font_title)
    y_pos += title_h
    canvas.paste(img1, (0, y_pos))
    y_pos += img1.height + gap

    # 凡例（大きく、はっきり）
    y_pos += 10
    # PSA10 赤丸
    draw.ellipse((40, y_pos + 12, 64, y_pos + 36), fill=(220, 38, 38))
    draw.text((74, y_pos + 8), "PSA10", fill=(20, 20, 50), font=font_legend)
    # 美品 青丸
    draw.ellipse((240, y_pos + 12, 264, y_pos + 36), fill=(59, 130, 246))
    draw.text((274, y_pos + 8), "\u7f8e\u54c1", fill=(20, 20, 50), font=font_legend)
    # 変動帯 黄丸
    draw.ellipse((440, y_pos + 12, 464, y_pos + 36), fill=(251, 191, 36))
    draw.text((474, y_pos + 8), "\u5909\u52d5\u5e2f", fill=(20, 20, 50), font=font_legend)
    # 取引件数 グレー丸
    draw.ellipse((640, y_pos + 12, 664, y_pos + 36), fill=(180, 180, 180))
    draw.text((674, y_pos + 8), "\u53d6\u5f15\u4ef6\u6570", fill=(20, 20, 50), font=font_legend)

    # 保存
    canvas.save(OUTPUT_IMG_WEB, "WEBP", quality=85)
    print(f"Web用画像: {OUTPUT_IMG_WEB} ({canvas.width}x{canvas.height})")

    # X用: 1200x630 (1.91:1) にリサイズ
    tw_w, tw_h = 1200, 630
    tw_img = canvas.resize((tw_w, tw_h), Image.LANCZOS)
    tw_img.save(OUTPUT_IMG_TW, "WEBP", quality=85)
    print(f"X用画像: {OUTPUT_IMG_TW} ({tw_w}x{tw_h})")


def save_history(history):
    # 全期間を保存（Web側でJSで期間切替できるように）
    with open(OUTPUT_HISTORY, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, separators=(",", ":"))
    print(f"指数履歴保存: {OUTPUT_HISTORY} ({len(history)}日分)")


def generate_html(history):
    """指数チャートWebページを生成"""
    now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    latest = history[-1] if history else {"d": "-", "a_idx": 0, "p_idx": 0, "a_avg": 0, "p_avg": 0}
    prev = history[-2] if len(history) >= 2 else latest
    # 前日比
    a_diff = latest["a_idx"] - prev["a_idx"]
    p_diff = latest["p_idx"] - prev["p_idx"]
    a_pct = round(a_diff / prev["a_idx"] * 100, 2) if prev["a_idx"] > 0 else 0
    p_pct = round(p_diff / prev["p_idx"] * 100, 2) if prev["p_idx"] > 0 else 0
    # 平均値の前日比
    a_avg_diff = latest.get("a_avg", 0) - prev.get("a_avg", 0)
    p_avg_diff = latest.get("p_avg", 0) - prev.get("p_avg", 0)
    a_avg_pct = round(a_avg_diff / prev.get("a_avg", 1) * 100, 2) if prev.get("a_avg", 0) > 0 else 0
    p_avg_pct = round(p_avg_diff / prev.get("p_avg", 1) * 100, 2) if prev.get("p_avg", 0) > 0 else 0

    history_json = json.dumps(history, ensure_ascii=False, separators=(",", ":"))
    html = _TEMPLATE
    html = html.replace("__GTAG__", get_gtag())
    html = html.replace("__META_KEYWORDS__", get_meta_keywords())
    html = html.replace("__BRAND_BAR__", get_brand_bar())
    html = html.replace("__HEADER__", get_header())
    html = html.replace("__NAV__", get_nav(active="index"))
    html = html.replace("__FOOTER__", get_footer())
    html = html.replace("__NOW__", now_str)
    html = html.replace("__DATE__", latest["d"])
    html = html.replace("__A_IDX__", f"¥{latest['a_idx']:,}")
    html = html.replace("__A_DIFF__", f"{'+' if a_diff >= 0 else ''}{a_diff:,}円 ({'+' if a_pct >= 0 else ''}{a_pct}%)")
    html = html.replace("__A_CLASS__", "up" if a_diff >= 0 else "down")
    html = html.replace("__P_IDX__", f"¥{latest['p_idx']:,}")
    html = html.replace("__P_DIFF__", f"{'+' if p_diff >= 0 else ''}{p_diff:,}円 ({'+' if p_pct >= 0 else ''}{p_pct}%)")
    html = html.replace("__P_CLASS__", "up" if p_diff >= 0 else "down")
    html = html.replace("__A_AVG__", f"¥{latest.get('a_avg', 0):,}")
    html = html.replace("__A_AVG_DIFF__", f"{'+' if a_avg_diff >= 0 else ''}{a_avg_diff:,}円 ({'+' if a_avg_pct >= 0 else ''}{a_avg_pct}%)")
    html = html.replace("__A_AVG_CLASS__", "up" if a_avg_diff >= 0 else "down")
    html = html.replace("__P_AVG__", f"¥{latest.get('p_avg', 0):,}")
    html = html.replace("__P_AVG_DIFF__", f"{'+' if p_avg_diff >= 0 else ''}{p_avg_diff:,}円 ({'+' if p_avg_pct >= 0 else ''}{p_avg_pct}%)")
    html = html.replace("__P_AVG_CLASS__", "up" if p_avg_diff >= 0 else "down")
    html = html.replace("__HISTORY_JSON__", history_json)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML生成: {OUTPUT_HTML}")


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
__GTAG__
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
__META_KEYWORDS__
<title>ポケカ指数チャート - ポケカるっく</title>
<meta name="description" content="ポケモンカード市場全体の相場を日次指数で可視化。美品指数・PSA10指数の推移、取引件数を毎日更新。">
<style>
.main-content{flex:1;min-width:0;max-width:900px;margin:0 auto}
.back{display:inline-block;margin-bottom:16px;color:#3b82f6;text-decoration:none;font-size:.9rem;font-weight:600}
.back:hover{text-decoration:underline}
.meta{color:#6b7280;font-size:.8rem;margin-bottom:20px;text-align:center}
.summary{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
.sm{background:#fff;border:2px solid #e5e7eb;border-radius:14px;padding:16px 20px;box-shadow:0 2px 8px rgba(0,0,0,.05)}
.sm h2{font-size:1rem;color:#1e40af;margin-bottom:10px;font-weight:800}
.sm .v{font-size:1.8rem;font-weight:800;color:#1a1a2e}
.sm .d{font-size:.95rem;font-weight:700;margin-top:4px}
.sm .d.up{color:#059669}
.sm .d.down{color:#dc2626}
.chart-wrap{background:#fff;border:2px solid #e5e7eb;border-radius:14px;padding:16px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.05);position:relative}
.chart-wrap h2{font-size:1rem;color:#1e40af;margin-bottom:12px;font-weight:800}
.chart-wrap canvas{width:100%;height:380px;display:block;touch-action:none}
.tooltip{position:absolute;background:rgba(17,24,39,.95);color:#fff;font-size:.75rem;padding:6px 10px;border-radius:6px;pointer-events:none;display:none;white-space:nowrap;z-index:10;line-height:1.5}
.tooltip .d{color:#9ca3af;font-size:.7rem}
.tooltip .v-a{color:#60a5fa;font-weight:700}
.tooltip .v-p{color:#fca5a5;font-weight:700}
.tooltip .v-c{color:#d1d5db;font-size:.7rem}
.sp-btns{display:flex;gap:6px;justify-content:center;margin:12px 0 8px;flex-wrap:wrap}
.sp-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:5px 14px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;font-family:inherit}
.sp-btn:hover{border-color:#3b82f6;color:#1d4ed8}
.sp-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.series-btns{display:flex;gap:6px;justify-content:center;margin-bottom:10px;flex-wrap:wrap}
.legend{display:flex;gap:14px;justify-content:center;margin-top:8px;font-size:.8rem;color:#374151;font-weight:600;flex-wrap:wrap}
.ldot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:5px;vertical-align:middle}
.explain{background:#eff6ff;border:2px solid #93c5fd;border-radius:10px;padding:14px 18px;margin:16px 0;font-size:.85rem;color:#1e40af}
.explain h3{font-size:.95rem;margin-bottom:6px}
@media(max-width:768px){
  body{padding:8px}
  .hdr h1{font-size:1.2rem}
  .summary{grid-template-columns:1fr;gap:10px}
  .sm .v{font-size:1.3rem}
  .chart-wrap canvas{height:300px}
}
</style>
</head>
<body>

__BRAND_BAR__
__HEADER__
__NAV__

<div class="main-content">

<div class="meta">最終更新: __NOW__ ｜ 指数日付: __DATE__</div>

<div class="summary">
  <div class="sm">
    <h2>💎 美品指数（中央値）</h2>
    <div class="v">__A_IDX__</div>
    <div class="d __A_CLASS__">前日比 __A_DIFF__</div>
  </div>
  <div class="sm">
    <h2>🏆 PSA10指数（中央値）</h2>
    <div class="v">__P_IDX__</div>
    <div class="d __P_CLASS__">前日比 __P_DIFF__</div>
  </div>
</div>

<div class="chart-wrap">
  <h2>📈 中央値チャート</h2>
  <div class="series-btns">
    <button class="sp-btn active" data-series="p">PSA10</button>
    <button class="sp-btn" data-series="a">美品</button>
    <button class="sp-btn" data-series="both">両方</button>
  </div>
  <div class="sp-btns">
    <button class="sp-btn" data-days="90">3ヶ月</button>
    <button class="sp-btn" data-days="180">6ヶ月</button>
    <button class="sp-btn active" data-days="365">1年</button>
    <button class="sp-btn" data-days="0">全期間</button>
  </div>
  <canvas id="chart"></canvas>
  <div class="tooltip" id="tt"></div>
  <div class="legend">
    <span><span class="ldot" style="background:#dc2626"></span>指数（直近30日中央値）</span>
    <span><span class="ldot" style="background:#fbbf24;opacity:.6"></span>価格変動帯</span>
    <span><span class="ldot" style="background:#d1d5db"></span>日次取引件数</span>
  </div>
</div>

<div class="explain">
  <h3>📖 指数とは？</h3>
  <p>ポケカるっく独自の市場指標です。PSA10価格5万円以上かつ直近30日で50件以上取引のある高流動カード（約100〜150枚）の取引価格を集計し、中央値を算出しています。ポケカ投資家が実際に売買する価格帯の動きを1つの数字で把握できます。</p>
  <h3 style="margin-top:10px">🎯 なぜ「中央値」を採用しているか</h3>
  <p>ポケカ価格は1枚¥1,000〜¥1,000万超まで幅があり、一部の高額カードが平均値を極端に歪めてしまいます。中央値は外れ値や誤入力の影響を受けにくく、市場の「真ん中の体感温度」を表すため実態に近い指標になります。不動産価格や所得統計でも標準的に使われる手法です。</p>
</div>

</div><!-- main-content -->
__FOOTER__

<script>
const HIST=__HISTORY_JSON__;
let curDays=365;
let curSeries="p";
let chartMeta=null; // {data, PL, PT, pw, ph, vmin, vmax, xFn, seriesKeys}

// Zoom & Pan state
let zoomLevel=1;    // 1 = fit all, >1 = zoomed in
let panOffset=0;    // 0〜1 range (0=left edge, 1=right edge)
const ZOOM_MIN=1;
const ZOOM_MAX=10;
const ZOOM_STEP=1.2;
let isDragging=false;
let dragStartX=0;
let dragStartPan=0;

function filterByDays(data,days){
  if(!days||days<=0) return data.filter(h=>(h.cards||0)>=30);
  const cutoff=new Date();
  cutoff.setDate(cutoff.getDate()-days);
  const cs=cutoff.toISOString().slice(0,10);
  return data.filter(h=>h.d>=cs&&(h.cards||0)>=30);
}

function resetZoom(){
  zoomLevel=1;
  panOffset=0;
}

function getVisibleRange(dataLen){
  // Returns [startIdx, endIdx] (inclusive) based on zoom/pan
  const visibleFraction=1/zoomLevel;
  const maxPan=1-visibleFraction;
  const clampedPan=Math.max(0,Math.min(maxPan,panOffset));
  const startIdx=Math.floor(clampedPan*(dataLen-1));
  const endIdx=Math.min(dataLen-1,Math.floor((clampedPan+visibleFraction)*(dataLen-1)));
  return [startIdx,endIdx];
}

function drawChart(){
  const canvas=document.getElementById('chart');
  const ctx=canvas.getContext('2d');
  const dpr=window.devicePixelRatio||1;
  const rect=canvas.getBoundingClientRect();
  canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;
  ctx.scale(dpr,dpr);
  const W=rect.width,H=rect.height;

  const allData=filterByDays(HIST,curDays);
  if(!allData.length) return;

  // Visible range based on zoom/pan
  const [visStart,visEnd]=getVisibleRange(allData.length);
  const data=allData.slice(visStart,visEnd+1);
  if(!data.length) return;

  const seriesKeys=curSeries==="both"?["a","p"]:[curSeries];
  const colors={a:"#3b82f6",p:"#dc2626"};

  // 値範囲（上下1%外れ値トリム）
  const allValues=[];
  for(const s of seriesKeys){
    for(const h of data){
      if(h[s+"_idx"]>0) allValues.push(h[s+"_idx"]);
    }
  }
  if(!allValues.length) return;
  const sorted=[...allValues].sort((a,b)=>a-b);
  const trimN=Math.max(1,Math.floor(sorted.length*0.01));
  const trimmed=sorted.slice(trimN,sorted.length-trimN);
  if(!trimmed.length) return;
  let vmin=trimmed[0]*0.95;
  let vmax=trimmed[trimmed.length-1]*1.05;

  // 取引件数最大
  let cmax=0;
  for(const s of seriesKeys){
    for(const h of data){
      if(h[s+"_cnt"]>cmax) cmax=h[s+"_cnt"];
    }
  }
  cmax=Math.max(cmax,1);

  const PL=55,PR=20,PT=20,PB=40;
  const pw=W-PL-PR,ph=H-PT-PB;

  function x(i){return PL+(i/Math.max(data.length-1,1))*pw}
  function y(v){return PT+ph-((v-vmin)/(vmax-vmin))*ph}
  function yCnt(c){return PT+ph-(c/cmax)*ph*0.3}

  // 背景
  ctx.fillStyle="#fff";ctx.fillRect(0,0,W,H);

  // グリッド
  ctx.strokeStyle="#e5e7eb";ctx.lineWidth=1;ctx.font="11px sans-serif";ctx.fillStyle="#6b7280";
  const steps=5;
  for(let i=0;i<=steps;i++){
    const gy=PT+(i/steps)*ph;
    ctx.beginPath();ctx.moveTo(PL,gy);ctx.lineTo(PL+pw,gy);ctx.stroke();
    const gv=vmax-(vmax-vmin)*i/steps;
    ctx.fillText(gv>=1000?Math.round(gv/1000)+"k":Math.round(gv),4,gy+4);
  }

  // 取引件数バー（1系列のみ表示、両方のときはp優先）
  const cntSeries=seriesKeys.includes("p")?"p":seriesKeys[0];
  ctx.fillStyle="#d1d5db";
  const bw=Math.max(pw/data.length*0.8,1);
  for(let i=0;i<data.length;i++){
    const c=data[i][cntSeries+"_cnt"];
    if(c>0){
      const bx=x(i),by=yCnt(c);
      ctx.fillRect(bx-bw/2,by,bw,PT+ph-by);
    }
  }

  // ボリンジャーバンド（20日移動平均±2σ）— vmin/vmaxでクリップ
  const bbColors={a:"rgba(147,197,253,.25)",p:"rgba(251,191,36,.25)"};
  const bbLine={a:"#93c5fd",p:"#fbbf24"};
  for(const s of seriesKeys){
    const vals=data.map(h=>h[s+"_idx"]);
    const period=20,sigma=2;
    const upperPts=[];
    const lowerPts=[];
    for(let i=period-1;i<vals.length;i++){
      const slice=vals.slice(i-period+1,i+1).filter(v=>v>0);
      if(slice.length<2) continue;
      const m=slice.reduce((a,b)=>a+b,0)/slice.length;
      const v=slice.reduce((a,b)=>a+(b-m)*(b-m),0)/slice.length;
      const sd=Math.sqrt(v);
      const u=Math.min(m+sigma*sd,vmax);
      const l=Math.max(m-sigma*sd,vmin);
      upperPts.push({i:i,v:u});
      lowerPts.push({i:i,v:l});
    }
    if(!upperPts.length) continue;
    ctx.fillStyle=bbColors[s];
    ctx.beginPath();
    ctx.moveTo(x(upperPts[0].i),y(upperPts[0].v));
    for(let k=1;k<upperPts.length;k++) ctx.lineTo(x(upperPts[k].i),y(upperPts[k].v));
    for(let k=lowerPts.length-1;k>=0;k--) ctx.lineTo(x(lowerPts[k].i),y(lowerPts[k].v));
    ctx.closePath();ctx.fill();
  }

  // 各系列の本体線
  for(const s of seriesKeys){
    const vals=data.map(h=>h[s+"_idx"]);
    ctx.strokeStyle=colors[s];ctx.lineWidth=2;ctx.beginPath();
    let started=false;
    for(let i=0;i<data.length;i++){
      if(vals[i]>0){
        if(!started){ctx.moveTo(x(i),y(vals[i]));started=true}
        else ctx.lineTo(x(i),y(vals[i]));
      }
    }
    ctx.stroke();
  }

  // 軸
  ctx.strokeStyle="#374151";ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(PL,PT);ctx.lineTo(PL,PT+ph);ctx.lineTo(PL+pw,PT+ph);ctx.stroke();

  // X軸ラベル（期間に応じて間引き: 全期間=3ヶ月ごと, 1年=毎月, 6ヶ月=毎月, 3ヶ月=2週ごと）
  // zoom時はデータ日数に応じて動的に間隔調整
  ctx.fillStyle="#6b7280";ctx.font="11px sans-serif";
  let prevLabel=null;
  const visibleDays=data.length;
  for(let i=0;i<data.length;i++){
    const dd=data[i].d;
    const mo=dd.slice(0,7);
    const day=parseInt(dd.slice(8,10));
    const month=parseInt(dd.slice(5,7));
    let label=null;
    let showTick=false;

    if(visibleDays<=100){
      // ~3ヶ月相当: 2週ごと（1日と15日）
      if(day===1||day===15){
        label=parseInt(dd.slice(5,7))+"/"+day;
        if(day===1&&month===1) label=dd.slice(0,4)+"/"+label;
        showTick=true;
      }
    } else if(visibleDays<=200){
      // ~6ヶ月相当: 毎月1日
      if(day===1){
        label=month+"月";
        if(month===1) label=dd.slice(0,4)+"/"+label;
        showTick=true;
      }
    } else if(visibleDays<=400){
      // ~1年相当: 毎月1日
      if(day===1){
        label=month+"月";
        if(month===1) label=dd.slice(0,4)+"/"+label;
        showTick=true;
      }
    } else {
      // 全期間: 3ヶ月ごと（1月,4月,7月,10月の1日）
      if(day===1&&(month===1||month===4||month===7||month===10)){
        label=dd.slice(0,4)+"/"+month+"月";
        showTick=true;
      }
    }

    if(showTick&&label&&label!==prevLabel){
      const gx=x(i);
      ctx.beginPath();ctx.moveTo(gx,PT+ph);ctx.lineTo(gx,PT+ph+4);ctx.stroke();
      ctx.fillText(label,gx-14,PT+ph+18);
      prevLabel=label;
    }
  }

  // Zoom indicator
  if(zoomLevel>1){
    ctx.fillStyle="rgba(59,130,246,.7)";ctx.font="bold 11px sans-serif";
    ctx.fillText("🔍 "+Math.round(zoomLevel*100)+"%  (ホイールでzoom / ドラッグでスクロール)",PL+4,PT+14);
  }

  // ツールチップ用のメタ情報を保存
  chartMeta={data:data,allData:allData,PL:PL,PT:PT,pw:pw,ph:ph,W:W,H:H,seriesKeys:seriesKeys};
}

function hideTooltip(){
  const tt=document.getElementById('tt');
  tt.style.display='none';
}

function showTooltipAt(clientX,clientY){
  if(!chartMeta) return;
  const canvas=document.getElementById('chart');
  const rect=canvas.getBoundingClientRect();
  const px=clientX-rect.left;
  const {data,PL,PT,pw,ph,seriesKeys}=chartMeta;
  if(px<PL||px>PL+pw) {hideTooltip();return}
  // 最寄りのデータインデックスを求める
  const rel=(px-PL)/Math.max(pw,1);
  let i=Math.round(rel*(data.length-1));
  if(i<0) i=0; if(i>=data.length) i=data.length-1;
  const h=data[i];
  const tt=document.getElementById('tt');
  let html=`<div class="d">${h.d}</div>`;
  if(seriesKeys.includes("a")){
    html+=`<div>💎 美品 <span class="v-a">¥${h.a_idx.toLocaleString()}</span> <span class="v-c">(${h.a_cnt}件)</span></div>`;
  }
  if(seriesKeys.includes("p")){
    html+=`<div>🏆 PSA10 <span class="v-p">¥${h.p_idx.toLocaleString()}</span> <span class="v-c">(${h.p_cnt}件)</span></div>`;
  }
  tt.innerHTML=html;
  tt.style.display='block';
  // 表示位置はchart-wrap基準で計算
  const wrap=canvas.parentElement;
  const wrapRect=wrap.getBoundingClientRect();
  const ttW=tt.offsetWidth;
  const ttH=tt.offsetHeight;
  let left=clientX-wrapRect.left+12;
  let top=clientY-wrapRect.top-ttH-8;
  // はみ出し防止
  if(left+ttW>wrapRect.width-8) left=clientX-wrapRect.left-ttW-12;
  if(top<8) top=clientY-wrapRect.top+16;
  tt.style.left=left+'px';
  tt.style.top=top+'px';
}

document.querySelectorAll('.sp-btn[data-days]').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.sp-btn[data-days]').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    curDays=parseInt(btn.dataset.days);
    resetZoom();
    drawChart();
  });
});
document.querySelectorAll('.sp-btn[data-series]').forEach(btn=>{
  btn.addEventListener('click',()=>{
    document.querySelectorAll('.sp-btn[data-series]').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    curSeries=btn.dataset.series;
    drawChart();
  });
});

drawChart();
window.addEventListener('resize',drawChart);

// ツールチップ: PC(マウス) / スマホ(タッチ)
const canvas=document.getElementById('chart');

// Wheel zoom
canvas.addEventListener('wheel',(e)=>{
  e.preventDefault();
  const rect=canvas.getBoundingClientRect();
  const mouseX=(e.clientX-rect.left)/rect.width; // 0〜1 position

  const oldZoom=zoomLevel;
  if(e.deltaY<0){
    zoomLevel=Math.min(ZOOM_MAX,zoomLevel*ZOOM_STEP);
  } else {
    zoomLevel=Math.max(ZOOM_MIN,zoomLevel/ZOOM_STEP);
  }

  // Adjust pan to keep mouse position stable
  const oldVisible=1/oldZoom;
  const newVisible=1/zoomLevel;
  const oldLeft=panOffset;
  const mouseData=oldLeft+mouseX*oldVisible;
  panOffset=mouseData-mouseX*newVisible;

  // Clamp pan
  const maxPan=1-newVisible;
  panOffset=Math.max(0,Math.min(maxPan,panOffset));

  drawChart();
},{passive:false});

// Drag pan
canvas.addEventListener('mousedown',(e)=>{
  if(zoomLevel<=1) return;
  isDragging=true;
  dragStartX=e.clientX;
  dragStartPan=panOffset;
  canvas.style.cursor='grabbing';
});
window.addEventListener('mousemove',(e)=>{
  if(!isDragging) return;
  const rect=canvas.getBoundingClientRect();
  const dx=e.clientX-dragStartX;
  const dataDx=-dx/rect.width*(1/zoomLevel);
  panOffset=dragStartPan+dataDx;
  const maxPan=1-1/zoomLevel;
  panOffset=Math.max(0,Math.min(maxPan,panOffset));
  drawChart();
});
window.addEventListener('mouseup',()=>{
  if(isDragging){
    isDragging=false;
    canvas.style.cursor='';
  }
});

// Touch pan (2-finger or single drag when zoomed)
let touchStartX=0;
let touchStartPan=0;
canvas.addEventListener('touchstart',(e)=>{
  if(zoomLevel>1&&e.touches.length===1){
    touchStartX=e.touches[0].clientX;
    touchStartPan=panOffset;
  }
  if(e.touches.length===1&&zoomLevel<=1){
    showTooltipAt(e.touches[0].clientX,e.touches[0].clientY);
  }
},{passive:true});
canvas.addEventListener('touchmove',(e)=>{
  if(zoomLevel>1&&e.touches.length===1){
    const rect=canvas.getBoundingClientRect();
    const dx=e.touches[0].clientX-touchStartX;
    const dataDx=-dx/rect.width*(1/zoomLevel);
    panOffset=touchStartPan+dataDx;
    const maxPan=1-1/zoomLevel;
    panOffset=Math.max(0,Math.min(maxPan,panOffset));
    drawChart();
  } else if(zoomLevel<=1&&e.touches.length===1){
    showTooltipAt(e.touches[0].clientX,e.touches[0].clientY);
  }
},{passive:true});
canvas.addEventListener('touchend',()=>setTimeout(hideTooltip,2000));

// Tooltip on mousemove (only when not dragging)
canvas.addEventListener('mousemove',(e)=>{
  if(!isDragging) showTooltipAt(e.clientX,e.clientY);
});
canvas.addEventListener('mouseleave',hideTooltip);

// Double-click to reset zoom
canvas.addEventListener('dblclick',()=>{
  resetZoom();
  drawChart();
});


</script>
</body>
</html>
"""


def main():
    if not os.path.exists(PRICE_CACHE):
        print(f"エラー: {PRICE_CACHE} が見つかりません")
        sys.exit(1)

    print("データ読み込み中...")
    cache = load_cache()
    print(f"カード数: {len(cache)}")

    print("日次指数計算中...")
    history = compute_daily_indices(cache)
    print(f"期間: {history[0]['d']} 〜 {history[-1]['d']} ({len(history)}日)")
    print(f"最新 美品指数: {history[-1]['a_idx']:,}円 / PSA10指数: {history[-1]['p_idx']:,}円")

    save_history(history)
    generate_html(history)
    save_images(history)
    print("完了")


if __name__ == "__main__":
    main()
