// 验证"渲染路径与交互"：在最小 DOM 桩里真实执行页面内联脚本，
// 派发鼠标事件，断言 SVG 结构、成交量/MACD 窗格、竖排提示、滚轮缩放、框选统计。
//
// 与 check_render.js 的分工：
//   check_render.js —— 校验内联**数据**与下钻**分组逻辑**
//   check_svg.js    —— 校验**交互与绘图**：执行页面脚本、派发事件、捕获输出
//   二者互补：数据对但图画不出/交互坏，只有本文件能发现。
//
// 不依赖浏览器（无需 Chromium）；只用 Node 内置 vm + 手写 DOM 桩。
//
// 用法:
//   node test/check_svg.js <generated.html>
// 端到端（离线，需先有 fixture）:
//   python scripts/render_kline.py test/fixtures/sample_payload.json /tmp/s.html
//   node test/check_svg.js /tmp/s.html
//
// 退出码: 全通过 0；任一失败 1；用法错误 2。

const fs = require('fs');
const vm = require('vm');

const path = process.argv[2];
if (!path) {
  console.error('usage: node check_svg.js <generated.html>');
  process.exit(2);
}
const html = fs.readFileSync(path, 'utf8');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`[PASS] ${name}`); }
  else { fail++; console.log(`[FAIL] ${name}  <- ${detail || ''}`); }
}
function done() {
  console.log('-'.repeat(64));
  console.log(`suite=svg assertions=${pass + fail} passed=${pass}`);
  if (fail) { console.log('EXIT 1'); process.exit(1); }
  console.log('EXIT 0 (全部通过)');
}

// --- 1. 抽出内联数据与页面脚本 ---
const mData = html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/);
check('内联数据块存在', !!mData);
let D = null;
if (mData) {
  try { D = JSON.parse(mData[1].replace(/<\\\//g, '</')); } catch (e) { /* 下方断言 */ }
}
check('内联数据可解析', !!D);

const mCode = html.match(/<script>\s*(\(function\(\)\{[\s\S]*?\}\)\(\);)\s*<\/script>/);
check('页面脚本存在', !!mCode);
if (!mData || !mCode || !D) { done(); }

// --- 2. 最小 DOM 桩（记录监听器，支持事件派发）---
function makeEl(id) {
  return {
    id, _html: '', _ls: {}, _attrs: {}, className: '',
    get textContent() { return id === 'data' ? mData[1].replace(/<\\\//g, '</') : ''; },
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
    style: {},
    clientWidth: 980, offsetWidth: 170, offsetHeight: 130,
    getBoundingClientRect() { return { left: 0, top: 0, width: 980, height: 508 }; },
    classList: { toggle() {}, add() {}, remove() {} },
    dataset: {},
    addEventListener(t, fn) { (this._ls[t] = this._ls[t] || []).push(fn); },
    set onclick(f) { this._oc = f; },
    getAttribute(k) { return this._attrs[k] || null; },
    setAttribute(k, v) { this._attrs[k] = v; },
    closest() { return null; },
    appendChild() {},
  };
}
const store = {};
const tabs = ['year', 'month', 'day'].map(lv => ({
  dataset: { lv }, classList: { toggle() {} }, set onclick(_f) {},
}));
const document = {
  getElementById(id) { return store[id] || (store[id] = makeEl(id)); },
  querySelectorAll(sel) { return sel === '.tab' ? tabs : []; },
  createElement(tag) { return makeEl('_' + tag); },
  addEventListener() {},
};
function fire(el, type, ev) {
  ((el && el._ls && el._ls[type]) || []).forEach(fn => fn(ev));
}

let execErr = null;
try {
  vm.runInContext(mCode[1], vm.createContext({ document, JSON, Math, console }),
                  { timeout: 5000 });
} catch (e) { execErr = e; }
check('页面脚本执行无异常', !execErr, execErr && execErr.message);

const chartEl = store['chart'] || makeEl('chart');
const wrapEl = store['chartwrap'] || makeEl('chartwrap');
const tipEl = store['tip'] || makeEl('tip');
const statEl = store['stats'] || makeEl('stats');
const hintEl = store['hint'] || makeEl('hint');
const cnt = (s, re) => (s.match(re) || []).length;
let svg = chartEl._html || '';

// --- 3. 默认月K视图的 SVG 断言 ---
const nM = D.months.length;
check('#chart 已写入内容', svg.length > 0);
check('写入的是 SVG 根元素', svg.startsWith('<svg'));
check('SVG 含三窗格 viewBox (0 0 980 508)', /viewBox="0 0 980 508"/.test(svg));
check('含红涨蜡烛 (#d94b4b)', svg.includes('#d94b4b'));
check('含绿跌蜡烛 (#3fa66a)', svg.includes('#3fa66a'));
check(`价格蜡烛数 = 月K数 (candle=${cnt(svg, /data-role="candle"/g)})`,
      cnt(svg, /data-role="candle"/g) === nM, `期望 ${nM}`);
check(`成交量柱数 = 月K数 (vol=${cnt(svg, /data-role="vol"/g)})`,
      cnt(svg, /data-role="vol"/g) === nM, `期望 ${nM}`);
check(`MACD 柱数 = 月K数 (macd=${cnt(svg, /data-role="macd"/g)})`,
      cnt(svg, /data-role="macd"/g) === nM, `期望 ${nM}`);
check('MACD 含 DIF 折线', /data-role="dif"/.test(svg));
check('MACD 含 DEA 折线', /data-role="dea"/.test(svg));
check('含「成交量」窗格标题', /成交量（手）/.test(svg));
check('含「MACD(12,26,9)」窗格标题', /MACD\(12,26,9\)/.test(svg));
check('默认无选区高亮带', !/data-role="sel"/.test(svg));
check(`含坐标轴文字标签 (text=${cnt(svg, /<text/g)})`, cnt(svg, /<text/g) > 0);
check('SVG 不含外部引用（自包含）', !/xlink:href|<image|url\(http/.test(svg));
const openTags = (svg.match(/<(?!\/)[a-zA-Z]/g) || []).length;
const closeTags = (svg.match(/<\/[a-zA-Z]+>/g) || []).length;
const selfClose = (svg.match(/\/>/g) || []).length;
check(`SVG 标签开闭配平 (${openTags}/${closeTags + selfClose})`,
      openTags === closeTags + selfClose);

// --- 4. 侧栏/提示渲染 ---
check('meta 含周期与 MACD 末值',
      /周期/.test(store['meta']._html) && /DIF/.test(store['meta']._html));
check('默认月K提示文案正确', /点击任意柱子/.test(hintEl._html));

// --- 5. 需求1：框选区间统计 ---
check('默认统计面板已渲染', /区间统计/.test(statEl._html) && /区间涨跌/.test(statEl._html));
check('统计含 交易日/最高/最低/累计成交量',
      ['交易日', '最高', '最低', '累计成交量'].every(k => statEl._html.includes(k)));
check('默认统计范围为「可见区间」', /可见区间/.test(statEl._html));

// 槽宽（默认全量月K）
const slotM = (980 - 56 - 16) / nM;
function xOf(i) { return 56 + slotM * (i + 0.5); }
fire(wrapEl, 'mousedown', { button: 0, shiftKey: false, clientX: xOf(2) });
fire(wrapEl, 'mousemove', { clientX: xOf(6) });
fire(wrapEl, 'mouseup', {});
const selSvg = chartEl._html || '';
check('框选后出现选区高亮带', /data-role="sel"/.test(selSvg));
check('框选后统计范围切换为「框选」', /框选 5 根/.test(statEl._html));
check('框选提示出现「已框选 5 根」', /已框选 5 根/.test(hintEl._html));
check('统计面板进入选中态样式', /(^|\s)sel(\s|$)/.test(statEl.className || ''));

// 双击复位应清除框选
fire(wrapEl, 'dblclick', {});
check('双击后清除框选', !/data-role="sel"/.test(chartEl._html || '') &&
      !/框选 5 根/.test(statEl._html));

// --- 6. 需求2：悬停竖排提示 ---
fire(wrapEl, 'mousemove', { clientX: xOf(3), clientY: 200, button: 0 });
const tip = tipEl._html || '';
check('悬停提示已生成', tip.length > 0);
check(`OHLCV 竖排为 5 行 (tr=${cnt(tip, /<div class="tr">/g)})`,
      cnt(tip, /<div class="tr">/g) === 5, '期望 5');
check('竖排提示含 开/高/低/收/量',
      ['开', '高', '低', '收', '量'].every(k => tip.includes(k)));
check('提示头部含日期与干支月',
      /\d{4}-\d{2}-\d{2}/.test(tip) &&
      /[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]月/.test(tip));

// --- 7. 需求3：滚轮缩放 ---
const beforeRect = cnt(chartEl._html, /data-role="candle"/g);
fire(wrapEl, 'wheel', { deltaY: -100, clientX: 490, clientY: 200, preventDefault() {} });
const zoomRe = cnt(chartEl._html, /data-role="candle"/g);
check(`滚轮放大后蜡烛减少 (${beforeRect} -> ${zoomRe})`, zoomRe < beforeRect);
check('放大后仍绘制成交量柱', cnt(chartEl._html, /data-role="vol"/g) === zoomRe);
check('放大后仍绘制 MACD 柱', cnt(chartEl._html, /data-role="macd"/g) === zoomRe);
fire(wrapEl, 'dblclick', {});
check(`双击复位回到全量 (candle=${cnt(chartEl._html, /data-role="candle"/g)})`,
      cnt(chartEl._html, /data-role="candle"/g) === nM, `期望 ${nM}`);

// --- 8. 横轴干支化（数据层）---
const GZ_DAY = /^[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]日$/;
check('日K 横轴标签为干支日（非阿拉伯）',
      D.bars.every(b => b.axis_label && GZ_DAY.test(b.axis_label)),
      D.bars.filter(b => !b.axis_label || !GZ_DAY.test(b.axis_label)).length + ' 条不符');
check('月K 横轴标签为干支月', D.months.every(b => b.axis_label === b.gz_month + '月'));
check('年K 横轴标签为干支年', D.years.every(b => b.axis_label === b.gz_year + '年'));
check('日K 轴标签不再是 MM-DD', !D.bars.some(b => /^\d{2}-\d{2}$/.test(b.axis_label)));

done();
