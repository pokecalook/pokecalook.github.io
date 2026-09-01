---
inclusion: auto
---

# ポケカるっく開発ルール（絶対遵守）

## 禁止事項（違反したら即指摘される。言い訳するな）

1. **「コンテキストが足りない」「残量が少ない」「次のチャットで」「残りは次回」等の発言は禁止。** 残量があるなら即やれ。コンテキスト残量に言及すること自体が禁止。
2. **ユーザーが「次のチャットへ」と明示的に指示するまで、自分から作業を打ち切る提案をするな。**
3. **「確認できない」「ログが見れない」は禁止。** GitHub APIで確認しろ。
4. **確認してない情報を断言するな。** 推測で「問題ないはず」と言うな。確認してから言え。
5. **ワークフロー実行済みか聞き返すな。** ユーザーが「動いてない」と言ったらコードのバグを疑え。

## 設計原則

- 同じコードが複数箇所にあるなら、個別修正ではなく共通化を最初にやれ
- 場当たり的な修正を繰り返すな
- 相談段階では相談だけ。実行段階になったら即やれ。手順案内だけで終わるな

## Git操作手順（厳守）

1. 動作確認でHTML生成物ができたら、commit前に必ず破棄:
   ```
   git checkout -- cards/ index.html portfolio.html sitemap.xml box.html report.html box/ articles/
   ```
2. `git add .` 禁止。ソースコードのみを `git add ファイル名` で明示指定
3. commit→push は1コマンドで:
   ```
   git add ファイル名; git commit -m "msg"; git pull --rebase --autostash origin main; git push origin main
   ```
4. git操作は `timeout 120000` 以上
5. `git commit --amend` 禁止
6. rebase conflict解決後、`<<<<<<` マーカー残留を確認。残っていたら絶対にcommitしない
7. conflict解決時に `git add -A` 禁止

## ワークフロー対応表

| 変更したファイル | 実行するワークフロー | オプション |
|---|---|---|
| step3_report.py / step3_box_report.py / step3_top.py / step3_articles.py / step5_index.py | Update Prices | HTMLのみ ✅ |
| step4_tweet.py | Generate Tweet Texts | なし |
| step1 / step2 / step2b / step1_box_links / step2_box_api | Update Prices | フル（チェックなし） |
| common.js / common.css / guide.html / about.html / privacy.html / contact.html | 不要（push時に即反映） |

## ワークフローdispatch方法

トークンはリモートURLに埋め込まれている:
```python
import subprocess
result = subprocess.run(['git', 'config', '--get', 'remote.origin.url'], capture_output=True, text=True)
token = result.stdout.strip().split(':')[2].split('@')[0]
```

dispatch:
```python
import urllib.request, json
url = 'https://api.github.com/repos/pokecalook/pokecalook.github.io/actions/workflows/update-prices.yml/dispatches'
data = json.dumps({'ref': 'main', 'inputs': {'html_only': 'true'}}).encode()
req = urllib.request.Request(url, data=data, method='POST')
req.add_header('Authorization', 'Bearer ' + token)
req.add_header('Accept', 'application/vnd.github+json')
req.add_header('Content-Type', 'application/json')
urllib.request.urlopen(req)
```

## 口調

- 敬語で丁寧に話せ
- JSTで時刻を話せ

## AdSense審査対策（常に意識すること）

- Google AdSenseに現在不合格。再審査に受かることを常に意識して設計・実装する
- 各ページに十分なオリジナルテキストコンテンツを持たせる（iframe埋め込みだけのページは作らない）
- お問い合わせページはHTMLネイティブフォーム（Formspree等のバックエンド利用）で実装する。Googleフォームのiframe埋め込みは「独自コンテンツが薄い」と判定されるリスクがある
- プライバシーポリシー・免責事項・運営者情報を充実させる
- 自動生成ページでも、解説文・注記・見出し等で人間が読んで価値のあるテキストを含める
- 記事ページはアーカイブとして蓄積し、ページ数を増やす
- 全ページにmeta description、canonical URL、OGPを設定する
- サイトマップを正しく生成し、Search Consoleに送信する

## CSS/デザイン変更時の鉄則（2026/5/24 事故から追加）

1. **common.jsとcommon_html.pyは必ずセットで確認しろ。** ナビ・ヘッダー・フッターはJS動的挿入とPython静的埋め込みの2系統がある。片方だけ変えると不整合が起きる
2. **CSSクラス名を変更したら、そのクラス名を使っている全ファイルをgrepで洗い出せ。** common.css / common.js / common_html.py / 全step*.py / build_static.py の全部
3. **push前に必ず全ページをローカルで生成して目視確認。** report.html / box.html / articles/index.html / index-chart.html / portfolio.html の最低5ページ。1ページだけ見て「OK」と判断するな
4. **デザイン変更は必ずサンプルHTMLで全パターン（ナビ・ツールバー・タブ・カード・フィルタ）を見せてからpush。** ユーザーが「いいよ」と言っても、全ページ確認が終わるまでpushするな
5. **「いいよpushしろ」と言われても、自分が全ページ確認してないなら「全ページ確認させてください」と言え。** 品質保証は俺の責任
