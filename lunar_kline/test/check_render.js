// 验证渲染器生成的 HTML 中，内联数据与下钻分组逻辑是否正确。
// 不依赖浏览器：直接抽出内联 JSON，复刻渲染器的分组逻辑并断言。
const fs = require('fs');
const path = process.argv[2];
const html = fs.readFileSync(path, 'utf8');

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`[PASS] ${name}`); }
  else { fail++; console.log(`[FAIL] ${name}  <- ${detail || ''}`); }
}

// 1. 三个级别按钮都在
check('含年K按钮', html.includes('data-lv="year"'));
check('含月K按钮', html.includes('data-lv="month"'));
check('含日K按钮', html.includes('data-lv="day"'));

// 2. 免责与口径声明
check('含免责声明', html.includes('不构成任何投资建议'));
check('含口径声明', html.includes('立春起为寅月'));

// 3. 抽出内联数据
const m = html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/);
check('内联数据块存在', !!m);
const raw = m[1].replace(/<\\\//g, '</');
const D = JSON.parse(raw);
check('内联数据可解析', !!D);

// 4. 三层数据都在且非空
check(`日K 非空 (${D.bars.length})`, D.bars.length > 0);
check(`干支月K 非空 (${D.months.length})`, D.months.length > 0);
check(`干支年K 非空 (${D.years.length})`, D.years.length > 0);

// 5. 复刻渲染器的下钻分组逻辑（干支月需用「年+月」唯一键，防跨年重名串数据）
const dayByMonth = {}, dayByYear = {};
const mkey = b => (b.gz_year || '') + (b.gz_month || '');
D.bars.forEach(b => {
  if (b.gz_month) (dayByMonth[mkey(b)] = dayByMonth[mkey(b)] || []).push(b);
  if (b.gz_year) (dayByYear[b.gz_year] = dayByYear[b.gz_year] || []).push(b);
});
check('日K按干支月分组成功', Object.keys(dayByMonth).length > 0);
check('日K按干支年分组成功', Object.keys(dayByYear).length > 0);

// 6. 关键：月K的每根柱，都能用「年+月」唯一键下钻到日K
const missing = [];
D.months.forEach(mb => {
  const k = (mb.gz_year || '') + (mb.gz_month || '');
  if (!dayByMonth[k]) missing.push(k);
});
check('每月K标签都能下钻到日K', missing.length === 0,
      '缺失: ' + missing.join(','));

// 6b. 重名保护：同名干支月应能分别下钻到各自年份的数据
const dupNames = {};
D.months.forEach(mb => {
  (dupNames[mb.gz_month] = dupNames[mb.gz_month] || []).push(
    (mb.gz_year || '') + (mb.gz_month || ''));
});
const dupChecked = Object.entries(dupNames).filter(([, v]) => v.length > 1);
check(`重名月份用唯一键区分 (${dupChecked.length} 组)`,
      dupChecked.every(([, keys]) => new Set(keys).size === keys.length));

// 7. 年K同理
const missingY = [];
D.years.forEach(yb => {
  if (!dayByYear[yb.gz_year]) missingY.push(yb.gz_year);
});
check('每年K标签都能下钻到日K', missingY.length === 0,
      '缺失: ' + missingY.join(','));

// 8. 下钻分组的天数之和 == 日K总条数（无遗漏）
const sumM = Object.values(dayByMonth).reduce((a, x) => a + x.length, 0);
check('月分组天数之和等于日K总数', sumM === D.bars.length,
      `${sumM} vs ${D.bars.length}`);

// 9. 聚合一致性：月K的 close 应等于该月最后一天的 close
let badClose = 0;
D.months.forEach(mb => {
  const k = (mb.gz_year || '') + (mb.gz_month || '');
  const days = (dayByMonth[k] || []).slice().sort((a, b) => a.date < b.date ? -1 : 1);
  if (!days.length) return;
  if (Math.abs(days[days.length - 1].close - mb.close) > 1e-6) badClose++;
});
check('月K收盘=该月末日的收盘', badClose === 0, `不符 ${badClose} 个`);

// 10. 月K的开盘应等于该月首日的开盘
let badOpen = 0;
D.months.forEach(mb => {
  const k = (mb.gz_year || '') + (mb.gz_month || '');
  const days = (dayByMonth[k] || []).slice().sort((a, b) => a.date < b.date ? -1 : 1);
  if (!days.length) return;
  if (Math.abs(days[0].open - mb.open) > 1e-6) badOpen++;
});
check('月K开盘=该月首日的开盘', badOpen === 0, `不符 ${badOpen} 个`);

// 11. 年K聚合一致性
let badY = 0;
D.years.forEach(yb => {
  const days = (dayByYear[yb.gz_year] || []).slice().sort((a, b) => a.date < b.date ? -1 : 1);
  if (!days.length) return;
  const hi = Math.max(...days.map(x => x.high));
  const lo = Math.min(...days.map(x => x.low));
  if (Math.abs(hi - yb.high) > 1e-6 || Math.abs(lo - yb.low) > 1e-6) badY++;
});
check('年K高低=该年全区间极值', badY === 0, `不符 ${badY} 个`);

// 12. 干支年边界正确性：丙午年应始于立春 2026-02-04
const bingwu = D.years.find(y => y.gz_year === '丙午');
check('存在丙午年', !!bingwu);
if (bingwu) {
  check('丙午年始于 2026-02-04（立春）', bingwu.start === '2026-02-04', bingwu.start);
}
const yisi = D.years.find(y => y.gz_year === '乙巳');
if (yisi) {
  check('乙巳年止于 2026-02-03', yisi.end === '2026-02-03', yisi.end);
}

// 13. 日K每条都带干支标签（下钻依赖此字段）
const noTag = D.bars.filter(b => !b.gz_month || !b.gz_year).length;
check('日K全部带干支标签', noTag === 0, `${noTag} 条缺失`);

console.log('-'.repeat(64));
console.log(`suite=render assertions=${pass + fail} passed=${pass}`);
if (fail > 0) { console.log('EXIT 1'); process.exit(1); }
console.log('EXIT 0 (全部通过)');
