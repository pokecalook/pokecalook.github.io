/**
 * ポケカるっく 共通コンポーネント (common.js)
 *
 * 使い方:
 *   ルート直下のページ: <script src="common.js"></script>
 *   サブディレクトリ:   <script src="../common.js"></script>
 *
 * このスクリプトは以下を動的挿入する:
 *   - Google Analytics (gtag)
 *   - ヘッダー（ロゴ + サイト名）
 *   - ナビゲーションボタン
 *   - フッター
 */
(function() {
  'use strict';

  // パス深度を自動判定（scriptタグのsrc属性から）
  var scripts = document.getElementsByTagName('script');
  var prefix = '';
  for (var i = 0; i < scripts.length; i++) {
    var src = scripts[i].getAttribute('src') || '';
    if (src.indexOf('common.js') !== -1) {
      // "../common.js" → prefix = "../"
      // "common.js" → prefix = ""
      prefix = src.replace('common.js', '');
      break;
    }
  }

  // --- Google Analytics ---
  var gaId = 'G-EH0SVLFEJM';
  var gaScript = document.createElement('script');
  gaScript.async = true;
  gaScript.src = 'https://www.googletagmanager.com/gtag/js?id=' + gaId;
  document.head.appendChild(gaScript);
  var gaInline = document.createElement('script');
  gaInline.textContent = "window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','" + gaId + "');";
  document.head.appendChild(gaInline);

  // --- ヘッダー ---
  var headerEl = document.getElementById('common-header');
  if (headerEl) {
    headerEl.className = 'hdr';
    headerEl.style.background = "url('" + prefix + "images/header-bg.png') center/cover no-repeat";
    headerEl.innerHTML = '<h1><a href="' + prefix + 'index.html" style="display:inline-flex;align-items:center;gap:14px;color:inherit;text-decoration:none"><img src="' + prefix + 'images/logo.png" alt="ポケカるっく" class="logo-img"> ポケカるっく</a></h1>';
  }

  // --- ナビゲーション ---
  var navEl = document.getElementById('common-nav');
  if (navEl) {
    var navItems = [
      { emoji: '🏠', label: 'TOP', href: 'index.html', cls: 'nav-btn-top' },
      { emoji: '🃏', label: 'シングル相場', href: 'report.html', cls: 'nav-btn-single' },
      { emoji: '📦', label: '未開封BOX', href: 'box.html', cls: 'nav-btn-box' },
      { emoji: '📰', label: '記事', href: 'articles/index.html', cls: 'nav-btn-articles' },
      { emoji: '📊', label: 'ポケカ指数', href: 'index-chart.html', cls: 'nav-btn-index' },
      { emoji: '📋', label: '持ってるリスト', href: 'portfolio.html', cls: 'nav-btn-portfolio' }
    ];

    navEl.className = 'nav-buttons';
    var currentPath = location.pathname;
    var html = '';
    for (var n = 0; n < navItems.length; n++) {
      var item = navItems[n];
      var href = prefix + item.href;
      // active判定: パスの末尾がhrefと一致するか
      var isActive = false;
      if (item.href === 'index.html') {
        isActive = currentPath === '/' || currentPath.endsWith('/index.html') || currentPath.endsWith('/');
        // サブディレクトリのindex.htmlは除外
        if (prefix !== '' && currentPath.endsWith('/index.html')) {
          isActive = false;
        }
      } else {
        isActive = currentPath.endsWith('/' + item.href) || currentPath.endsWith('/' + item.href.replace('index.html', ''));
      }
      var activeCls = isActive ? ' active' : '';
      html += '<a href="' + href + '" class="nav-btn ' + item.cls + activeCls + '">' + item.emoji + ' ' + item.label + '</a>';
    }
    navEl.innerHTML = html;
  }

  // --- フッター ---
  var footerEl = document.getElementById('common-footer');
  if (footerEl) {
    footerEl.className = 'common-footer';
    var footerLinks = [
      { label: 'シングル相場', href: 'report.html' },
      { label: '未開封BOX', href: 'box.html' },
      { label: '記事一覧', href: 'articles/index.html' },
      { label: '使い方ガイド', href: 'guide.html' },
      { label: 'このサイトについて', href: 'about.html' },
      { label: 'プライバシーポリシー', href: 'privacy.html' },
      { label: 'ポケカ指数', href: 'index-chart.html' },
      { label: 'お問い合わせ', href: 'contact.html' },
      { label: '持ってるリスト管理', href: 'portfolio.html' }
    ];
    var fhtml = '';
    for (var f = 0; f < footerLinks.length; f++) {
      fhtml += '<a href="' + prefix + footerLinks[f].href + '">' + footerLinks[f].label + '</a>';
    }
    fhtml += '<p>© 2026 ポケカるっく</p>';
    footerEl.innerHTML = fhtml;
  }
})();
