#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端：取数 -> 聚合（日/干支月/干支年）-> 渲染交互式 HTML K 线图。

用法:
    python build_chart.py <代码> <起> <止> [输出路径] [--klt day]
    python build_chart.py sh000001 2020-01-01 2026-04-15
"""

import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fetch_data import (fetch, normalize_code, aggregate_by_ganzhi_month,  # noqa: E402
                        aggregate_by_ganzhi_year)
from render_kline import render  # noqa: E402

SPEC_TEXT = (
    "月分界=十二节气（立春起为寅月）；年分界=立春（干支年）；横轴=天干地支名"
    "（年/月/日均为干支）；非交易日跳过；数据源=腾讯行情（前复权）。"
    "下方两窗格：成交量（单位「手」，红涨绿跌）与 MACD(12,26,9)。"
    "「成交量」为量口径，非成交额（本环境可用的免费源不含成交额）。"
    "节气由天文算法计算，精度约 1 分钟；交节当日整日归入新月。"
)


def build(code, start, end, klt="day", out=None, title=None):
    c = normalize_code(code)
    bars = fetch(c, start, end, klt)
    if not bars:
        raise ValueError("NO_DATA: 区间内无行情数据")
    months = aggregate_by_ganzhi_month(bars)
    years = aggregate_by_ganzhi_year(bars)

    payload = {
        "name": title or "%s（%s ~ %s）" % (c, start, end),
        "calendar_spec": SPEC_TEXT,
        "bars": bars,        # 日K
        "months": months,    # 干支月K
        "years": years,      # 干支年K
    }
    html_out = render(payload)

    if out is None:
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        runs = os.path.join(os.path.dirname(HERE), "runs", stamp)
        out = os.path.join(runs, "%s.html" % c)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_out)
    return out, len(bars), len(months), len(years)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 3:
        sys.stderr.write("usage: build_chart.py <code> <start> <end> [out.html] [--klt day]\n")
        return 1
    code, start, end = args[0], args[1], args[2]
    out = args[3] if len(args) > 3 else None
    klt = "day"
    if "--klt" in argv:
        klt = argv[argv.index("--klt") + 1]
    try:
        path, nd, nm, ny = build(code, start, end, klt, out)
    except ValueError as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    print("OK %s  (日K %d 条 / 干支月 %d 个 / 干支年 %d 个)" % (path, nd, nm, ny))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
