"""
ポケカるっく 共通HTMLコンポーネント (common_html.py)

全ページで使うヘッダー/ナビ/フッター/gtag/meta keywordsを
Python側で静的に埋め込むためのモジュール。

使い方:
    from common_html import get_header, get_nav, get_footer, get_gtag, get_meta_keywords, COMMON_CSS
"""

GA_ID = "G-EH0SVLFEJM"


def get_gtag():
    """Google Analytics gtagスクリプトタグを返す"""
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>\n'
        f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA_ID}');</script>"
    )


def get_meta_keywords():
    """meta keywordsタグを返す"""
    return '<meta name="keywords" content="ポケカるっく,ポケカルック,ぽけかるっく,ぽけかルック,pokecalook,PokeCalook,ポケモンカード,PSA10,相場,倍率,美品,鑑定">'


def get_header(prefix=""):
    """ヘッダーHTML（背景画像+ロゴ80px+「ポケカるっく」h1）を返す"""
    return (
        f'<header class="hdr" style="background:url(\'{prefix}images/header-bg.png\') center/cover no-repeat">'
        f'<h1><a href="{prefix}index.html">'
        f'<img src="{prefix}images/logo.png" alt="ポケカるっく" class="logo-img"> ポケカるっく</a></h1>'
        f'<p class="sub">ポケカるっく（ポケカルック / pokecalook）はポケモンカードの相場チェックに役立つ無料データベースです</p>'
        f'</header>'
    )


def get_nav(prefix="", active=""):
    """ナビゲーションボタンHTMLを返す。activeにはページキーを指定。

    ページキー: "top", "single", "box", "articles", "index", "portfolio"
    """
    items = [
        ("top", "🏠", "TOP", "index.html", "nav-btn-top"),
        ("single", "🃏", "シングル相場", "report.html", "nav-btn-single"),
        ("box", "📦", "未開封BOX", "box.html", "nav-btn-box"),
        ("articles", "📰", "記事", "articles/index.html", "nav-btn-articles"),
        ("index", "📊", "ポケカ指数", "index-chart.html", "nav-btn-index"),
        ("portfolio", "📋", "持ってるリスト", "portfolio.html", "nav-btn-portfolio"),
    ]
    buttons = []
    for key, emoji, label, href, cls in items:
        active_cls = " active" if key == active else ""
        buttons.append(
            f'<a href="{prefix}{href}" class="nav-btn {cls}{active_cls}">{emoji} {label}</a>'
        )
    return f'<nav class="nav-buttons">{"".join(buttons)}</nav>'


def get_footer(prefix=""):
    """フッターHTMLを返す（9リンク+©+promo.js読み込み）"""
    links = [
        ("シングル相場", "report.html"),
        ("未開封BOX", "box.html"),
        ("記事一覧", "articles/index.html"),
        ("使い方ガイド", "guide.html"),
        ("このサイトについて", "about.html"),
        ("プライバシーポリシー", "privacy.html"),
        ("ポケカ指数", "index-chart.html"),
        ("お問い合わせ", "contact.html"),
        ("持ってるリスト管理", "portfolio.html"),
    ]
    link_html = "".join(f'<a href="{prefix}{href}">{label}</a>' for label, href in links)
    return (
        f'<footer class="common-footer">{link_html}<p>© 2026 ポケカるっく</p></footer>'
        f'<script src="{prefix}promo.js" defer></script>'
    )


def get_brand_bar():
    """スクショ用ブランドバー（ページ最上部に表示）
    Playwrightでスクショを撮ると自動的に含まれる。
    """
    return (
        '<div class="brand-bar" style="background:#1e40af;color:#fff;text-align:center;'
        'padding:6px 0;font-size:13px;font-weight:600;letter-spacing:0.5px;">'
        'ポケカるっく | pokecalook.com</div>'
    )


# 全ページ共通CSS（<style>タグ内に埋め込む用、common.cssと重複しないインライン用途）
# 基本的にはcommon.cssを外部読み込みするので、ここには追加で必要なものだけ定義
COMMON_CSS = ""
