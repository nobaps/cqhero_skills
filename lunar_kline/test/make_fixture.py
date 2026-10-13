#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成离线渲染回归样本 test/fixtures/sample_payload.json。

- 价格用确定性 LCG 合成（不联网、可复现）
- 干支标注与聚合**复用真实脚本**（ganzhi.py / fetch_data.py），
  因此样本口径与线上完全一致，唯一差别是价格来源。
- 冻结为 fixture 后，回归测试无需联网、结果确定。

仅由维护者手动重跑（fixture 不应随每次测试变化）。
"""
import os
import sys
import json
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from ganzhi import ganzhi_month                       # noqa: E402
from fetch_data import (aggregate_by_ganzhi_month,     # noqa: E402
                        aggregate_by_ganzhi_year)

SPEC_TEXT = (
    "月分界=十二节气（立春起为寅月）；年分界=立春（干支年）；"
    "坐标为天干地支名；非交易日跳过；数据源=腾讯行情（前复权）。"
    "节气由天文算法计算，精度约 1 分钟；交节当日整日归入新月。"
)

START, END = date(2025, 6, 1), date(2026, 8, 31)


def lcg(seed):
    """确定性伪随机（线性同余），保证 fixture 可复现。"""
    x = seed
    while True:
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        yield x / 0x7FFFFFFF


def build_bars():
    rnd = lcg(20261010)
    price = 3000.0
    bars, d = [], START
    while d <= END:
        if d.weekday() < 5:                      # 仅工作日近似交易日
            drift = (next(rnd) - 0.48) * 40.0
            o = round(price, 2)
            c = round(max(10.0, price + drift), 2)
            hi = round(max(o, c) + next(rnd) * 15.0, 2)
            lo = round(min(o, c) - next(rnd) * 15.0, 2)
            vol = round(1e8 + next(rnd) * 5e8, 0)
            info = ganzhi_month(d)
            bars.append({
                "date": d.isoformat(), "open": o, "close": c,
                "high": hi, "low": lo, "volume": vol,
                "label": d.strftime("%m-%d"),
                "axis_label": info["gz_day"] + "日",
                "label_full": "%s %s%s月" % (d.isoformat(), info["gz_year"], info["gz_month"]),
                "gz_year": info["gz_year"], "gz_year_num": info["gz_year_num"],
                "gz_month": info["gz_month"], "gz_day": info["gz_day"],
                "jie": info["jie"],
            })
            price = c
        d += timedelta(days=1)
    bars.sort(key=lambda b: b["date"])
    return bars


def main():
    bars = build_bars()
    payload = {
        "name": "合成样本（离线回归用）",
        "calendar_spec": SPEC_TEXT,
        "bars": bars,
        "months": aggregate_by_ganzhi_month(bars),
        "years": aggregate_by_ganzhi_year(bars),
    }
    out = os.path.join(HERE, "fixtures", "sample_payload.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("OK %s  日K %d / 月K %d / 年K %d" %
          (out, len(payload["bars"]), len(payload["months"]), len(payload["years"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
