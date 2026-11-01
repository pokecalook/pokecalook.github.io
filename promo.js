/**
 * promo.js - ポケカるっく プロモーション挿入スクリプト
 * - PC: 両サイドstickyバナー（300x250 + 160x600/120x600 縦長）
 * - PC: ヘッダー下/フッター上に横長バナー（728x90）
 * - スマホ: カード/BOX一覧のアイテム間にバナー挿入
 * - 全デバイス: オリくじポップアップ（600x600、1セッション1回、ランダム確率）
 */
(function(){
  var prefix = '';
  if(location.pathname.indexOf('/cards/')===0 || location.pathname.indexOf('/box/')===0 || location.pathname.indexOf('/articles/')===0){
    prefix = '../';
  }

  // --- バナーデータ ---
  // 300x250 (サイド用 + スマホインライン用)
  var sq = [
    {img: prefix+'images/ptn-1.gif', link: prefix+'go/extoreca.html', w:300, h:250},
    {img: prefix+'images/ptn-2.gif', link: prefix+'go/dokkan.html', w:300, h:250},
    {img: prefix+'images/ptn-4.gif', link: prefix+'go/penguin.html', w:300, h:250},
    {img: prefix+'images/ptn-8.gif', link: prefix+'go/ptn8.html', w:300, h:250}
  ];
  // 728x90 (横長: ヘッダー下/フッター上)
  var hz = [
    {img: prefix+'images/ptn-5.gif', link: prefix+'go/ptn5.html', w:728, h:90},
    {img: prefix+'images/ptn-6.gif', link: prefix+'go/ptn6.html', w:728, h:90},
    {img: prefix+'images/ptn-7.gif', link: prefix+'go/ptn7.html', w:728, h:90}
  ];
  // 縦長 (サイド用)
  var vt = [
    {img: prefix+'images/ptn-9.gif', link: prefix+'go/ptn9.html', w:160, h:600},
    {img: prefix+'images/ptn-10.gif', link: prefix+'go/ptn10.html', w:120, h:600}
  ];


  function pick(arr){ return arr[Math.floor(Math.random()*arr.length)]; }

  function makeImg(b, style){
    return '<a href="'+b.link+'" rel="nofollow" target="_blank"><img src="'+b.img+'" width="'+b.w+'" height="'+b.h+'" alt="" loading="lazy" style="'+(style||'max-width:100%;height:auto;display:block')+'"></a>';
  }

  // --- PC: 横長バナー（ヘッダー下 + フッター上） ---
  function insertHorizontalBanners(){
    if(window.innerWidth < 768) return;
    // ヘッダー下
    var header = document.querySelector('.hdr') || document.querySelector('header');
    if(header){
      var b = pick(hz);
      var el = document.createElement('div');
      el.className = 'ptn-hz ptn-hz-top';
      el.innerHTML = makeImg(b, 'max-width:100%;height:auto;display:block;margin:0 auto;border-radius:4px');
      header.parentNode.insertBefore(el, header.nextSibling);
    }
    // フッター上
    var footer = document.querySelector('.common-footer') || document.querySelector('footer');
    if(footer){
      var b2 = pick(hz);
      var el2 = document.createElement('div');
      el2.className = 'ptn-hz ptn-hz-bottom';
      el2.innerHTML = makeImg(b2, 'max-width:100%;height:auto;display:block;margin:0 auto;border-radius:4px');
      footer.parentNode.insertBefore(el2, footer);
    }
  }

  // --- PC: 両サイドstickyバナー（縦長 + 正方形） ---
  function insertSideBanners(){
    if(window.innerWidth < 1200) return;
    // 左サイド: 縦長
    var v1 = pick(vt);
    var leftEl = document.createElement('div');
    leftEl.className = 'ptn-side ptn-side-l';
    leftEl.innerHTML = makeImg(v1, 'display:block;border-radius:6px');
    document.body.appendChild(leftEl);

    // 右サイド: 縦長
    var v2 = pick(vt);
    var rightEl = document.createElement('div');
    rightEl.className = 'ptn-side ptn-side-r';
    rightEl.innerHTML = makeImg(v2, 'display:block;border-radius:6px');
    document.body.appendChild(rightEl);

    // 余裕があれば正方形も追加（1400px以上）
    if(window.innerWidth >= 1400){
      var s1 = pick(sq);
      var leftSq = document.createElement('div');
      leftSq.className = 'ptn-side-sq ptn-side-sq-l';
      leftSq.innerHTML = makeImg(s1, 'display:block;border-radius:6px;margin-top:12px');
      document.body.appendChild(leftSq);

      var s2 = pick(sq);
      var rightSq = document.createElement('div');
      rightSq.className = 'ptn-side-sq ptn-side-sq-r';
      rightSq.innerHTML = makeImg(s2, 'display:block;border-radius:6px;margin-top:12px');
      document.body.appendChild(rightSq);
    }
  }

  // --- スマホ: アイテム間バナー挿入 ---
  function insertMobileBanners(){
    if(window.innerWidth >= 768) return;
    var container = document.querySelector('.cards') || document.getElementById('box-grid');
    if(!container) return;

    if(container.id === 'box-grid'){
      var boxObserver = new MutationObserver(function(){
        if(container.children.length >= 6){
          boxObserver.disconnect();
          doInsert(container);
        }
      });
      boxObserver.observe(container, {childList:true});
      if(container.children.length >= 6){
        boxObserver.disconnect();
        doInsert(container);
      }
    } else {
      doInsert(container);
    }
  }

  function doInsert(container){
    var items = container.children;
    if(!items || items.length < 6) return;
    var inserted = 0;
    for(var i = 4; i < items.length; i += 6){
      var b = pick(sq);
      var slot = document.createElement('div');
      slot.className = 'ptn-inline';
      if(container.id === 'box-grid'){
        slot.className = 'ptn-inline box-grid-slot';
        slot.style.gridColumn = '1 / -1';
      }
      slot.innerHTML = makeImg(b, 'max-width:100%;height:auto;display:block;margin:0 auto;border-radius:8px');
      var refNode = items[i + inserted];
      if(refNode){
        container.insertBefore(slot, refNode);
        inserted++;
      }
      if(inserted >= 3) break;
    }
  }



  // --- CSS ---
  function injectStyles(){
    var css = ''
      + '.ptn-hz{text-align:center;padding:10px 0;}'
      + '.ptn-side{position:fixed;top:50%;z-index:50;}'
      + '.ptn-side-l{left:10px;transform:translateY(-50%);}'
      + '.ptn-side-r{right:10px;transform:translateY(-50%);}'
      + '.ptn-side img{box-shadow:0 2px 12px rgba(0,0,0,.1);}'
      + '.ptn-side-sq{position:fixed;z-index:50;}'
      + '.ptn-side-sq-l{left:10px;top:calc(50% + 320px);}'
      + '.ptn-side-sq-r{right:10px;top:calc(50% + 320px);}'
      + '.ptn-side-sq img{box-shadow:0 2px 12px rgba(0,0,0,.1);}'
      + '.ptn-inline{padding:12px 0;text-align:center;}'

      + '@media(max-width:1199px){.ptn-side,.ptn-side-sq{display:none !important;}}'
      + '@media(max-width:767px){.ptn-hz{display:none !important;}.ptn-inline{margin:8px 0;}}';
    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
  }

  // --- 実行 ---
  function init(){
    injectStyles();
    insertHorizontalBanners();
    insertSideBanners();

    if(document.readyState === 'complete'){
      insertMobileBanners();
    } else {
      window.addEventListener('load', insertMobileBanners);
    }
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
