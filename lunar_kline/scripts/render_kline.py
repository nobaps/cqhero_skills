#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K 线图渲染（自包含单文件 HTML，零外部依赖，多窗格交互）。

交互设计（v0.6.0）:
  1. 级别切换：年K / 月K / 日K
  2. 点击下钻：月K 点某月 / 年K 点某年 → 展开内部日K
  3. 滚轮缩放（光标锚点）/ Shift+拖拽平移（或中键）/ 双击复位
  4. 悬停**竖排**提示：OHLCV 逐行显示
  5. **框选区间统计**：左键拖拽框选一段 → 统计该段（精确到柱），并高亮选区
  6. **成交量窗格**：价格图下方绘制成交量柱（红涨绿跌），与 K 线共享横轴（v0.6.0）
  7. **MACD 窗格**：DIF / DEA / 柱 三线，参数 12,26,9，共享横轴（v0.6.0）
  8. 横轴标签一律干支：年K=干支年、月K=干支月、日K=干支日

契约:
    python render_kline.py <input.json> <output.html>

input.json 结构:
    {
      "name": "标的名",
      "calendar_spec": "口径描述",          # 必填
      "bars":       [...],                  # 日K（原始）
      "years":      [...],                  # 干支年K
      "months":     [...],                  # 干支月K
    }
每个 bar: {date, label, axis_label?, open, high, low, close, volume,
           gz_year?, gz_month?, gz_day?, start?, end?}
输出: 单文件 HTML（内联数据 + 内联 SVG），可离线打开。
红线: 不含买卖建议 / 目标价 / 预测；图内强制附口径声明与免责声明。
"""

import sys
import os
import json
import html

DISCLAIMER = "本图仅为历史数据的整理与可视化，不构成任何投资建议，不含买卖时点或涨跌预测。"


def _esc(s):
    return html.escape(str(s), quote=True)


def _validate(data):
    if not isinstance(data, dict):
        raise ValueError("BAD_INPUT: 根节点应为对象")
    if not data.get("calendar_spec"):
        raise ValueError("MISSING_SPEC: calendar_spec 为必填——图脱离口径无意义")
    bars = data.get("bars")
    if not isinstance(bars, list) or not bars:
        raise ValueError("BAD_INPUT: bars 缺失或为空，无法绘图")
    for i, b in enumerate(bars):
        for k in ("date", "open", "high", "low", "close"):
            if k not in b:
                raise ValueError("BAD_INPUT: bars[%d] 缺少字段 %s" % (i, k))
        if float(b["high"]) < float(b["low"]):
            raise ValueError("BAD_INPUT: bars[%d] high < low" % i)
    return bars


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__NAME__ · 干支K线图</title>
<style>
  :root{--up:#d94b4b;--dn:#3fa66a;--line:#e6e8eb;--txt:#222;--mut:#666;--acc:#2f5bd0;}
  *{box-sizing:border-box;}
  body{margin:0;padding:24px 16px;background:#f7f8fa;color:var(--txt);
       font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;}
  .card{max-width:1060px;margin:0 auto;background:#fff;border:1px solid var(--line);
        border-radius:10px;padding:20px 24px;}
  h1{font-size:18px;margin:0 0 12px;}
  .tabs{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center;}
  .tab{padding:6px 18px;border:1px solid var(--line);background:#fff;border-radius:6px;
       cursor:pointer;font-size:13px;color:#444;transition:.15s;}
  .tab:hover{border-color:#b9c6e0;}
  .tab.on{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600;}
  .btn{padding:6px 12px;border:1px solid var(--line);background:#fff;border-radius:6px;
       cursor:pointer;font-size:12px;color:#555;}
  .btn:hover{border-color:#b9c6e0;color:var(--acc);}
  .crumb{margin-left:auto;font-size:12px;color:var(--mut);}
  .crumb b{color:var(--acc);cursor:pointer;}
  .chartwrap{position:relative;cursor:crosshair;user-select:none;-webkit-user-select:none;}
  .hint{font-size:12px;color:var(--mut);margin-top:6px;min-height:18px;line-height:1.7;}
  .hint b{color:var(--acc);}
  .meta{font-size:12px;color:var(--mut);margin:10px 0 0;line-height:1.7;}
  .meta b{color:#333;}
  .stats{margin-top:12px;border:1px solid var(--line);border-radius:8px;
         padding:12px 14px;background:#fbfcfe;}
  .stats.sel{border-color:#b9c9f2;background:#f5f8ff;}
  .st-h{font-size:13px;font-weight:600;margin-bottom:10px;}
  .st-sub{font-size:11px;color:var(--mut);font-weight:400;margin-left:6px;}
  .st-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px 16px;}
  .st-cell{font-size:12px;color:var(--mut);line-height:1.5;}
  .st-cell b{display:block;color:#222;font-size:13px;font-weight:600;
             font-variant-numeric:tabular-nums;word-break:break-all;}
  .tip{position:absolute;display:none;z-index:9;background:rgba(20,26,38,.94);color:#eef2f8;
       border-radius:6px;padding:8px 11px;font-size:12px;line-height:1.75;pointer-events:none;
       box-shadow:0 4px 16px rgba(0,0,0,.28);white-space:nowrap;}
  .tip .tk{font-weight:600;margin-bottom:5px;color:#cfe0ff;letter-spacing:.3px;}
  .tip .tr{display:flex;justify-content:space-between;gap:20px;}
  .tip .tr span{color:#9fb0c8;}
  .tip .tr b{font-variant-numeric:tabular-nums;}
  .tip hr{border:0;border-top:1px solid rgba(255,255,255,.14);margin:5px 0;}
  .spec{margin-top:14px;padding:10px 12px;background:#f2f6ff;border-left:3px solid #4a6fd9;
        font-size:12px;color:#33456b;border-radius:4px;}
  .disc{margin-top:10px;padding:10px 12px;background:#fff8f2;border-left:3px solid #d98f4a;
        font-size:12px;color:#7a5220;border-radius:4px;}
  .lg{font-size:12px;color:var(--mut);margin-top:8px;line-height:1.9;}
  .up{color:var(--up);font-weight:600;} .dn{color:var(--dn);font-weight:600;}
  .empty{padding:40px;text-align:center;color:var(--mut);font-size:13px;}
</style>
</head>
<body>
<div class="card">
  <h1>__NAME__</h1>
  <div class="tabs">
    <button class="tab" data-lv="year">年K（干支年）</button>
    <button class="tab on" data-lv="month">月K（干支月）</button>
    <button class="tab" data-lv="day">日K</button>
    <button class="btn" id="clearSel">清除框选</button>
    <span class="crumb" id="crumb"></span>
  </div>
  <div class="chartwrap" id="chartwrap">
    <div id="chart"></div>
    <div class="tip" id="tip"></div>
  </div>
  <div class="hint" id="hint"></div>
  <div class="meta" id="meta"></div>
  <div class="stats" id="stats"></div>
  <div class="lg">颜色惯例：<span class="up">红=收涨</span>　<span class="dn">绿=收跌</span>（成交量同色）　｜　
    <b>左键拖拽=框选区间统计</b> · <b>Shift+拖拽=平移</b> · 滚轮=缩放 · 双击=复位 · 单击空白=清除框选　｜　
    点击柱子可下钻日K　｜　横轴：年K=干支年／月K=干支月／日K=干支日</div>
  <div class="spec"><b>本次所用口径：</b>__SPEC__</div>
  <div class="disc"><b>免责声明：</b>__DISC__</div>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  var D = JSON.parse(document.getElementById('data').textContent);
  var W=980, padL=56, padR=16, PLOTW=W-padL-padR;
  var PRICE={top:20, h:268};   PRICE.bot=PRICE.top+PRICE.h;
  var VOL={top:300, h:64};     VOL.bot=VOL.top+VOL.h;
  var MACD={top:376, h:84};    MACD.bot=MACD.top+MACD.h;
  var H=508;
  var LV = {year: D.years||[], month: D.months||[], day: D.bars||[]};
  var LABEL = {year:'年K（干支年）', month:'月K（干支月）', day:'日K'};

  // 日K 按干支月 / 干支年 分组，用于下钻。
  // 干支月名会跨年重复（丙子月每年都有），必须用「干支年+干支月」作唯一键。
  var dayByMonth = {}, dayByYear = {};
  function mkey(b){ return (b.gz_year||'') + (b.gz_month||''); }
  (D.bars||[]).forEach(function(b){
    if(b.gz_month){ var k=mkey(b); (dayByMonth[k]=dayByMonth[k]||[]).push(b); }
  });
  (D.bars||[]).forEach(function(b){
    if(b.gz_year) (dayByYear[b.gz_year]=dayByYear[b.gz_year]||[]).push(b);
  });

  var state = {level:'month', drill:null, win:null, sel:null};

  var wrapEl  = document.getElementById('chartwrap');
  var chartEl = document.getElementById('chart');
  var tipEl   = document.getElementById('tip');

  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function fmt(v){ return (Math.round(v*100)/100).toFixed(2); }
  function fmtSigned(v){ return (v>=0?'+':'')+fmt(v); }
  function fmtVol(v){
    v = +v || 0;
    if(v>=1e8) return (v/1e8).toFixed(2)+'亿';
    if(v>=1e4) return (v/1e4).toFixed(2)+'万';
    return String(Math.round(v));
  }
  function axLab(b){ return b.axis_label || b.label || b.date; }

  // ---- MACD(12,26,9)：对当前级别的收盘序列计算 ----
  function ema(arr, p){
    var k=2/(p+1), out=[], prev=null;
    for(var i=0;i<arr.length;i++){
      prev = (prev===null) ? arr[i] : (arr[i]*k + prev*(1-k));
      out.push(prev);
    }
    return out;
  }
  function macdSeries(bars){
    var c=bars.map(function(b){ return +b.close; });
    var e12=ema(c,12), e26=ema(c,26), dif=[], dea, hist=[];
    for(var i=0;i<c.length;i++) dif.push(e12[i]-e26[i]);
    dea=ema(dif,9);
    for(i=0;i<dif.length;i++) hist.push(2*(dif[i]-dea[i]));
    return {dif:dif, dea:dea, hist:hist, ready:c.length>=35};
  }

  function cur(){ return state.drill ? state.drill.bars : LV[state.level]; }
  function winIdx(){
    var n = cur().length;
    if(!state.win) return {i0:0, i1:n};
    var i0 = Math.max(0, Math.min(state.win.i0, n-1));
    var i1 = Math.max(i0+1, Math.min(state.win.i1, n));
    return {i0:i0, i1:i1};
  }
  function visible(){ var w=winIdx(); return cur().slice(w.i0, w.i1); }

  function xAt(i, slot){ return padL + slot*(i+0.5); }

  function svg(bars, mac, offset, selLocal){
    var n=bars.length;
    if(!n) return '<div class="empty">该区间无数据</div>';
    var i, b;
    var vmax=-Infinity, vmin=Infinity, vmaxV=0;
    for(i=0;i<n;i++){ b=bars[i];
      if(+b.high>vmax) vmax=+b.high;
      if(+b.low<vmin) vmin=+b.low;
      if((+b.volume||0)>vmaxV) vmaxV=+b.volume||0; }
    if(vmax===vmin){ vmax+=1; vmin-=1; }
    var padP=(vmax-vmin)*0.04; vmax+=padP; vmin-=padP;
    function yP(v){ return PRICE.top + PRICE.h*(vmax-v)/(vmax-vmin); }
    function yV(v){ return VOL.top + VOL.h*(1 - (vmaxV? v/vmaxV : 0)); }

    var mMax=0;
    for(i=0;i<n;i++){
      mMax=Math.max(mMax, Math.abs(+mac.dif[i]||0), Math.abs(+mac.dea[i]||0),
                    Math.abs(+mac.hist[i]||0));
    }
    if(!mMax) mMax=1;
    function yM(v){ return MACD.top + MACD.h/2 - (v/mMax)*(MACD.h/2 - 4); }

    var slot=PLOTW/Math.max(n,1), bw=Math.max(1, slot*0.62);
    var s=[];
    s.push('<rect x="0" y="0" width="'+W+'" height="'+H+'" fill="#ffffff"/>');

    // 选区高亮带（置于最底层）
    if(selLocal){
      var sx1=padL+slot*selLocal.a, sx2=padL+slot*selLocal.b;
      s.push('<rect data-role="sel" x="'+sx1.toFixed(1)+'" y="'+PRICE.top+'" width="'+
             Math.max(1,sx2-sx1).toFixed(1)+'" height="'+(MACD.bot-PRICE.top)+
             '" fill="#2f5bd0" opacity="0.07"/>');
    }

    // ---- 价格窗格 ----
    for(i=0;i<5;i++){
      var pv=vmin+(vmax-vmin)*i/4, yy=yP(pv);
      s.push('<line x1="'+padL+'" y1="'+yy.toFixed(1)+'" x2="'+(W-padR)+'" y2="'+yy.toFixed(1)+
             '" stroke="#ececec" stroke-width="1"/>');
      s.push('<text x="'+(padL-6)+'" y="'+(yy+4).toFixed(1)+'" font-size="11" fill="#888" '+
             'text-anchor="end">'+pv.toFixed(2)+'</text>');
    }
    for(i=0;i<n;i++){
      b=bars[i];
      var cx=xAt(i,slot), o=+b.open, h=+b.high, l=+b.low, c=+b.close;
      var up=c>=o, col=up?'#d94b4b':'#3fa66a';
      var clickable=(state.level!=='day' && !state.drill && (b.gz_month||b.gz_year));
      s.push('<line x1="'+cx.toFixed(1)+'" y1="'+yP(h).toFixed(1)+'" x2="'+cx.toFixed(1)+
             '" y2="'+yP(l).toFixed(1)+'" stroke="'+col+'" stroke-width="1"/>');
      var yo=yP(o), yc=yP(c), top=Math.min(yo,yc), bh=Math.max(1,Math.abs(yc-yo));
      s.push('<rect data-role="candle" x="'+(cx-bw/2).toFixed(1)+'" y="'+top.toFixed(1)+
             '" width="'+bw.toFixed(1)+'" height="'+bh.toFixed(1)+'" fill="'+col+'"'+
             (clickable?' style="cursor:pointer" data-click="'+(offset+i)+'"':'')+'/>');
    }
    s.push('<line x1="'+padL+'" y1="'+PRICE.top+'" x2="'+padL+'" y2="'+PRICE.bot+
           '" stroke="#bbb" stroke-width="1"/>');

    // ---- 成交量窗格 ----
    s.push('<text x="'+(padL+4)+'" y="'+(VOL.top+11)+'" font-size="10" fill="#999">成交量（手）</text>');
    s.push('<line x1="'+padL+'" y1="'+VOL.bot+'" x2="'+(W-padR)+'" y2="'+VOL.bot+
           '" stroke="#e6e6e6" stroke-width="1"/>');
    s.push('<text x="'+(padL-6)+'" y="'+(VOL.top+10)+'" font-size="10" fill="#999" '+
           'text-anchor="end">'+fmtVol(vmaxV)+'</text>');
    s.push('<line x1="'+padL+'" y1="'+VOL.top+'" x2="'+padL+'" y2="'+VOL.bot+
           '" stroke="#bbb" stroke-width="1"/>');
    for(i=0;i<n;i++){
      b=bars[i];
      var vv=+b.volume||0, vx=xAt(i,slot), vy=yV(vv), vh=Math.max(0.6, VOL.bot-vy);
      var vcol=(+b.close>=+b.open)?'#d94b4b':'#3fa66a';
      s.push('<rect data-role="vol" x="'+(vx-bw/2).toFixed(1)+'" y="'+vy.toFixed(1)+
             '" width="'+bw.toFixed(1)+'" height="'+vh.toFixed(1)+'" fill="'+vcol+
             '" opacity="0.75"/>');
    }

    // ---- MACD 窗格 ----
    s.push('<text x="'+(padL+4)+'" y="'+(MACD.top+11)+'" font-size="10" fill="#999">'+
           'MACD(12,26,9)'+(mac.ready?'':' · 样本偏少，仅供参考')+'</text>');
    s.push('<line x1="'+padL+'" y1="'+yM(0).toFixed(1)+'" x2="'+(W-padR)+'" y2="'+yM(0).toFixed(1)+
           '" stroke="#e0e0e0" stroke-width="1"/>');
    s.push('<line x1="'+padL+'" y1="'+MACD.top+'" x2="'+padL+'" y2="'+MACD.bot+
           '" stroke="#bbb" stroke-width="1"/>');
    s.push('<line x1="'+padL+'" y1="'+MACD.bot+'" x2="'+(W-padR)+'" y2="'+MACD.bot+
           '" stroke="#bbb" stroke-width="1"/>');
    for(i=0;i<n;i++){
      var hh=+mac.hist[i]||0, hx=xAt(i,slot), hy=yM(hh), hz=yM(0);
      var hcol=(hh>=0)?'#d94b4b':'#3fa66a';
      s.push('<rect data-role="macd" x="'+(hx-Math.max(1,bw*0.5)/2).toFixed(1)+
             '" y="'+Math.min(hy,hz).toFixed(1)+'" width="'+Math.max(1,bw*0.5).toFixed(1)+
             '" height="'+Math.max(0.6,Math.abs(hz-hy)).toFixed(1)+'" fill="'+hcol+
             '" opacity="0.8"/>');
    }
    function line(role, arr, color){
      var pts=[];
      for(var j=0;j<n;j++) pts.push(xAt(j,slot).toFixed(1)+','+yM(+arr[j]||0).toFixed(1));
      return '<polyline data-role="'+role+'" points="'+pts.join(' ')+'" fill="none" stroke="'+
             color+'" stroke-width="1.2"/>';
    }
    s.push(line('dea', mac.dea, '#e0a030'));
    s.push(line('dif', mac.dif, '#2f5bd0'));

    // ---- 共享横轴（干支标签）----
    var step=Math.max(1, Math.ceil(n/12));
    for(i=0;i<n;i+=step){
      var lx=xAt(i,slot), lab=String(axLab(bars[i]));
      if(lab.length<=3 && /^[\\u4e00-\\u9fff]+$/.test(lab)){
        for(var q=0;q<lab.length;q++)
          s.push('<text x="'+lx.toFixed(1)+'" y="'+(MACD.bot+16+q*11)+'" font-size="10" '+
                 'fill="#666" text-anchor="middle">'+esc(lab[q])+'</text>');
      } else {
        s.push('<text x="'+lx.toFixed(1)+'" y="'+(MACD.bot+16)+'" font-size="10" fill="#666" '+
               'text-anchor="middle">'+esc(lab)+'</text>');
      }
    }
    return '<svg viewBox="0 0 '+W+' '+H+'" width="100%" preserveAspectRatio="xMidYMid meet">'+
           s.join('')+'</svg>';
  }

  function metaText(bars, mac){
    if(!bars.length) return '';
    var f=bars[0], l=bars[bars.length-1];
    return '当前周期：<b>'+LABEL[state.level]+'</b> ｜ 可见区间：<b>'+
      esc(f.start||f.date)+' ~ '+esc(l.end||l.date)+'</b> ｜ 样本：<b>'+bars.length+'</b>'+
      ' ｜ MACD 末值 DIF <b>'+fmt(mac.dif[mac.dif.length-1]||0)+'</b> / DEA <b>'+
      fmt(mac.dea[mac.dea.length-1]||0)+'</b>';
  }

  // ---- 区间统计：框选优先，其次可见区间；基于日线口径 ----
  function statsHTML(bars){
    if(!bars.length) return '';
    var f=bars[0], l=bars[bars.length-1];
    var s=f.start||f.date, e=l.end||l.date;
    var daily=(D.bars||[]).filter(function(b){ return b.date>=s && b.date<=e; });
    if(!daily.length) return '';
    var o=+daily[0].open, c=+daily[daily.length-1].close;
    var hi=-Infinity, lo=Infinity, hiD='', loD='', vol=0, up=0, i;
    for(i=0;i<daily.length;i++){
      var b=daily[i];
      if(+b.high>hi){ hi=+b.high; hiD=b.date; }
      if(+b.low<lo){ lo=+b.low; loD=b.date; }
      vol += (+b.volume||0);
      if(+b.close >= +b.open) up++;
    }
    var chg=c-o, pct=(c/o-1)*100, amp=(hi-lo)/lo*100;
    var cls=chg>=0?'up':'dn';
    var scope = state.sel ? ('框选 '+bars.length+' 根') : ('可见区间 '+bars.length+' 根');
    function cell(k,v){ return '<div class="st-cell">'+k+'<b>'+v+'</b></div>'; }
    return '<div class="st-h">区间统计 <span class="st-sub">（'+scope+'；基于日线口径'+
      (state.sel?'；单击空白或「清除框选」取消':'')+'）</span></div>'+
      '<div class="st-grid">'+
        cell('区间', esc(s)+' ~ '+esc(e))+
        cell('交易日', daily.length+' 天')+
        cell('起始开盘', fmt(o))+
        cell('结束收盘', fmt(c))+
        cell('区间涨跌', '<span class="'+cls+'">'+fmtSigned(chg)+'（'+fmtSigned(pct)+'%）</span>')+
        cell('最高 '+esc(hiD), fmt(hi))+
        cell('最低 '+esc(loD), fmt(lo))+
        cell('振幅', amp.toFixed(2)+'%')+
        cell('累计成交量', fmtVol(vol)+'手')+
        cell('阳/阴线', up+' / '+(daily.length-up))+
      '</div>';
  }

  function showTip(b, ev){
    var wr=wrapEl.getBoundingClientRect();
    var x=ev.clientX-wr.left, y=ev.clientY-wr.top;
    var head=esc(b.date)+'　'+esc((b.gz_year||'')+(b.gz_month?b.gz_month+'月':''))+
             (b.gz_day?(' '+esc(b.gz_day)+'日'):'');
    tipEl.innerHTML =
      '<div class="tk">'+head+'</div>'+
      '<div class="tr"><span>开</span><b>'+fmt(+b.open)+'</b></div>'+
      '<div class="tr"><span>高</span><b>'+fmt(+b.high)+'</b></div>'+
      '<div class="tr"><span>低</span><b>'+fmt(+b.low)+'</b></div>'+
      '<div class="tr"><span>收</span><b>'+fmt(+b.close)+'</b></div>'+
      '<div class="tr"><span>量</span><b>'+fmtVol(+b.volume||0)+'手</b></div>';
    tipEl.style.display='block';
    var tw=tipEl.offsetWidth||170, th=tipEl.offsetHeight||130;
    var left=x+16, top=y+14;
    if(x > wr.width-tw-24) left=x-tw-16;
    if(y > wr.height-th-8) top=y-th-14;
    tipEl.style.left=Math.max(0,left)+'px';
    tipEl.style.top=Math.max(0,top)+'px';
  }
  function hideTip(){ tipEl.style.display='none'; }

  function render(){
    var base=cur(), w=winIdx(), vis=base.slice(w.i0, w.i1);
    var macFull=macdSeries(base);
    var mac={dif:macFull.dif.slice(w.i0,w.i1), dea:macFull.dea.slice(w.i0,w.i1),
             hist:macFull.hist.slice(w.i0,w.i1), ready:macFull.ready};
    var selLocal=null;
    if(state.sel){
      var a=state.sel.i0-w.i0, b=state.sel.i1-w.i0;
      if(!(b<=0 || a>=vis.length)){
        selLocal={a:Math.max(0,a), b:Math.min(vis.length,b)};
      }
    }
    chartEl.innerHTML = svg(vis, mac, w.i0, selLocal);
    document.getElementById('meta').innerHTML = metaText(vis, mac);
    var st=document.getElementById('stats');
    st.innerHTML = statsHTML(state.sel ? base.slice(state.sel.i0, state.sel.i1) : vis);
    st.className = 'stats' + (state.sel ? ' sel' : '');

    var crumb=document.getElementById('crumb'), hint=document.getElementById('hint');
    if(state.drill){
      crumb.innerHTML='<b id="back">← 返回'+esc(state.drill.fromLabel)+'</b>';
      hint.innerHTML='正在查看 <b>'+esc(state.drill.title)+'</b> 的日K（横轴为干支日）';
      var bk=document.getElementById('back');
      if(bk) bk.onclick=function(){ state.drill=null; state.win=null; state.sel=null; render(); };
    } else {
      crumb.innerHTML='';
      hint.innerHTML = (state.level==='day')
        ? '日K视图：每根柱为一个交易日（横轴为干支日）'
        : '<b>点击任意柱子</b>可下钻查看该周期内的日K';
    }
    if(state.sel){
      hint.innerHTML += ' ｜ <b class="sel">已框选 '+ (state.sel.i1-state.sel.i0) +' 根</b>';
    } else if(w.i1-w.i0 < base.length){
      hint.innerHTML += ' ｜ <b>已放大 '+ (w.i1-w.i0) +'/'+ base.length +'</b>';
    }
    hint.innerHTML += ' ｜ 左键拖拽框选 · Shift+拖拽平移 · 滚轮缩放 · 双击复位';

    var tabs=document.querySelectorAll('.tab');
    for(var i=0;i<tabs.length;i++)
      tabs[i].classList.toggle('on', !state.drill && tabs[i].dataset.lv===state.level);
  }

  // ---- 几何：由鼠标 x 求可见序号 / 基准序号 ----
  function kScale(){ var cw=chartEl.clientWidth||W; return cw/W; }
  function localIdx(clientX){
    var rect=chartEl.getBoundingClientRect(), k=kScale();
    var vx=(clientX-rect.left)/k, vis=visible(), slot=PLOTW/Math.max(vis.length,1);
    var i=Math.floor((vx-padL)/slot);
    return Math.max(0, Math.min(vis.length-1, i));
  }
  function baseIdx(clientX){ return winIdx().i0 + localIdx(clientX); }

  function zoomAt(vx, factor){
    var n=cur().length, w=winIdx(), count=w.i1-w.i0;
    var nc=Math.max(5, Math.min(n, Math.round(count*factor)));
    if(nc===count) return;
    var slot=PLOTW/count;
    var frac=(vx-padL)/slot; frac=Math.max(0, Math.min(count, frac));
    var anchor=w.i0+frac;
    var ni=Math.round(anchor - frac*nc/count);
    ni=Math.max(0, Math.min(n-nc, ni));
    state.win={i0:ni, i1:ni+nc};
    render();
  }

  // ---- 事件 ----
  var tabs=document.querySelectorAll('.tab');
  for(var ti=0; ti<tabs.length; ti++){
    (function(t){
      t.onclick=function(){ state.level=t.dataset.lv; state.drill=null; state.win=null; state.sel=null; render(); };
    })(tabs[ti]);
  }
  var csBtn=document.getElementById('clearSel');
  if(csBtn) csBtn.onclick=function(){ state.sel=null; render(); };

  var drag=null, dragged=false;

  chartEl.addEventListener('click', function(e){
    if(dragged){ dragged=false; return; }
    var el = (e.target && e.target.closest) ? e.target.closest('[data-click]') : null;
    if(el){
      var idx=+el.getAttribute('data-click'), bar=cur()[idx];
      if(!bar) return;
      var bars=null, title='';
      if(state.level==='month' && bar.gz_month){
        bars=dayByMonth[(bar.gz_year||'')+(bar.gz_month||'')]||null;
        title=(bar.gz_year||'')+(bar.gz_month||'')+'月';
      } else if(state.level==='year' && bar.gz_year){
        bars=dayByYear[bar.gz_year]||null;
        title=(bar.gz_year||'')+'年';
      }
      if(!bars || !bars.length) return;
      bars=bars.slice().sort(function(a,b){ return a.date<b.date?-1:1; });
      state.drill={bars:bars, title:title, fromLabel:LABEL[state.level]};
      state.win=null; state.sel=null;
      render();
      return;
    }
    if(state.sel){ state.sel=null; render(); }   // 单击空白 -> 清除框选
  });

  wrapEl.addEventListener('mousedown', function(e){
    if(e.button!==0) return;
    var mode = e.shiftKey ? 'pan' : 'sel';
    drag={x:e.clientX, mode:mode, i0:winIdx().i0,
          anchor:(mode==='sel') ? baseIdx(e.clientX) : 0};
    if(mode==='sel') hideTip();
  });
  wrapEl.addEventListener('mouseup', function(){ drag=null; });
  wrapEl.addEventListener('mouseleave', function(){ drag=null; hideTip(); });
  wrapEl.addEventListener('dblclick', function(){ state.win=null; state.sel=null; render(); });

  wrapEl.addEventListener('mousemove', function(e){
    if(drag){
      if(drag.mode==='pan'){
        var dx=e.clientX-drag.x;
        if(Math.abs(dx)>3) drag.moved=true;
        if(drag.moved){
          dragged=true;
          var n=cur().length, w0=winIdx(), count=w0.i1-w0.i0;
          var dvx=dx/kScale(), dslot=PLOTW/count;
          var di=Math.round(-dvx/dslot);
          var ni=Math.max(0, Math.min(n-count, drag.i0+di));
          if(ni!==w0.i0){ state.win={i0:ni, i1:ni+count}; render(); }
        }
      } else {   // 框选
        var cur2=baseIdx(e.clientX);
        var a=Math.min(drag.anchor, cur2), b=Math.max(drag.anchor, cur2);
        dragged=true;
        var ns={i0:a, i1:b+1};
        if(!state.sel || state.sel.i0!==ns.i0 || state.sel.i1!==ns.i1){
          state.sel=ns; render();
        }
      }
      return;
    }
    var visAll=visible(), m=visAll.length;
    if(!m){ hideTip(); return; }
    showTip(visAll[localIdx(e.clientX)], e);
  });

  wrapEl.addEventListener('wheel', function(e){
    if(e.preventDefault) e.preventDefault();
    if(cur().length<=1) return;
    var vx=(e.clientX-chartEl.getBoundingClientRect().left)/kScale();
    zoomAt(vx, (e.deltaY>0)?1.25:0.8);
  }, {passive:false});

  render();
})();
</script>
</body>
</html>"""


def render(data):
    bars = _validate(data)
    name = _esc(data.get("name", "未命名标的"))
    spec = _esc(data["calendar_spec"])
    payload = {
        "name": data.get("name", ""),
        "bars": bars,
        "years": data.get("years", []),
        "months": data.get("months", []),
    }
    # 内联 JSON 需转义 </script> 防截断
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")
    return (PAGE
            .replace("__NAME__", name)
            .replace("__SPEC__", spec)
            .replace("__DISC__", DISCLAIMER)
            .replace("__DATA__", blob))


def main(argv):
    if len(argv) < 3:
        sys.stderr.write("usage: render_kline.py <input.json> <output.html>\n")
        return 1
    src, dst = argv[1], argv[2]
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        sys.stderr.write("NO_DATA: 输入文件不存在 %s\n" % src)
        return 1
    except json.JSONDecodeError as e:
        sys.stderr.write("BAD_JSON: %s\n" % e.msg)
        return 1
    try:
        out = render(data)
    except ValueError as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(out)
    print("OK %s" % dst)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
