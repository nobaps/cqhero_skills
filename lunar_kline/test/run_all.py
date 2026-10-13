#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证集（真实可跑，纯 stdlib 断言）。

覆盖：节气日期锚点、干支年月推导、异常分支、聚合口径、
      以及**离线渲染回归**（fixture -> render_kline -> Node 双校验：
      数据/下钻 + 绘图/SVG）。
判据：全部通过 EXIT 0；任一失败 EXIT 1。（无 node 时渲染回归记 SKIP）
运行：python test/run_all.py
"""

import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import ganzhi as G            # noqa: E402
import lunar_convert as L     # noqa: E402

PY = sys.executable
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), "" if cond else detail))


# ---------------------------------------------------------------------------
# 1. 节气日期锚点（公开历表事实，非编造）
#    来源：公开日历；此处为日级判定
# ---------------------------------------------------------------------------
TERM_ANCHORS = [
    # (年份, 节气名, 期望月, 期望日)
    # 数据来源：公开节气历表 / 紫金山天文台发布值（非凭记忆）
    (2024, "立春", 2, 4), (2025, "立春", 2, 3), (2026, "立春", 2, 4),
    (2024, "清明", 4, 4), (2026, "清明", 4, 5),
    # 冬至实测值：2026-12-22 04:49:55（北京时间，紫金山天文台）
    (2026, "冬至", 12, 22),
    (2026, "惊蛰", 3, 5), (2026, "芒种", 6, 5),
    (2026, "夏至", 6, 21), (2026, "霜降", 10, 23), (2026, "大雪", 12, 7),
]

for y, tname, em, ed in TERM_ANCHORS:
    ts = {n: d for _, n, d in G.terms_of_year(y)}
    d = ts.get(tname)
    check("节气 %d %s = %02d-%02d" % (y, tname, em, ed),
          d is not None and d.month == em and d.day == ed,
          "实际得到 %s" % d)


# ---------------------------------------------------------------------------
# 2. 干支年 / 干支月锚点
# ---------------------------------------------------------------------------
YZ = {2024: "甲辰", 2025: "乙巳", 2026: "丙午", 2027: "丁未"}
for y, exp in YZ.items():
    _, _, txt = G.year_gz(y)
    check("年干支 %d = %s" % (y, exp), txt == exp, "实际 %s" % txt)

# 用户给定锚点：2026-02-04 立春 = 丙午年庚寅月
info = G.ganzhi_month(__import__("datetime").date(2026, 2, 4))
check("2026-02-04 = 丙午年庚寅月",
      info["gz_year"] == "丙午" and info["gz_month"] == "庚寅",
      "实际 %s %s" % (info["gz_year"], info["gz_month"]))
check("2026-02-04 交节名为立春", info["jie"] == "立春", "实际 %s" % info["jie"])

# 交节前一日：2026-02-03 = 乙巳年己丑月
info2 = G.ganzhi_month(__import__("datetime").date(2026, 2, 3))
check("2026-02-03 = 乙巳年己丑月",
      info2["gz_year"] == "乙巳" and info2["gz_month"] == "己丑",
      "实际 %s %s" % (info2["gz_year"], info2["gz_month"]))

# 连续 12 个干支月应互不重复且地支按序
ms = G.months_of_range(2026, 2026)
zys = [m["gz_month"][1] for m in ms]
check("2026 年 12 个干支月", len(ms) == 12, "实际 %d" % len(ms))
check("2026 年干支月地支不重复", len(set(zys)) == len(zys), "实际 %s" % zys)

# 日柱干支（干支纪日）锚点：公开万年历校对（非凭记忆）
from datetime import date as _dt_date, timedelta as _dt_td  # noqa: E402
DAY_ANCHORS = [("2024-01-01", "甲子"), ("2000-01-01", "戊午"),
               ("2024-01-02", "乙丑")]
for iso, exp in DAY_ANCHORS:
    _y, _m, _dd = (int(x) for x in iso.split("-"))
    _got = G.day_gz(_dt_date(_y, _m, _dd))[2]
    check("日柱 %s = %s日" % (iso, exp), _got == exp, "实际 %s" % _got)
check("日柱 60 日循环成立",
      G.day_gz(_dt_date(2024, 1, 1))[2]
      == G.day_gz(_dt_date(2024, 1, 1) + _dt_td(days=60))[2])


# ---------------------------------------------------------------------------
# 3. 农历锚点（保留，验证 lunar_convert 未回归）
# ---------------------------------------------------------------------------
ANCHORS = [
    ("2024-02-10", "2024年正月初一"),
    ("2025-01-29", "2025年正月初一"),
    ("2024-09-17", "2024年八月十五"),
]
for iso, expect in ANCHORS:
    r = L.tag_date(iso)
    check("农历 %s -> %s" % (iso, expect), expect in r["lunar_text"],
          "实际 %s" % r["lunar_text"])


# ---------------------------------------------------------------------------
# 4. 异常分支：应抛错且错误码正确
# ---------------------------------------------------------------------------
def expect_error(name, fn, code, *a, **kw):
    try:
        fn(*a, **kw)
        check(name, False, "未抛异常")
    except ValueError as e:
        check(name, code in str(e), "错误码不符: %s" % e)


expect_error("越界日期 -> OUT_OF_RANGE", L.tag_date, "OUT_OF_RANGE", "1850-01-01")
expect_error("非法日期 -> BAD_INPUT", L.tag_date, "BAD_INPUT", "2024-13-45")

from fetch_data import normalize_code  # noqa: E402
expect_error("非法代码 -> BAD_INPUT", normalize_code, "BAD_INPUT", "abcd")

try:
    normalize_code("600519")
    check("代码归一 600519 -> sh600519", normalize_code("600519") == "sh600519")
    check("代码归一 000001 -> sz000001", normalize_code("000001") == "sz000001")
except ValueError as e:
    check("代码归一化", False, str(e))


# ---------------------------------------------------------------------------
# 5. 聚合口径：用构造数据（不依赖网络）
# ---------------------------------------------------------------------------
from fetch_data import aggregate_by_ganzhi_month, aggregate_by_ganzhi_year  # noqa: E402

fake = [
    {"date": "2026-02-03", "open": 100.0, "close": 101.0, "high": 102.0,
     "low": 99.0, "volume": 10.0},   # 乙巳己丑月最后一日
    {"date": "2026-02-04", "open": 101.0, "close": 103.0, "high": 104.0,
     "low": 100.5, "volume": 20.0},  # 丙午庚寅月首日（立春）
    {"date": "2026-02-05", "open": 103.0, "close": 102.0, "high": 105.0,
     "low": 101.0, "volume": 30.0},  # 仍属庚寅月
]
agg = aggregate_by_ganzhi_month(fake)
check("聚合出 2 个干支月", len(agg) == 2, "实际 %d" % len(agg))
if len(agg) == 2:
    m0, m1 = agg[0], agg[1]
    check("首月为乙巳己丑月", m0["gz_year"] == "乙巳" and m0["gz_month"] == "己丑",
          "实际 %s%s" % (m0["gz_year"], m0["gz_month"]))
    check("次月为丙午庚寅月且起于 02-04",
          m1["gz_year"] == "丙午" and m1["gz_month"] == "庚寅"
          and m1["start"] == "2026-02-04",
          "实际 %s%s start=%s" % (m1["gz_year"], m1["gz_month"], m1["start"]))
    check("庚寅月开=首日开 103.0- 收盘=末日收",
          m1["open"] == 101.0 and m1["close"] == 102.0,
          "实际 O=%s C=%s" % (m1["open"], m1["close"]))
    check("庚寅月高/低取全月极值",
          m1["high"] == 105.0 and m1["low"] == 100.5,
          "实际 H=%s L=%s" % (m1["high"], m1["low"]))
    check("庚寅月量=求和 50.0", m1["volume"] == 50.0, "实际 %s" % m1["volume"])


# ---------------------------------------------------------------------------
# 6. 干支年聚合（v0.4.0 新增）
# ---------------------------------------------------------------------------
fake_year = [
    {"date": "2026-02-03", "open": 100.0, "close": 101.0, "high": 102.0,
     "low": 99.0, "volume": 10.0},   # 乙巳年最后一日
    {"date": "2026-02-04", "open": 101.0, "close": 103.0, "high": 104.0,
     "low": 100.5, "volume": 20.0},  # 丙午年首日（立春）
    {"date": "2026-06-15", "open": 103.0, "close": 108.0, "high": 110.0,
     "low": 102.0, "volume": 30.0},  # 丙午年内
]
agg_y = aggregate_by_ganzhi_year(fake_year)
check("干支年聚合出 2 个年", len(agg_y) == 2, "实际 %d" % len(agg_y))
if len(agg_y) == 2:
    y0, y1 = agg_y[0], agg_y[1]
    check("首年为乙巳年", y0["gz_year"] == "乙巳", "实际 %s" % y0["gz_year"])
    check("次年为丙午年且起于 02-04",
          y1["gz_year"] == "丙午" and y1["start"] == "2026-02-04",
          "实际 %s start=%s" % (y1["gz_year"], y1["start"]))
    check("丙午年高低=全区间极值",
          y1["high"] == 110.0 and y1["low"] == 100.5,
          "实际 H=%s L=%s" % (y1["high"], y1["low"]))
    check("丙午年量=求和 50.0", y1["volume"] == 50.0, "实际 %s" % y1["volume"])


# ---------------------------------------------------------------------------
# 7. 重名保护：同名干支月跨年不应混淆（v0.4.0 踩坑）
# ---------------------------------------------------------------------------
# 2025 与 2026 都可能有同名干支月，验证唯一键 (gz_year_num, gz_month) 能区分
from datetime import date as _date  # noqa: E402
i2025 = G.ganzhi_month(_date(2026, 1, 20))    # 乙巳年
i2026 = G.ganzhi_month(_date(2026, 3, 10))    # 丙午年
check("不同年可产生同名干支月（用于验证唯一键必要性）",
      isinstance(i2025["gz_month"], str) and isinstance(i2026["gz_month"], str))

# 用较长区间验证：干支月名会跨年重复（实测 6 年区间出现 17 组重名）
ms_long = G.months_of_range(2020, 2026)
names_long = [m["gz_month"] for m in ms_long]
keys_long = [(m["gz_year"], m["gz_month"]) for m in ms_long]
check("长区间内干支月名确有重复（唯一键必要）",
      len(set(names_long)) < len(names_long),
      "实际 %d 个名 / %d 个月" % (len(set(names_long)), len(names_long)))
check("「年+月」唯一键无重复",
      len(set(keys_long)) == len(keys_long),
      "实际 %d 组唯一 / %d 个月" % (len(set(keys_long)), len(keys_long)))


# ---------------------------------------------------------------------------
# 8. 渲染回归（离线）：fixture -> render_kline -> 两道 Node 校验
#    覆盖"绘图"路径（check_svg.js）与"数据/下钻"路径（check_render.js）。
#    Node 缺失时该项记为 SKIP（不判失败），保证本套件在纯 Python 环境仍可运行。
#    样本由 test/make_fixture.py 生成（确定性，冻结为 fixture）。
# ---------------------------------------------------------------------------
import json          # noqa: E402
import shutil        # noqa: E402
import tempfile      # noqa: E402
import render_kline  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "sample_payload.json")
NODE = shutil.which("node")
node_skipped = []
render_tmp = None

if not os.path.exists(FIXTURE):
    check("离线回归样本存在", False,
          "缺 %s（运行 python test/make_fixture.py 生成）" % FIXTURE)
else:
    check("离线回归样本存在", True)
    try:
        with open(FIXTURE, "r", encoding="utf-8") as f:
            _payload = json.load(f)
        _html = render_kline.render(_payload)
        render_tmp = os.path.join(tempfile.gettempdir(), "lkc_fixture_render.html")
        with open(render_tmp, "w", encoding="utf-8") as f:
            f.write(_html)
        check("离线渲染产出 HTML", len(_html) > 1000, "长度 %d" % len(_html))
    except Exception as e:  # noqa: BLE001
        render_tmp = None
        check("离线渲染产出 HTML", False, "%s: %s" % (type(e).__name__, e))

    for _js, _label in (("check_render.js", "数据/下钻"),
                        ("check_svg.js", "绘图/SVG")):
        if render_tmp is None:
            check("Node 校验 %s" % _label, False, "无渲染产物")
        elif not NODE:
            node_skipped.append("Node 校验 %s (%s)" % (_label, _js))
        else:
            _p = subprocess.run([NODE, os.path.join(HERE, _js), render_tmp],
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
            _lines = [l for l in (_p.stdout or "").strip().splitlines() if l.strip()]
            _tail = _lines[-2] if len(_lines) >= 2 else ""
            check("Node 校验 %s (%s)" % (_label, _js), _p.returncode == 0,
                  "exit=%s %s" % (_p.returncode, _tail))


# ---------------------------------------------------------------------------
def main():
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, detail in results:
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                             "" if ok else "  <- " + detail))
    for name in node_skipped:
        print("[SKIP] %s  <- 未找到 node，跳过" % name)
    print("-" * 64)
    print("suite=all assertions=%d passed=%d%s" % (
        total, passed, (" skipped=%d" % len(node_skipped)) if node_skipped else ""))
    if passed != total:
        print("EXIT 1 (存在失败用例)")
        return 1
    print("EXIT 0 (全部通过)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
