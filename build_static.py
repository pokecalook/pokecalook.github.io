"""
build_static.py - 静的HTMLページ（guide/about/contact/privacy）を再生成

common_html.py のヘッダー/ナビ/フッター/gtagを静的に埋め込んだHTMLを出力する。
ワークフローで実行し、common.js依存を排除する。

使い方: python build_static.py
"""

from common_html import get_header, get_nav, get_footer, get_gtag, get_meta_keywords


def build_guide():
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{get_gtag()}
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
{get_meta_keywords()}
<title>使い方ガイド - ポケカるっく</title>
<style>
.main-content{{flex:1;min-width:0;max-width:800px;margin:0 auto}}
h2{{font-size:1.3rem;color:#1e40af;margin:32px 0 12px;padding-bottom:8px;border-bottom:3px solid #dbeafe}}
h3{{font-size:1.05rem;color:#374151;margin:20px 0 8px}}
p{{margin:8px 0;color:#374151}}
.card{{background:#fff;border:2px solid #e5e7eb;border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.badge-demo{{display:inline-block;padding:3px 10px;border-radius:16px;font-size:.85rem;font-weight:700;margin:2px 4px}}
.b-r{{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}}
.b-o{{background:#fff7ed;color:#ea580c;border:1px solid #fed7aa}}
.b-b{{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}}
.b-t{{background:#f0fdfa;color:#0d9488;border:1px solid #99f6e4}}
.b-x{{background:#f3f4f6;color:#6b7280;border:1px solid #d1d5db}}
table{{width:100%;border-collapse:collapse;margin:12px 0}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #e5e7eb;font-size:.9rem}}
th{{background:#f9fafb;font-weight:700;color:#374151}}
.highlight{{background:#fef3c7;padding:2px 6px;border-radius:4px;font-weight:600}}
.note{{background:#eff6ff;border:2px solid #93c5fd;border-radius:10px;padding:14px 18px;margin:16px 0;font-size:.9rem;color:#1e40af}}
@media(max-width:768px){{
  h2{{font-size:1.1rem}}
  .card{{padding:14px}}
}}
</style>
</head>
<body>

{get_header()}
{get_nav(active="single")}

<div class="main-content">

<h2>ポケカるっくとは？</h2>
<div class="card">
  <p>国内の複数サイトの取引データをもとに、ポケモンカードの<span class="highlight">美品価格</span>と<span class="highlight">PSA10価格</span>を比較するサイトです。</p>
  <p>「この美品カードをPSA鑑定に出してPSA10を取ったら、何倍の値段で売れるか？」がひと目でわかります。</p>
</div>

<h2>数字の見方</h2>
<div class="card">
<h3>美品 / PSA10</h3>
<p>それぞれ直近7日間の取引価格の中央値です。</p>

<h3>倍率</h3>
<p>PSA10価格 ÷ 美品価格。高いほど鑑定に出す旨味が大きいです。</p>
<table>
  <tr><th>倍率</th><th>色</th><th>意味</th></tr>
  <tr><td>4.0x以上</td><td style="color:#059669;font-weight:700">緑</td><td>鑑定の旨味が大きい</td></tr>
  <tr><td>3.0x〜3.9x</td><td style="color:#d97706;font-weight:700">黄</td><td>まあまあ</td></tr>
  <tr><td>3.0x未満</td><td style="color:#6b7280;font-weight:700">グレー</td><td>鑑定コスト考えると微妙</td></tr>
</table>

<h3>取引件数</h3>
<p>多いほど相場の信頼性が高いです。</p>
</div>

<h2>トレンドバッジ</h2>
<div class="card">
<p>PSA10価格の直近1週間の変動額です。</p>
<table>
  <tr><th>バッジ</th><th>意味</th></tr>
  <tr><td><span class="badge-demo b-r">🔥 +¥8,000</span></td><td>¥5,000以上の急騰</td></tr>
  <tr><td><span class="badge-demo b-o">📈 +¥2,000</span></td><td>¥1,000〜¥5,000の上昇</td></tr>
  <tr><td><span class="badge-demo b-b">→ +¥300</span></td><td>横ばい（±¥1,000以内）</td></tr>
  <tr><td><span class="badge-demo b-t">📉 -¥2,000</span></td><td>¥1,000〜¥5,000の下落</td></tr>
</table>
</div>

<h2>ソート・検索</h2>
<div class="card">
<h3>ソート</h3>
<table>
  <tr><th>項目</th><th>説明</th></tr>
  <tr><td>取引件数</td><td>取引件数が多い順（デフォルト）</td></tr>
  <tr><td>倍率（PSA10÷美品）</td><td>倍率が高い順</td></tr>
  <tr><td>美品価格</td><td>美品価格が高い順</td></tr>
  <tr><td>PSA10価格</td><td>PSA10価格が高い順</td></tr>
  <tr><td>PSA10 週間変動額</td><td>直近1週間のPSA10価格の変動額</td></tr>
  <tr><td>美品 週間変動額</td><td>直近1週間の美品価格の変動額</td></tr>
  <tr><td>PSA10 1ヶ月変動額</td><td>直近1ヶ月のPSA10価格の変動額</td></tr>
  <tr><td>美品 1ヶ月変動額</td><td>直近1ヶ月の美品価格の変動額</td></tr>
  <tr><td>差額（PSA10−美品）</td><td>PSA10と美品の差額が大きい順</td></tr>
</table>
<p>同じボタンをもう一度押すと昇順/降順が切り替わります。</p>

<h3>検索</h3>
<p>ポケモン名やカード名で検索。スペース区切りでAND検索。</p>
</div>

<h2>お気に入り・ポートフォリオ</h2>
<div class="card">
<p>☆をクリックでお気に入り登録。「持ってる」で枚数を登録するとポートフォリオバーに合計資産が表示されます。データはブラウザに保存されます。</p>
</div>

<h2>PSA10鑑定率チェック</h2>
<div class="card">
<p>「🎯 PSA10鑑定率チェック」ボタンを押すと、検索テキストがコピーされGemRateが開きます。貼り付けて検索すると、そのカードのPSA10取得率がわかります。</p>
</div>

</div>

{get_footer()}
</body>
</html>'''


def build_about():
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{get_gtag()}
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
{get_meta_keywords()}
<title>このサイトについて - ポケカるっく</title>
<meta name="description" content="ポケカるっくの運営方針・データ収集方法・分析手法について。国内取引履歴を集計し、ポケモンカードの美品とPSA10の相場を可視化しています。">
<style>
.main-content{{flex:1;min-width:0;max-width:800px;margin:0 auto}}
h2{{font-size:1.3rem;color:#1e40af;margin:28px 0 12px;padding-bottom:8px;border-bottom:3px solid #dbeafe}}
h3{{font-size:1.05rem;color:#374151;margin:18px 0 8px}}
p{{margin:8px 0;color:#374151}}
.card{{background:#fff;border:2px solid #e5e7eb;border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
ul{{margin:8px 0 8px 20px;color:#374151}}
li{{margin:6px 0}}
.highlight{{background:#fef3c7;padding:2px 6px;border-radius:4px;font-weight:600}}
.note{{background:#eff6ff;border-left:4px solid #3b82f6;padding:12px 16px;margin:14px 0;font-size:.9rem;color:#1e40af}}
table{{width:100%;border-collapse:collapse;margin:12px 0}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #e5e7eb;font-size:.9rem}}
th{{background:#f9fafb;font-weight:700;color:#374151}}
.profile{{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}}
.profile-img{{width:80px;height:80px;border-radius:50%;background:#e8941a;display:flex;align-items:center;justify-content:center;font-size:2.5rem;flex-shrink:0}}
.profile-text{{flex:1;min-width:200px}}
.profile-text h3{{margin-top:0}}
@media(max-width:768px){{
  .card{{padding:14px}}
}}
</style>
</head>
<body>

{get_header()}
{get_nav()}

<div class="main-content">

<h2>ポケカるっくとは</h2>
<div class="card">
  <p><strong>ポケカるっく（pokecalook.com）</strong>は、ポケモンカードの「<span class="highlight">美品</span>」と「<span class="highlight">PSA10鑑定済み</span>」の取引価格を比較できる無料の相場データベースです。</p>
  <p>ポケモンカードのコレクターやプレイヤーが「手元のカードをPSA鑑定に出すべきか」「いま売るべきか、保有するべきか」を判断するための、客観的なデータを提供することを目的としています。</p>
  <p>2026年5月に公開し、現時点で<strong>10,000枚以上のシングルカード</strong>と<strong>1,000種類以上の未開封BOX</strong>の相場を追跡しています。</p>
</div>

<h2>運営者について</h2>
<div class="card">
  <div class="profile">
    <div class="profile-img">🃏</div>
    <div class="profile-text">
      <h3>ポケカるっく管理人</h3>
      <p>ポケカるっくは、<strong>ポケモンカードのコレクターである管理人</strong>が、自分自身が日々の相場チェックに使いやすいサイトを作りたいという思いから立ち上げた、個人運営のファンサイトです。</p>
      <p>毎日の相場チェック、価格推移の確認、保有カードの資産管理など、コレクター目線で「あったら便利」と思った機能をひとつずつ形にしています。利用者と同じ目線でサイトを使いながら改善を続けています。</p>
      <p>ご意見・ご要望は <a href="contact.html" style="color:#3b82f6">お問い合わせフォーム</a> からお寄せください。</p>
    </div>
  </div>
</div>

<h2>データ収集と更新の仕組み</h2>
<div class="card">
  <h3>データソース</h3>
  <p>本サイトの価格データは、国内のポケモンカード取引プラットフォームに掲載された<strong>取引成立済みデータ</strong>をもとに集計しています。実際に売買が成立した価格のみを使用しているため、出品価格や希望価格ではなく、<strong>市場で実際に動いた金額</strong>を反映しています。</p>
  <h3>更新頻度</h3>
  <p>データは<strong>毎日更新</strong>しています。日次で取得・集計・サイト再生成を行うため、相場の変動をタイムリーに反映できます。</p>
  <h3>収集対象</h3>
  <ul>
    <li>シングルカード（美品コンディション・PSA10鑑定済み）</li>
    <li>未開封BOX（シュリンク付き・シュリンクなしを含む）</li>
    <li>カード番号・レアリティ・収録セット情報</li>
    <li>取引日時・取引価格・出品コンディション</li>
  </ul>
  <h3>セット売り（複数枚出品）の扱い</h3>
  <p>2枚以上をまとめて出品されたケースについても、<code>取引価格 ÷ 枚数</code> で1枚あたりの単価を算出して集計に含めています。サンプル数が増えることで、相場精度が向上するメリットがあります。</p>
  <h3>データの集計方法</h3>
  <p>表示価格は、原則として<strong>直近7日間の取引価格の中央値</strong>を採用しています。中央値を使う理由は、極端な高値・安値の影響を受けにくく、より実態に近い相場を表せるためです。</p>
</div>

<h2>分析指標について</h2>
<div class="card">
  <h3>倍率（PSA10 ÷ 美品）</h3>
  <p>美品価格に対してPSA10価格が何倍になっているかを示す指標です。</p>
  <table>
    <tr><th>倍率</th><th>判断目安</th></tr>
    <tr><td>4.0倍以上</td><td>鑑定費用を考慮しても利益が出やすい水準</td></tr>
    <tr><td>3.0〜3.9倍</td><td>鑑定の妙味あり、ただしコスト試算が必須</td></tr>
    <tr><td>3.0倍未満</td><td>鑑定費用を回収しづらい水準</td></tr>
  </table>
  <p class="note">⚠️ 倍率はあくまで「PSA10が取得できた場合」の理論値です。実際にはPSA10取得率を考慮した期待値で判断する必要があります。</p>
  <h3>変動額（円）</h3>
  <p>「直近7日間の中央値」と「前週7日間の中央値」の差を「週間変動額」、4週前との差を「1ヶ月変動額」として表示しています。</p>
  <h3>取引件数</h3>
  <p>サンプル数の多寡を示します。取引件数が少ないカードは中央値が外れ値の影響を受けやすいため、本サイトでは<strong>10件未満のカードは一覧から除外</strong>しています。</p>
</div>

<h2>掲載される情報・機能</h2>
<div class="card">
  <ul>
    <li>美品価格とPSA10価格の倍率比較（<a href="report.html" style="color:#3b82f6">シングル相場</a>）</li>
    <li>未開封BOX相場（<a href="box.html" style="color:#3b82f6">未開封BOX</a>）</li>
    <li>価格推移チャート（1ヶ月／3ヶ月／6ヶ月／1年／全期間）</li>
    <li>ポケカ全体相場の動向を一目で把握できる<a href="index-chart.html" style="color:#3b82f6">ポケカ指数</a></li>
    <li>ポケモン名・カード名での検索、各種ソート・フィルタ</li>
    <li>GemRateと連携したPSA10鑑定率チェック</li>
    <li>お気に入り登録・<a href="portfolio.html" style="color:#3b82f6">ポートフォリオ管理</a>（ブラウザ内に保存）</li>
    <li>個別カードページ（最高値・最安値・取引期間・週間／月間変動の詳細）</li>
  </ul>
</div>

<h2>免責事項</h2>
<div class="card">
  <p>本サイトの情報は<strong>参考値</strong>であり、実際の取引価格を保証するものではありません。</p>
  <p>本サイトの情報を利用したことによる売買・鑑定・投資判断について、運営者は一切の責任を負いません。最終的な判断はご自身の責任でお願いいたします。</p>
</div>

<h2>著作権・商標について</h2>
<div class="card">
  <p>本サイトは個人が運営するファンサイトであり、株式会社ポケモン・株式会社クリーチャーズ・任天堂株式会社、ならびにデータ提供元の取引プラットフォーム企業のいずれとも一切関係ありません。</p>
  <p>「ポケットモンスター」「ポケモンカードゲーム」を含むポケモン関連の名称・キャラクター画像・ロゴ等の著作権・商標権は、それぞれの権利者に帰属します。</p>
  <p>本サイト独自のデザイン・分析指標・集計データの無断転載はご遠慮ください。引用の際は出典としてサイト名（ポケカるっく）と該当ページのURLの記載をお願いします。</p>
</div>

</div>

{get_footer()}
</body>
</html>'''


def build_contact():
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{get_gtag()}
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
{get_meta_keywords()}
<title>お問い合わせ - ポケカるっく</title>
<meta name="description" content="ポケカるっくへのお問い合わせフォーム。ご意見・ご要望・不具合報告などお気軽にどうぞ。">
<style>
.main-content{{flex:1;min-width:0;max-width:700px;margin:0 auto}}
h2{{font-size:1.3rem;color:#1e40af;margin:28px 0 12px;padding-bottom:8px;border-bottom:3px solid #dbeafe}}
p{{margin:8px 0;color:#374151}}
.form-card{{background:#fff;border:2px solid #e5e7eb;border-radius:14px;padding:28px 24px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.form-group{{margin-bottom:20px}}
.form-group label{{display:block;font-size:.9rem;font-weight:700;color:#374151;margin-bottom:6px}}
.form-group label .req{{color:#dc2626;margin-left:4px}}
.form-group input,.form-group textarea,.form-group select{{
  width:100%;padding:12px 14px;border:2px solid #d1d5db;border-radius:10px;
  font-size:.9rem;font-family:inherit;color:#1a1a2e;background:#fff;
  transition:border-color .15s;
}}
.form-group input:focus,.form-group textarea:focus,.form-group select:focus{{
  border-color:#3b82f6;outline:none;box-shadow:0 0 0 3px rgba(59,130,246,.1);
}}
.form-group textarea{{resize:vertical;min-height:160px}}
.submit-btn{{
  display:block;width:100%;padding:14px;border:none;border-radius:10px;
  background:linear-gradient(135deg,#3b82f6,#1d4ed8);color:#fff;
  font-size:1rem;font-weight:700;cursor:pointer;font-family:inherit;
  transition:opacity .15s,transform .15s;
}}
.submit-btn:hover{{opacity:.9;transform:translateY(-1px)}}
.submit-btn:active{{transform:translateY(0)}}
.note{{font-size:.8rem;color:#6b7280;margin-top:12px;text-align:center}}
@media(max-width:768px){{
  .form-card{{padding:20px 16px}}
}}
</style>
</head>
<body>

{get_header()}
{get_nav()}

<div class="main-content">

<p style="text-align:center;color:#6b7280;font-size:.85rem;margin-bottom:8px">ご意見・ご要望・不具合報告などお気軽にどうぞ。</p>
<p style="text-align:center;color:#9ca3af;font-size:.75rem;margin-bottom:20px">※ すべてのお問い合わせに個別にご返信できない場合がございます。予めご了承ください。</p>

<div class="form-card">
  <form action="https://formspree.io/f/xwpkgjvr" method="POST">
    <div class="form-group">
      <label>お名前（ニックネーム可）<span class="req">*</span></label>
      <input type="text" name="name" required placeholder="例: ポケカ太郎">
    </div>
    <div class="form-group">
      <label>メールアドレス<span class="req">*</span></label>
      <input type="email" name="email" required placeholder="例: example@mail.com">
    </div>
    <div class="form-group">
      <label>お問い合わせ種別</label>
      <select name="category">
        <option value="ご意見・ご要望">ご意見・ご要望</option>
        <option value="不具合報告">不具合報告</option>
        <option value="データに関する質問">データに関する質問</option>
        <option value="その他">その他</option>
      </select>
    </div>
    <div class="form-group">
      <label>お問い合わせ内容<span class="req">*</span></label>
      <textarea name="message" required placeholder="お問い合わせ内容をご記入ください"></textarea>
    </div>
    <button type="submit" class="submit-btn">送信する</button>
  </form>
  <p class="note">送信後、確認メールが届きます。届かない場合はメールアドレスをご確認ください。</p>
</div>

<h2>よくあるご質問</h2>
<div class="form-card">
  <p><strong>Q. データはどこから取得していますか？</strong></p>
  <p>A. 国内フリマサイトの取引成立済みデータをもとに集計しています。詳しくは<a href="about.html" style="color:#3b82f6">このサイトについて</a>をご覧ください。</p>
  <p style="margin-top:16px"><strong>Q. 特定のカードを追加してほしい</strong></p>
  <p>A. 取引データが一定数以上あるカードは自動的に追加されます。まだ掲載されていないカードは取引件数が不足している可能性があります。</p>
  <p style="margin-top:16px"><strong>Q. 価格が実際と違う気がする</strong></p>
  <p>A. 表示価格は直近7日間の取引中央値です。出品価格ではなく成立価格のため、現在の出品価格とは異なる場合があります。</p>
</div>

</div>

{get_footer()}
</body>
</html>'''


def build_privacy():
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{get_gtag()}
<link rel="icon" type="image/png" href="images/logo.png">
<link rel="stylesheet" href="common.css">
{get_meta_keywords()}
<title>プライバシーポリシー - ポケカるっく</title>
<style>
.main-content{{flex:1;min-width:0;max-width:800px;margin:0 auto}}
h2{{font-size:1.3rem;color:#1e40af;margin:28px 0 12px;padding-bottom:8px;border-bottom:3px solid #dbeafe}}
p{{margin:8px 0;color:#374151}}
.card{{background:#fff;border:2px solid #e5e7eb;border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
ul{{margin:8px 0 8px 20px;color:#374151}}
li{{margin:4px 0}}
@media(max-width:768px){{
  .card{{padding:14px}}
}}
</style>
</head>
<body>

{get_header()}
{get_nav()}

<div class="main-content">

<p>ポケカるっく（以下「本サイト」）は、利用者のプライバシーを尊重し、以下の方針に基づいて運営しています。</p>

<h2>個人情報の収集について</h2>
<div class="card">
  <p>本サイトでは、利用者から氏名・メールアドレス等の個人情報を直接収集することはありません。</p>
  <p>会員登録やログインの機能はなく、すべてのコンテンツを匿名でご利用いただけます。</p>
</div>

<h2>アクセス解析について</h2>
<div class="card">
  <p>本サイトでは、サービス改善のためにアクセス解析ツールを導入する場合があります。</p>
  <p>アクセス解析ツールでは、Cookieを使用してアクセス情報（IPアドレス、ブラウザの種類、参照元ページ等）を収集することがあります。この情報は統計データとして利用され、個人を特定するものではありません。</p>
  <p>Cookieの使用を望まない場合は、ブラウザの設定から無効にすることができます。</p>
</div>

<h2>広告について</h2>
<div class="card">
  <p>本サイトでは、今後以下の広告サービスを利用する場合があります。</p>
  <ul>
    <li>Google AdSense（第三者配信の広告サービス）</li>
    <li>A8.net（アフィリエイト広告）</li>
  </ul>
  <p>広告配信事業者は、利用者の興味に応じた広告を表示するためにCookieを使用することがあります。利用者はこれらの広告配信事業者のWebサイトにて、Cookieの使用を無効にすることができます。</p>
</div>

<h2>外部リンクについて</h2>
<div class="card">
  <p>本サイトにはGemRate等の外部サイトへのリンクが含まれています。リンク先のサイトにおけるプライバシーの取り扱いについては、各サイトのプライバシーポリシーをご確認ください。</p>
</div>

<h2>ポリシーの変更について</h2>
<div class="card">
  <p>本ポリシーの内容は、必要に応じて変更することがあります。変更後のポリシーは本ページに掲載した時点で効力を持ちます。</p>
</div>

<p style="text-align:right;color:#6b7280;font-size:.85rem;margin-top:20px">制定日: 2026年5月2日</p>

</div>

{get_footer()}
</body>
</html>'''


def main():
    pages = [
        ("guide.html", build_guide),
        ("about.html", build_about),
        ("contact.html", build_contact),
        ("privacy.html", build_privacy),
    ]
    for filename, builder in pages:
        html = builder()
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ {filename} 生成完了 ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
