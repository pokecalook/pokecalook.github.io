# ポケカるっく

URL: https://pokecalook.com
GitHub: https://github.com/pokecalook/pokecalook.github.io

ポケモンカードの美品・PSA10・未開封BOXの相場が簡単にチェックできるサイト。毎日自動更新。

## アーキテクチャ

### データソース
- 出品一覧API（`/used`）のSOLDデータ（status=4）がメイン
- セット売り（2枚以上）も含め `price÷枚数` で1枚単価を算出
- `price_data_api.json` に `sold_data` フィールドとして保存（各エントリに `qty` 付与）
- 取引件数は SOLD 1回=1件（枚数で割り増ししない）

### ワークフロー対応表
| 変更したファイル | 実行するワークフロー | オプション |
|---|---|---|
| step3_report.py / HTMLテンプレート | Update Prices | HTMLのみ ✅ |
| step3_box_report.py | Update Prices | HTMLのみ ✅ |
| step3_top.py | Update Prices | HTMLのみ ✅ |
| step3_articles.py | Update Prices | HTMLのみ ✅ |
| step5_index.py | Update Prices | HTMLのみ ✅ |
| step4_tweet.py | Generate Tweet Texts | なし |
| step1 / step2 / step2b | Update Prices | フル（チェックなし） |
| step1_box_links / step2_box_api | Update Prices | フル（チェックなし） |
| common.js / common.css | 不要（push時に即反映） |
| guide.html / about.html / privacy.html / contact.html / ads.txt / CNAME | 不要（push時に即反映） |

### ファイル生成元
- `index.html`: step3_top.py（TOPページ）。step3_report.pyが `report.html` を生成し `cp report.html index.html` もする
- `report.html`: step3_report.py
- `cards/*.html`: step3_report.py の `generate_card_pages()`
- `portfolio.html`: step3_report.py の `generate_portfolio_page()`
- `box.html`: step3_box_report.py（Chart.js使用）
- `box/*.html`: step3_box_report.py
- `articles/*.html`: step3_articles.py
- `index-chart.html`: step5_index.py
- `tweets.html`: step4_tweet.py（Generate Tweet Textsワークフローで生成）

### 変動額表示仕様
- 全ページで「変動率(%)」を廃止し「変動額(円)」に統一
- 計算方法: 直近7日中央値 − 前週(or 4週前)7日中央値 = 変動額
- 表示: `+¥3,000`（緑） / `-¥1,500`（赤） / `±¥0`（青）

### 共通コンポーネント（現状: common.js方式 → Python静的埋め込みに移行予定）
- **common.js**: ヘッダー/ナビ/フッター/gtagを動的挿入（FOUC問題あり、SEO問題あり）
- **common.css**: 全ページ共通CSS
- **移行先**: `common_html.py` で共通HTML変数を定義し、各Pythonスクリプトがimportして静的に埋め込む方式

## Git運用ルール
- ローカル: `C:\Users\shimitk\Documents\Kiro\snkrdunk_scraper\`
- push前に必ず `git pull --rebase --autostash origin main`

### Kiro向けgit操作手順（厳守）
1. 動作確認でHTML生成物ができたら、commit前に `git checkout -- cards/ index.html portfolio.html sitemap.xml box.html report.html` で破棄
2. ソースコード（.py, .yml, .html静的ファイル）のみを `git add ファイル名` で明示指定。**`git add .` 禁止**
3. commit→push は1コマンドで:
   ```
   git add step3_report.py; git commit -m "msg"; git pull --rebase --autostash origin main; git push origin main
   ```
4. git操作は `timeout 120000` 以上
5. `index.lock` が出たら: `Remove-Item .git/index.lock -Force` → 即リトライ
6. **`git commit --amend` 禁止**
7. ワークフロー実行中でもソースコードのみならpush可（HTML生成物を含めなければ安全）
8. **rebase conflict解決後、commit前に必ず `<<<<<<` マーカー残留を確認。残っていたら絶対にcommitしない**
9. conflict解決時に `git add -A` 禁止。対象ファイルを明示指定

## GitHub Pages デプロイ
- `deploy-pages.yml` が push 毎に Pages artifact を作成して deploy
- Jekyll不使用（`build_type: workflow`）

## キャッシュ運用ルール（重要）
- `price_data_api.json` のデータ構造を変更したら、`is_cache_stale()` に旧形式判定を追加しないと既存キャッシュが再取得されない
- `CACHE_MAX_AGE_DAYS=1` だけでは、24時間以内に取得済みのキャッシュは新ロジックで再取得されない
- `price_data_api.json` / `box_price_data.json` を勝手に削除するな（`schema` フィールド含む）

## 注意事項（Kiro向け）
- 敬語で丁寧に話せ
- 忖度するな。確認してない情報を断言するな。無駄な作業は即指摘
- 相談段階では相談だけ。実行段階になったら即やれ
- Pythonスクリプト変更時は必ず実行して動作確認してからpush
- push後はワークフロー対応表に従って正しいワークフローを実行
- ファイル変更後は commit→push→ワークフロー実行まで一気通貫でやれ。手順案内だけで終わるな
- Git経由でpush。手動アップロードはしない
- **ユーザーが「動いてない」「反映されてない」と指摘した場合、ワークフローは実行済み・反映済みという前提で対応しろ。「ワークフロー走らせましたか？」と聞き返すな。コードのバグを疑え**
- コンテキストを言い訳にして後回しにするな
- ユーザーが「次のチャットへ」と指示するまで、自分から次のチャットでやると言うな
- **GitHub Actions ワークフローのログ確認方法:**
  - ghコマンドが使えなくても `urllib.request` で GitHub API を直接叩ける
  - runs一覧: `https://api.github.com/repos/pokecalook/pokecalook.github.io/actions/runs?per_page=5`
  - jobs一覧: `https://api.github.com/repos/pokecalook/pokecalook.github.io/actions/runs/{run_id}/jobs`
  - 「ログが見れない」「確認できない」と言い訳するな。APIで確認しろ
- HTMLソースに px.a8.net を直書きするな（go/リダイレクト経由）
- クラス名やIDに「ad」を含めるな。バナー画像は images/ptn-* から配信
- X（Twitter）の文字数制限: 280文字（日本語は1文字=2カウント、実質140文字）
- **GitHub Actions操作の鉄則:**
  - workflow dispatchがタイムアウトで返っても受理されている可能性あり。リトライ前にruns一覧を確認
  - cancelやdispatchは対象のワークフロー名とrun IDを明示してから実行。「全部キャンセル」は絶対にやるな
  - 推測で破壊的操作をするな。事実を確認してから行動しろ
- **設計判断の原則: 同じコードが複数箇所にあるなら、個別修正ではなく共通化を最初にやれ。場当たり的な修正を繰り返すな**

## ナビボタンのリンク先（確定）
- 🏠 TOP → /index.html
- 🃏 シングル相場 → /report.html
- 📦 未開封BOX → /box.html
- 📰 記事 → /articles/index.html
- 📊 ポケカ指数 → /index-chart.html
- 📋 持ってるリスト → /portfolio.html

## フッターリンク（確定）
シングル相場 / 未開封BOX / 記事一覧 / 使い方ガイド / このサイトについて / プライバシーポリシー / ポケカ指数 / お問い合わせ / 持ってるリスト管理

## 収益化
**A8.netアフィリエイト（4案件提携済み）**
- トレトク買取: 1390円/件
- カーナベル買取: 1500円/件（2026/5/13〜 一時停止）
- カーナベル通販: 新規12%
- Bee本舗: 購入5%+買取1400円

**Google AdSense**
- Publisher ID: `ca-pub-6291930766379160`
- 現在広告なし（再審査待ち）

**アドブロック対策**
- バナー画像: images/ptn-* から配信
- リンクURL: go/xxx.html リダイレクト経由
- 広告 `<a><img>` は JSで動的挿入

## ポスト文ルール
### 投稿数・構成
- 1日3投稿: 指数チャート1 + カード1 + BOX1
- 画像は必ず添付（チャート画像にサイト名「pokecalook.com」を焼き込む）

### Xアルゴリズム対策（2025年5月時点）
**禁止事項（ペナルティ対象）:**
- 「どう思う？」「皆さんはどう予想しますか？」「賛成ならRT」系のエンゲージメント誘導文
- 1日4投稿以上の連投（投稿希釈ペナルティ）
- テキストだけの投稿（画像/動画付きが圧倒的優遇）
- リプ欄に外部リンクを貼る（無効化済み。本ポストもリプも外部リンクはマイナス）

**伸びるフォーマット:**
- 一次データ・証拠付きの投稿（実際の取引データを持ってるのが強み）
- テキスト＋画像
- 具体的な数字・実例
- 一次分析（「なぜそうなったか」の考察）
- 長文投稿（4000文字フォーマットが強シグナル）
- 投稿直後30分の返信活動

**サイト誘導方法（リンク貼れないので）:**
- チャート画像に「pokecalook.com」を焼き込む
- プロフィールのリンク（唯一ペナルティなし）
- アカウント名/bioで「ポケカるっく」を認知させ、検索流入を狙う
- 固定ポストにサイト紹介

### テンプレート
- B型（比較型）7割 / C型（ストーリー型）3割
- 問いかけ系全廃
- 分析パート: データ事実のみ（倍率変化、取引件数増減、月間変動）
- ハッシュタグ全廃
- URLはポスト文に含めない（リプにも貼らない。外部リンクはペナルティ）
- 絵文字は1行目の末尾に1個のみ（📈📉📦📊）
- 敬語（です/ます調）
- 構造: 見出し→データ行→事実締め（条件分岐で自動選択）
- パート単位で3パターン以上、組み合わせで被らないようにする
- 文字数: 130-140文字（Xカウント260-280）を狙う。250未満なら追加データ行を挿入（280超えない範囲で）
- 画像: Playwrightでページスクショ（ブランドバー付き）
- tweets.htmlの「URLコピー」ボタン廃止済み

### 選定ロジック
- カード: 週間取引50件以上 & 変動額±3,000円以上（美品orPSA10の大きい方）、変動額絶対値でソート
- BOX: 週間取引100個以上 & 変動額±800円以上、変動額絶対値でソート
- 重複排除: 同じカードID 3日、同じポケモン名 3日。使い切ったら重複無視（型を変える）
- 生成数: カード2本 + BOX2本 + index1本（計5本）

## 法的リスク（決定済み）
- スニダン規約上はスクレイピング禁止だが、許可を求めず運営継続
- 画像は自サーバーにホスティング済み
- 出典は「国内フリマサイトの取引履歴をもとに集計」と表記
