"""
Step 4b: Playwrightでページスクショを撮影
- カード詳細ページ / BOX詳細ページ / 指数チャートページ
- step4_tweet.pyが選定したカード/BOXのIDを受け取り、スクショを保存
- ブランドバー「ポケカるっく | pokecalook.com」をJS挿入してから撮影
- 本番サイト(pokecalook.com)からスクショを撮る
"""
import json, os, sys
from playwright.sync_api import sync_playwright

SITE_URL = "https://pokecalook.com"
IMG_DIR = "images"
POSTED_FILE = "posted_tweets.json"


def hide_chrome(page):
    """ヘッダー・広告・ナビ・フッター・ポップアップを非表示 + ブランドバー挿入"""
    page.evaluate("""() => {
        document.querySelectorAll('.hdr, header, .promo-banner, [class*="promo"], [class*="ad-banner"], .nav-buttons, nav, .back, a.back, .common-footer, footer, [class*="popup"], [class*="modal"], [class*="overlay"]').forEach(el => el.style.display = 'none');
        document.body.style.paddingTop = '0';
        document.body.style.marginTop = '0';
        // ブランドバーを.main-contentの先頭に挿入
        const mc = document.querySelector('.main-content');
        if (mc && !mc.querySelector('.brand-bar')) {
            const bar = document.createElement('div');
            bar.className = 'brand-bar';
            bar.style.cssText = 'background:#1e40af;color:#fff;text-align:center;padding:8px 0;font-size:14px;font-weight:600;letter-spacing:0.5px;margin-bottom:12px;border-radius:6px;';
            bar.textContent = 'ポケカるっく | pokecalook.com';
            mc.insertBefore(bar, mc.firstChild);
        }
    }""")


def take_card_screenshot(page, card_id, output_path):
    """カード詳細ページのスクショ"""
    url = f"{SITE_URL}/cards/{card_id}.html"
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2500)
    hide_chrome(page)
    # h1タイトル、更新日付、ボタン行、h2以降を非表示
    page.evaluate("""() => {
        document.querySelectorAll('h1, .meta, p.meta').forEach(el => el.style.display = 'none');
        const allLinks = document.querySelectorAll('a, button');
        allLinks.forEach(el => {
            const t = el.textContent.trim();
            if (t.includes('スニダン') || t.includes('メルカリ') || t.includes('カードラッシュ') || t.includes('共有') || t.includes('一覧に戻る') || t.includes('PSA10鑑定率')) {
                const parent = el.closest('.btn-row, .buttons, .action-buttons, .cta-buttons, .card-actions');
                if (parent) { parent.style.display = 'none'; }
                else { el.style.display = 'none'; }
            }
        });
        document.querySelectorAll('h2').forEach(h2 => {
            let el = h2;
            while (el) { el.style.display = 'none'; el = el.nextElementSibling; }
        });
    }""")
    page.wait_for_timeout(300)
    el = page.query_selector(".main-content")
    if el:
        el.screenshot(path=output_path, type="jpeg", quality=90)
        print(f"  カードスクショ保存: {output_path}")
        return True
    print(f"  カード .main-content が見つかりません")
    return False


def take_box_screenshot(page, box_id, output_path):
    """BOX詳細ページのスクショ"""
    url = f"{SITE_URL}/box/{box_id}.html"
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2500)
    hide_chrome(page)
    # h1タイトル、更新日付、ボタン行を非表示
    page.evaluate("""() => {
        document.querySelectorAll('h1, .meta, p.meta').forEach(el => el.style.display = 'none');
        const allLinks = document.querySelectorAll('a, button');
        allLinks.forEach(el => {
            const t = el.textContent.trim();
            if (t.includes('スニダン') || t.includes('メルカリ') || t.includes('共有') || t.includes('BOX一覧に戻る') || t.includes('一覧に戻る')) {
                const parent = el.closest('.btn-row, .buttons, .action-buttons, .cta-buttons');
                if (parent) { parent.style.display = 'none'; }
                else { el.style.display = 'none'; }
            }
        });
    }""")
    page.wait_for_timeout(300)
    el = page.query_selector(".main-content")
    if el:
        el.screenshot(path=output_path, type="jpeg", quality=90)
        print(f"  BOXスクショ保存: {output_path}")
        return True
    print(f"  BOX .main-content が見つかりません")
    return False


def take_index_screenshot(page, output_path):
    """指数チャートページのスクショ"""
    url = f"{SITE_URL}/index-chart.html"
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2500)
    hide_chrome(page)
    # 「両方」ボタンをクリック
    page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.textContent.trim() === '両方') { btn.click(); break; }
        }
    }""")
    page.wait_for_timeout(1000)
    # 「1年」ボタンをクリック
    page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.textContent.trim() === '1年') { btn.click(); break; }
        }
    }""")
    page.wait_for_timeout(2000)
    # 「指数とは？」以下を非表示
    page.evaluate("""() => {
        const allEls = document.querySelectorAll('.main-content > *');
        let hide = false;
        allEls.forEach(el => {
            if (el.textContent && el.textContent.includes('指数とは')) hide = true;
            if (hide) el.style.display = 'none';
        });
        document.querySelectorAll('h2, h3, .info-section, .explanation, [class*="info"], [class*="explain"]').forEach(el => {
            if (el.textContent && el.textContent.includes('指数とは')) {
                let node = el;
                while (node) { node.style.display = 'none'; node = node.nextElementSibling; }
            }
        });
    }""")
    page.wait_for_timeout(300)
    el = page.query_selector(".main-content")
    if el:
        el.screenshot(path=output_path, type="jpeg", quality=90)
        print(f"  指数スクショ保存: {output_path}")
        return True
    print(f"  指数 .main-content が見つかりません")
    return False


def main():
    if not os.path.exists(POSTED_FILE):
        print("posted_tweets.json が見つかりません。step4_tweet.py を先に実行してください。")
        sys.exit(1)

    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        posted = json.load(f)

    # 直近のエントリからカードIDとBOX IDを取得
    card_ids = []
    box_ids = []
    for entry in reversed(posted[-5:]):
        eid = entry.get("id", "")
        if eid.startswith("box_"):
            box_ids.append(eid.replace("box_", ""))
        elif eid and not eid.startswith("index"):
            card_ids.append(eid)

    os.makedirs(IMG_DIR, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1024, "height": 1600})

        # カードスクショ
        for card_id in card_ids[:2]:
            output = os.path.join(IMG_DIR, f"tw_{card_id}.jpg")
            try:
                take_card_screenshot(page, card_id, output)
            except Exception as e:
                print(f"  カードスクショ失敗 ({card_id}): {e}")

        # BOXスクショ
        for box_id in box_ids[:2]:
            output = os.path.join(IMG_DIR, f"tw_box_{box_id}.jpg")
            try:
                take_box_screenshot(page, box_id, output)
            except Exception as e:
                print(f"  BOXスクショ失敗 ({box_id}): {e}")

        # 指数チャートスクショ
        index_img = os.path.join(IMG_DIR, "tw_index.jpg")
        try:
            take_index_screenshot(page, index_img)
        except Exception as e:
            print(f"  指数スクショ失敗: {e}")

        browser.close()

    print("スクショ撮影完了")


if __name__ == "__main__":
    main()
