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
import statistics
from datetime import datetime, timedelta

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
        a_prices = data.get("a_prices", [])
        a_dates = data.get("a_dates", [])
        p_prices = data.get("psa10_prices", [])
        p_dates = data.get("psa10_dates", [])
        if not a_prices:
            continue

        a_med = statistics.median(a_prices[-5:])
        p_med = statistics.median(p_prices[-5:]) if p_prices else 0
        if a_med <= 0:
            continue
        ratio = round(p_med / a_med, 2) if p_med > 0 else 0

        # weekly medians
        def wk(dates, prices, w):
            s = (now - timedelta(days=7*w)).strftime("%Y-%m-%d")
            e = (now - timedelta(days=7*(w-1))).strftime("%Y-%m-%d")
            wp = [p for d, p in zip(dates, prices) if s <= d < e]
            return int(statistics.median(wp)) if wp else None

        a_wk = [wk(a_dates, a_prices, w) for w in range(4, 0, -1)]
        p_wk = [wk(p_dates, p_prices, w) for w in range(4, 0, -1)]

        # trend
        p1w = [p for d, p in zip(p_dates, p_prices) if d >= one_week_ago]
        p2w = [p for d, p in zip(p_dates, p_prices) if two_weeks_ago <= d < one_week_ago]
        trend = None
        if p1w and p2w:
            mn, mp = statistics.median(p1w), statistics.median(p2w)
            if mp > 0:
                trend = round((mn - mp) / mp * 100, 1)

        # sparkline (全期間 daily median — JS側で期間切り替え)
        def spark(dates, prices):
            by_d = {}
            for d, p in zip(dates, prices):
                by_d.setdefault(d, []).append(p)
            return [[d, int(statistics.median(v))] for d, v in sorted(by_d.items())]

        # お買い得スコア: 倍率 × 取引量の対数 (取引が活発で倍率が高いカードが上位)
        volume = min(len(a_prices), len(p_prices))
        score = round(ratio * math.log2(max(volume, 1) + 1), 1)

        cards.append({
            "id": pid,
            "n": data.get("name", pid),
            "en": data.get("en_name", ""),
            "yr": data.get("release_year", ""),
            "img": data.get("image_url", ""),
            "a": int(a_med),
            "p": int(p_med),
            "r": ratio,
            "d": int(p_med - a_med),
            "ac": len(a_prices),
            "pc": len(p_prices),
            "t": trend,
            "sc": score,
            "aw": a_wk,
            "pw": p_wk,
            "as": spark(a_dates, a_prices),
            "ps": spark(p_dates, p_prices),
            "af": a_dates[0] if a_dates else "",
            "al": a_dates[-1] if a_dates else "",
            "pf": p_dates[0] if p_dates else "",
            "pl": p_dates[-1] if p_dates else "",
            "u": f"https://snkrdunk.com/apparels/{pid}",
            "gc": name_to_pokeca_chart_url(data.get("name", "")),
        })

    cards.sort(key=lambda x: x["r"], reverse=True)
    if top > 0:
        cards = cards[:top]
    return cards


def generate_html(cards):
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    cards_json = json.dumps(cards, ensure_ascii=False, separators=(',', ':'))
    hot_count = len([c for c in cards if c["r"] >= 4])
    fire_count = len([c for c in cards if c.get("t") is not None and c["t"] > 20])
    max_ratio = max((c["r"] for c in cards), default=0)

    html = _HTML_TEMPLATE.replace("__CARDS_JSON__", cards_json)
    html = html.replace("__NOW__", now_str)
    html = html.replace("__TOTAL__", str(len(cards)))
    html = html.replace("__HOT__", str(hot_count))
    html = html.replace("__FIRE__", str(fire_count))
    html = html.replace("__MAX_RATIO__", f"{max_ratio:.1f}")

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTMLレポート生成完了: {OUTPUT_HTML}")
    print(f"対象カード: {len(cards)}枚 / 倍率4x↑: {hot_count}枚 / 🔥高騰: {fire_count}枚")



_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ポケカるっく - ポケカ PSA10 vs 美品 相場比較</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#fffbf0;color:#1a1a2e;padding:16px}
.hdr{text-align:center;margin-bottom:20px;padding:20px 16px}
.hdr h1{font-size:2rem;margin-bottom:6px;background:linear-gradient(135deg,#ef4444,#f59e0b,#3b82f6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;font-weight:900}
.hdr .sub{color:#6b7280;font-size:.85rem;font-weight:500}
.desc{color:#555;font-size:.8rem;margin-top:12px;line-height:1.6;max-width:700px;margin-left:auto;margin-right:auto;background:#fff;padding:12px 16px;border-radius:10px;border:1px solid #e5e7eb}
.desc a{color:#d97706;text-decoration:none;font-weight:600}
.desc a:hover{text-decoration:underline}
.sum{display:flex;gap:12px;justify-content:center;margin-bottom:18px;flex-wrap:wrap}
.sc{background:linear-gradient(135deg,#fef3c7,#fde68a);border-radius:12px;padding:12px 22px;text-align:center;border:2px solid #f59e0b;box-shadow:0 2px 8px rgba(245,158,11,.15)}
.sc .n{font-size:1.5rem;font-weight:800;color:#92400e}
.sc .l{font-size:.75rem;color:#78350f;margin-top:2px;font-weight:600}
.toolbar{display:flex;gap:10px;justify-content:center;align-items:center;margin-bottom:18px;flex-wrap:wrap}
.sort-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:7px 16px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;transition:all .15s}
.sort-btn:hover{border-color:#3b82f6;color:#1d4ed8;background:#eff6ff}
.sort-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.sort-btn .arrow{margin-left:4px;font-size:.7rem}
.tip{font-size:.9rem;color:#3b82f6;cursor:pointer;padding:2px;border-radius:4px;transition:background .15s;display:inline-block}
.tip:hover{background:#dbeafe}
#tooltip-popup{position:absolute;background:#1e293b;color:#fff;padding:10px 14px;border-radius:8px;font-size:.85rem;max-width:320px;line-height:1.6;z-index:1000;display:none;box-shadow:0 4px 12px rgba(0,0,0,.2);pointer-events:none}
#tooltip-popup::after{content:'';position:absolute;top:-6px;left:50%;transform:translateX(-50%);border-left:6px solid transparent;border-right:6px solid transparent;border-bottom:6px solid #1e293b}
.filter-select{background:#fff;border:2px solid #d1d5db;color:#374151;padding:6px 10px;border-radius:8px;font-size:.85rem;cursor:pointer;font-weight:600}
.filter-select:focus{border-color:#3b82f6;outline:none}
.filter-bar{display:flex;gap:20px;justify-content:center;align-items:center;margin-bottom:16px;flex-wrap:wrap;padding:12px 18px;background:linear-gradient(135deg,#dbeafe,#eff6ff);border:2px solid #93c5fd;border-radius:12px;max-width:900px;margin-left:auto;margin-right:auto}
.filter-group{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.filter-label{color:#1e40af;font-size:.8rem;margin-right:4px;white-space:nowrap;font-weight:700}
.pager{display:flex;gap:6px;align-items:center;margin:20px auto;justify-content:center}
.pg-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:6px 14px;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600}
.pg-btn:hover{border-color:#3b82f6;color:#1d4ed8}
.pg-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.pg-btn:disabled{opacity:.3;cursor:default}
.pg-info{color:#6b7280;font-size:.85rem;margin:0 8px;font-weight:600}
.cards{display:flex;flex-direction:column;gap:16px;max-width:1400px;margin:0 auto}
.card{background:#fff;border-radius:14px;overflow:hidden;border:2px solid #e5e7eb;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.card-h{display:flex;align-items:center;gap:10px;padding:12px 16px;background:#fafafa;border-bottom:2px solid #e5e7eb}
.card-rk{font-size:1.1rem;font-weight:800;color:#6b7280;min-width:36px}
.card-nm{flex:1;font-size:.9rem;color:#1a1a2e;font-weight:600}
.card-nm a{color:#1a1a2e;text-decoration:none}
.card-nm a:hover{text-decoration:underline;color:#dc2626}
.card-links{display:flex;gap:6px;margin-top:4px}
.card-links a{font-size:.7rem;padding:3px 8px;border-radius:6px;text-decoration:none;border:1px solid #d1d5db;font-weight:600}
.card-links a.lk-snkr{color:#2563eb;border-color:#93c5fd;background:#eff6ff}
.card-links a.lk-snkr:hover{background:#dbeafe}
.card-links a.lk-gem,.card-links button.lk-gem{color:#b45309;border-color:#fcd34d;background:#fefce8;cursor:pointer;font-family:inherit;font-weight:600;font-size:.7rem;padding:3px 8px;border-radius:6px}
.card-links a.lk-gem:hover,.card-links button.lk-gem:hover{background:#fef3c7}
.card-links button.lk-copy{color:#059669;border:1px solid #a7f3d0;background:#ecfdf5;cursor:pointer;font-family:inherit;font-weight:600;font-size:.7rem;padding:3px 8px;border-radius:6px}
.card-links button.lk-copy:hover{background:#d1fae5}
.card-links button.lk-copy.copied{background:#d1fae5;color:#047857}
.card-links a.lk-gem-link{color:#b45309;border-color:#fcd34d;background:#fefce8;font-weight:600;font-size:.7rem;padding:3px 8px;border-radius:6px}
.card-links a.lk-gem-link:hover{background:#fef3c7}
.cp-hint{font-size:.55rem;opacity:0;transition:opacity .3s;margin-left:4px}
.cp-done .cp-hint{opacity:.8}
.cp-done{background:#fef3c7 !important}
.card-tr{flex-shrink:0}
.card-b{display:flex;gap:0;padding:0}
.card-img-wrap{flex-shrink:0;width:350px;display:flex;align-items:center;justify-content:center;background:#f9fafb;padding:8px;border-right:2px solid #e5e7eb}
.card-img{width:100%;border-radius:6px;object-fit:cover;aspect-ratio:3/4}
.card-data{flex:1;min-width:0;padding:16px}
.stats{display:flex;gap:16px;margin-bottom:14px}
.st{flex:1;text-align:center;background:#f9fafb;border-radius:10px;padding:8px 4px;border:1px solid #e5e7eb}
.st-l{font-size:.8rem;color:#374151;letter-spacing:.3px;margin-bottom:4px;font-weight:700}
.st-v{font-size:1.5rem;font-weight:800;color:#111827}
.st-p{color:#d97706}
.st-s{font-size:.8rem;color:#4b5563;margin-top:3px;font-weight:600}
.r-hot{color:#dc2626}.r-warm{color:#ea580c}.r-cool{color:#2563eb}
.spark-wrap{margin:10px 0;background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;padding:8px;min-height:110px}
.trade-period{font-size:.7rem;color:#4b5563;text-align:center;margin-bottom:8px;padding:4px 8px;background:#f9fafb;border-radius:6px;border:1px solid #e5e7eb}
.spark-wrap canvas{width:100%;height:110px;display:block}
.wk-row{display:flex;gap:16px;margin-top:10px}
.wk-sec{flex:1}
.wk-t{font-size:.75rem;color:#374151;margin-bottom:6px;text-align:center;font-weight:700}
.wb-c{display:flex;justify-content:center;align-items:flex-end;gap:5px;height:60px}
.wb-col{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;flex:1}
.wb{width:100%;max-width:36px;border-radius:4px 4px 0 0}
.wb-v{font-size:.7rem;color:#374151;margin-top:3px;white-space:nowrap;font-weight:600}
.wb-l{font-size:.65rem;color:#6b7280;font-weight:600}
.badge{display:inline-block;padding:3px 10px;border-radius:16px;font-size:.78rem;font-weight:700}
.b-r{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}.b-o{background:#fff7ed;color:#ea580c;border:1px solid #fed7aa}
.b-b{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}.b-t{background:#f0fdfa;color:#0d9488;border:1px solid #99f6e4}
.b-g{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}.b-x{background:#f3f4f6;color:#6b7280;border:1px solid #d1d5db}
.trend-label{font-size:.6rem;color:#4b5563;vertical-align:middle}
.search-box{position:relative;width:100%;max-width:600px}
.search-box input{width:100%;background:#fff;border:2px solid #d1d5db;color:#111827;padding:10px 70px 10px 14px;border-radius:10px;font-size:.95rem;outline:none;transition:border-color .15s;font-weight:500}
.search-box input:focus{border-color:#3b82f6}
.search-box input::placeholder{color:#6b7280}
.search-count{position:absolute;right:36px;top:50%;transform:translateY(-50%);font-size:.78rem;color:#6b7280;font-weight:600}
.search-clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);background:none;border:none;color:#6b7280;cursor:pointer;font-size:1rem;padding:4px}
.search-clear:hover{color:#111827}
.no-results{text-align:center;padding:40px;color:#6b7280;font-size:.95rem}
.legend{display:flex;gap:14px;justify-content:center;margin-bottom:14px;font-size:.9rem;color:#374151;font-weight:600}
.ldot{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:5px;vertical-align:middle}
.sp-btn{background:#fff;border:2px solid #d1d5db;color:#374151;padding:3px 10px;border-radius:6px;cursor:pointer;font-size:.78rem;margin-left:3px;font-weight:600}
.sp-btn:hover{border-color:#3b82f6;color:#1d4ed8}
.sp-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
@media(max-width:768px){
  body{padding:8px}
  .hdr h1{font-size:1.3rem;background:none;-webkit-text-fill-color:#dc2626;color:#dc2626}
  .hdr .sub{font-size:.7rem}
  .desc{font-size:.7rem;padding:10px 12px}
  .sum{gap:6px}
  .sc{padding:6px 10px}
  .sc .n{font-size:1rem}
  .sc .l{font-size:.6rem}
  .toolbar{flex-wrap:wrap;justify-content:center;gap:6px;padding-bottom:6px}
  .sort-btn{font-size:.7rem;padding:5px 10px;flex-shrink:0}
  .sort-help{gap:6px}
  .sort-help .tip{font-size:.75rem}
  .search-box{max-width:100%}
  .search-box input{font-size:.85rem;padding:8px 60px 8px 12px}
  .cards{gap:10px}
  .card-h{flex-direction:column;gap:6px;padding:10px 12px}
  .card-rk{font-size:.85rem}
  .card-nm{font-size:.8rem;word-break:normal;overflow-wrap:break-word}
  .card-links{flex-wrap:wrap;gap:4px}
  .card-links a,.card-links button{font-size:.65rem;padding:3px 8px}
  .card-tr{align-self:flex-start}
  .trend-label{font-size:.5rem}
  .card-b{flex-direction:column;padding:0}
  .card-img-wrap{width:100%;padding:12px;border-right:none;border-bottom:1px solid #e2e8f0}
  .card-img{width:70%;max-width:300px;margin:0 auto;display:block}
  .card-data{padding:10px}
  .stats{gap:6px;flex-wrap:wrap}
  .st{flex:1 1 45%;min-width:0;padding:6px 2px}
  .st-v{font-size:.9rem}
  .st-l{font-size:.5rem}
  .st-s{font-size:.5rem}
  .trade-period{font-size:.55rem}
  .spark-wrap{min-height:80px}
  .spark-wrap canvas{height:80px}
  .wk-row{flex-direction:column;gap:10px}
  .wk-t{font-size:.65rem}
  .wb-c{height:70px;margin-top:4px}
  .wb-v{font-size:.5rem}
  .wb-l{font-size:.5rem}
  .filter-bar{flex-direction:column;gap:8px;padding:8px 10px}
  .filter-group{justify-content:center;flex-wrap:wrap}
  .filter-label{font-size:.7rem}
  .sp-btn{font-size:.65rem;padding:3px 8px}
  .filter-select{font-size:.75rem}
  .pager{flex-wrap:wrap;gap:4px}
  .pg-btn{padding:4px 8px;font-size:.7rem}
  .pg-info{font-size:.65rem}
}
</style>
</head>
<body>
<div class="hdr">
  <h1>🃏 ポケカるっく</h1>
  <div class="sub">最終更新日: __NOW__ ｜ __TOTAL__件（美品の取引があるカードのみ表示）</div>
  <div class="desc">美品をPSA10にしたら何倍になる？がひと目でわかるサイトです！<br>ポケカの相場チェックにもお使いください。<br>📋コピーボタンで検索テキストをコピー → 🔗GemRateボタンで<a href="https://www.gemrate.com/search" target="_blank">GemRate</a>を開く → 貼り付けるだけでPSA鑑定率が確認できます！</div>
</div>
<div class="sum">
  <div class="sc"><div class="n">__TOTAL__</div><div class="l">対象カード</div></div>
  <div class="sc" title="PSA10÷美品の倍率が4倍以上のカード数"><div class="n">__HOT__枚</div><div class="l">倍率4x以上</div></div>
  <div class="sc" title="直近1週間でPSA10価格が20%以上上昇したカード数"><div class="n">__FIRE__枚</div><div class="l">🔥 高騰中</div></div>
  <div class="sc" title="全カード中で最も高いPSA10÷美品の倍率"><div class="n">__MAX_RATIO__x</div><div class="l">最大倍率</div></div>
</div>
<div class="toolbar">
  <div class="search-box">
    <input type="text" id="search" placeholder="🔍 ポケモン名・カード名で検索..." autocomplete="off">
    <span id="search-count" class="search-count"></span>
    <button id="search-clear" class="search-clear" style="display:none">✕</button>
  </div>
</div>
<div class="toolbar">
  <span style="color:#374151;font-size:.85rem;font-weight:700">ソート<span class="tip" data-txt="【倍率】PSA10÷美品の倍率が高い順｜【美品】美品の価格が高い順｜【PSA10】PSA10の価格が高い順｜【トレンド】直近1週間でPSA10価格が上がった順｜【差額】PSA10と美品の差額が大きい順｜【注目度】倍率×取引量が大きい順" style="margin-left:4px">ⓘ</span>:</span>
  <button class="sort-btn active" data-key="r" data-dir="desc">倍率<span class="arrow">▼</span></button>
  <button class="sort-btn" data-key="a" data-dir="desc">美品<span class="arrow">▼</span></button>
  <button class="sort-btn" data-key="p" data-dir="desc">PSA10<span class="arrow">▼</span></button>
  <button class="sort-btn" data-key="t" data-dir="desc">トレンド<span class="arrow">▼</span></button>
  <button class="sort-btn" data-key="d" data-dir="desc">差額<span class="arrow">▼</span></button>
  <button class="sort-btn" data-key="sc" data-dir="desc">注目度<span class="arrow">▼</span></button>
</div>
</div>
<div class="filter-bar">
  <div class="filter-group">
    <span class="filter-label">📅 期間</span>
    <button class="sp-btn" data-days="30">1ヶ月</button>
    <button class="sp-btn active" data-days="90">3ヶ月</button>
    <button class="sp-btn" data-days="180">6ヶ月</button>
    <button class="sp-btn" data-days="365">1年</button>
    <button class="sp-btn" data-days="0">全期間</button>
  </div>
  <div class="filter-group">
    <span class="filter-label">📊 期間内の取引件数（美品・PSA10ともに）</span>
    <select id="min-trades" class="filter-select">
      <option value="0">全件</option>
      <option value="10">10件以上</option>
      <option value="20">20件以上</option>
      <option value="30">30件以上</option>
      <option value="40">40件以上</option>
      <option value="50">50件以上</option>
      <option value="100">100件以上</option>
      <option value="200">200件以上</option>
    </select>
  </div>
</div>
<div class="pager" id="pager-top"></div>
<div class="cards" id="cards"></div>
<div class="pager" id="pager-bottom"></div>
<div id="tooltip-popup"></div>

<script>
const ALL=__CARDS_JSON__;
const PER=50;
let filtered=[...ALL];
let sorted=[...ALL];
let curPage=1;
let curKey='r',curDir='desc';
let searchQuery='';
let minTrades=0;

function tBadge(t){
  if(t==null)return'<span class="badge b-x">データなし</span> <span class="trend-label">PSA10価格の週間変動率</span>';
  if(t>20)return`<span class="badge b-r">🔥 +${t.toFixed(0)}%</span> <span class="trend-label">PSA10価格の週間変動率</span>`;
  if(t>5)return`<span class="badge b-o">📈 +${t.toFixed(0)}%</span> <span class="trend-label">PSA10価格の週間変動率</span>`;
  if(t>-5)return`<span class="badge b-b">→ ${t>=0?'+':''}${t.toFixed(0)}%</span> <span class="trend-label">PSA10価格の週間変動率</span>`;
  if(t>-20)return`<span class="badge b-t">📉 ${t.toFixed(0)}%</span> <span class="trend-label">PSA10価格の週間変動率</span>`;
  return`<span class="badge b-g">⬇ ${t.toFixed(0)}%</span> <span class="trend-label">PSA10価格の週間変動率</span>`;
}
function fmt(v){return v==null?'-':'¥'+v.toLocaleString()}
function wkBars(wk,color){
  const valid=wk.filter(v=>v!=null);
  if(!valid.length)return'<span style="color:#475569;font-size:.75rem">-</span>';
  const mx=Math.max(...valid)||1;
  const labels=['4週前','3週前','2週前','1週前'];
  return'<div class="wb-c">'+wk.map((v,i)=>{
    if(v==null)return`<div class="wb-col"><div class="wb" style="height:2px;background:#e2e8f0"></div><div class="wb-v">-</div><div class="wb-l">${labels[i]}</div></div>`;
    const h=Math.max(4,Math.round(v/mx*36));
    return`<div class="wb-col"><div class="wb" style="height:${h}px;background:${color}"></div><div class="wb-v">${fmt(v)}</div><div class="wb-l">${labels[i]}</div></div>`;
  }).join('')+'</div>';
}
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
    return`<div class="card" data-pid="${c.id}">
      <div class="card-h">
        <div class="card-rk">#${rank}</div>
        <div class="card-nm">
          ${escH(c.n)}
          <div class="card-links">
            <a class="lk-snkr" href="${c.u}" target="_blank">📦 スニダン</a>
            ${c.en?`<button class="lk-copy" data-en="${escH(c.en)}" data-yr="${c.yr||''}">📋 GemRate検索用コピー</button><a class="lk-gem-link" href="https://www.gemrate.com/search" target="_blank">🔗 GemRate</a>`:''}
          </div>
        </div>
        <div class="card-tr">${tBadge(c.t)}</div>
      </div>
      <div class="card-b">
        ${c.img?`<div class="card-img-wrap"><img class="card-img" src="${c.img}" alt="" loading="lazy"></div>`:''}
        <div class="card-data">
        <div class="stats">
          <div class="st"><div class="st-l">💎 美品（直近5件の中央値）</div><div class="st-v">${fmt(c.a)}</div><div class="st-s">過去の全取引 ${c.ac}件</div></div>
          <div class="st"><div class="st-l">🏆 PSA10（直近5件の中央値）</div><div class="st-v st-p">${fmt(c.p)}</div><div class="st-s">過去の全取引 ${c.pc}件</div></div>
          <div class="st"><div class="st-l">⚡ 倍率</div><div class="st-v ${rc}">${c.r.toFixed(1)}x</div><div class="st-s">PSA10との差額 ${fmt(c.d)}</div></div>
          <div class="st"><div class="st-l">⭐ 注目度（倍率×取引量）</div><div class="st-v" style="color:#a78bfa">${c.sc}</div><div class="st-s">計${c.ac+c.pc}件の取引</div></div>
        </div>
        <div class="trade-period">📅 美品: ${c.af||'ー'} 〜 ${c.al||'ー'} ｜ PSA10: ${c.pf||'ー'} 〜 ${c.pl||'ー'}</div>
        <div class="spark-wrap"><canvas data-spark="${c.id}" width="400" height="100"></canvas></div>
        <div class="wk-row">
          <div class="wk-sec"><div class="wk-t">美品 最近4週の値段</div>${wkBars(c.aw,'#3b82f6')}</div>
          <div class="wk-sec"><div class="wk-t">PSA10 最近4週の値段</div>${wkBars(c.pw,'#ef4444')}</div>
        </div>
        </div>
      </div>
    </div>`;
  }).join('');
  renderPagers();
  setupObserver();
  // GemRateコピーボタンのイベント登録
  document.querySelectorAll('.lk-copy[data-en]').forEach(btn=>{
    btn.addEventListener('click',function(e){
      copyGemRate(this,this.dataset.en,this.dataset.yr||'');
    });
  });
  window.scrollTo({top:0,behavior:'smooth'});
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
let sparkDays=90;

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
  function x(ds){const t0=new Date(minD),t1=new Date(maxD),t=new Date(ds);return pad.l+(t1-t0>0?(t-t0)/(t1-t0)*cw:cw/2)}
  function y(v){return pad.t+ch-(maxV>minV?(v-minV)/(maxV-minV)*ch:ch/2)}
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
    data.forEach((p,i)=>{const px=x(p[0]),py=y(p[1]);i===0?ctx.moveTo(px,py):ctx.lineTo(px,py)});
    ctx.stroke();
    ctx.globalAlpha=.07;
    ctx.lineTo(x(data[data.length-1][0]),pad.t+ch);
    ctx.lineTo(x(data[0][0]),pad.t+ch);
    ctx.closePath();ctx.fillStyle=color;ctx.fill();ctx.globalAlpha=1;
    const last=data[data.length-1];
    ctx.beginPath();ctx.arc(x(last[0]),y(last[1]),3,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();
  }
  line(aD,'#3b82f6');line(pD,'#ef4444');
}

// Sort
function applySort(){
  sorted=[...filtered].sort((a,b)=>{
    let va=a[curKey],vb=b[curKey];
    if(va==null)va=-9999;if(vb==null)vb=-9999;
    return curDir==='desc'?vb-va:va-vb;
  });
}

document.querySelectorAll('.sort-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const key=btn.dataset.key;
    let dir=btn.dataset.dir;
    if(key===curKey){dir=dir==='desc'?'asc':'desc';btn.dataset.dir=dir}
    else{dir='desc';btn.dataset.dir='desc'}
    curKey=key;curDir=dir;
    document.querySelectorAll('.sort-btn').forEach(b=>{
      b.classList.remove('active');
      b.querySelector('.arrow').textContent=b.dataset.dir==='desc'?'▼':'▲';
    });
    btn.classList.add('active');
    btn.querySelector('.arrow').textContent=dir==='desc'?'▼':'▲';
    applySort();
    curPage=1;
    renderPage();
  });
});

// Search
const searchInput=document.getElementById('search');
const searchCount=document.getElementById('search-count');
const searchClear=document.getElementById('search-clear');
let searchTimer=null;

function applySearch(){
  const q=searchQuery.toLowerCase().trim();
  if(!q){
    filtered=[...ALL];
  }else{
    const terms=q.split(/\s+/).filter(t=>t);
    filtered=ALL.filter(c=>{
      const name=c.n.toLowerCase();
      return terms.every(t=>name.includes(t));
    });
  }
  // 取引件数フィルタ（選択中のチャート期間内の件数で判定）
  if(minTrades>0){
    filtered=filtered.filter(c=>{
      const d=sparkCache[c.id];
      if(!d)return false;
      const aInPeriod=filterByDays(d.a,sparkDays).length;
      const pInPeriod=filterByDays(d.p,sparkDays).length;
      return Math.min(aInPeriod,pInPeriod)>=minTrades;
    });
  }
  if(q){
    searchCount.textContent=`${filtered.length}件`;
    searchClear.style.display='block';
  }else{
    searchCount.textContent=minTrades>0?`${filtered.length}件`:'';
    searchClear.style.display='none';
  }
  applySort();
  curPage=1;
  renderPage();
}

searchInput.addEventListener('input',()=>{
  searchQuery=searchInput.value;
  // デバウンス（150ms）
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

// Trades filter
document.getElementById('min-trades').addEventListener('change',function(){
  minTrades=parseInt(this.value);
  applySearch();
});

// Sparkline period toggle
document.querySelectorAll('.sp-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    sparkDays=parseInt(btn.dataset.days);
    document.querySelectorAll('.sp-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    // 期間変更時にフィルタも再適用
    applySearch();
    // Redraw all visible sparklines
    document.querySelectorAll('canvas[data-spark]').forEach(cv=>{
      cv.dataset.drawn='';
      const pid=cv.dataset.spark;
      if(pid)drawSpark(cv,pid);
      cv.dataset.drawn='1';
    });
  });
});

// GemRate copy helper
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

  // file:// でも動くコピー方式
  const ta=document.createElement('textarea');
  ta.value=text;
  ta.style.cssText='position:fixed;left:-9999px;top:-9999px';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);

  el.classList.add('copied');
  el.textContent='✅ コピー済';
  setTimeout(()=>{el.classList.remove('copied');el.textContent='📋 GemRate検索用コピー';},2000);
}

// Custom tooltip (click or hover)
const tooltipEl=document.getElementById('tooltip-popup');
function showTooltip(el,text){
  tooltipEl.textContent=text;
  tooltipEl.style.display='block';
  const rect=el.getBoundingClientRect();
  const ttRect=tooltipEl.getBoundingClientRect();
  const top=rect.bottom+window.scrollY+10;
  let left=rect.left+window.scrollX+rect.width/2-ttRect.width/2;
  if(left<10)left=10;
  if(left+ttRect.width>window.innerWidth-10)left=window.innerWidth-ttRect.width-10;
  tooltipEl.style.top=top+'px';
  tooltipEl.style.left=left+'px';
}
function hideTooltip(){tooltipEl.style.display='none';}
document.querySelectorAll('.tip[data-txt]').forEach(el=>{
  el.addEventListener('mouseenter',()=>showTooltip(el,el.dataset.txt));
  el.addEventListener('mouseleave',hideTooltip);
  el.addEventListener('click',(e)=>{
    e.stopPropagation();
    if(tooltipEl.style.display==='block'&&tooltipEl.textContent===el.dataset.txt){
      hideTooltip();
    }else{
      showTooltip(el,el.dataset.txt);
    }
  });
});
document.addEventListener('click',hideTooltip);

// Init
renderPage();
</script>
</body>
</html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTMLレポート生成")
    parser.add_argument("--top", type=int, default=0, help="上位N件のみ (0=全件)")
    args = parser.parse_args()

    cache = load_price_cache()
    cards = build_card_data(cache, args.top)
    generate_html(cards)
