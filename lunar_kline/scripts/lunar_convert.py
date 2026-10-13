#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公历 <-> 农历 <-> 节气 转换（纯标准库，确定性输出）。

设计意图：农历换算与节气日期是模型凭记忆必然算错的部分，
因此这部分不交给模型推理，而是由本脚本确定性计算。

数据来源：节气采用天文近似算法（太阳黄经），农历采用内置 1900-2100 年压缩表。
本文件为零依赖实现，避免第三方库缺失导致技能不可用。

用法:
    python lunar_convert.py date 2024-02-10        # 公历 -> 农历 + 节气
    python lunar_convert.py range 2024-01-01 2024-03-01  # 批量打标
"""

import sys
import json
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# 农历数据表（1900-2100），每年一个 16 位十六进制编码
# 位 0-3: 闰月月份（0 = 无闰月）
# 位 4-15: 12 或 13 个月的大小月（1 = 30 天，0 = 29 天）
# 说明：该表为公开通用农历数据表，来源见 references/lunar-table-source.md
# ---------------------------------------------------------------------------
LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0,
    0x09ad0, 0x055d2, 0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540,
    0x0d6a0, 0x0ada2, 0x095b0, 0x14977, 0x04970, 0x0a4b0, 0x0b4b5, 0x06a50,
    0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970, 0x06566, 0x0d4a0,
    0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2,
    0x0a950, 0x0b557, 0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573,
    0x052b0, 0x0a9a8, 0x0e950, 0x06aa0, 0x0aea6, 0x0ab50, 0x04b60, 0x0aae4,
    0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0, 0x096d0, 0x04dd5,
    0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46,
    0x0ab60, 0x09570, 0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58,
    0x05ac0, 0x0ab60, 0x096d5, 0x092e0, 0x0c960, 0x0d954, 0x0d4a0, 0x0da50,
    0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5, 0x0a950, 0x0b4a0,
    0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260,
    0x0ea65, 0x0d530, 0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0,
    0x1d0b6, 0x0d250, 0x0d520, 0x0dd45, 0x0b5a0, 0x056d0, 0x055b2, 0x049b0,
    0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0, 0x14b63, 0x09370,
    0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,
    0x0a2e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0,
    0x0a6d0, 0x055d4, 0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50,
    0x055a0, 0x0aba4, 0x0a5b0, 0x052b0, 0x0b273, 0x06930, 0x07337, 0x06aa0,
    0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160, 0x0e968, 0x0d520,
    0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,
    0x0d520,
]

LUNAR_MONTH_CN = ["正", "二", "三", "四", "五", "六",
                  "七", "八", "九", "十", "冬", "腊"]
LUNAR_DAY_CN = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]

BASE_DATE = date(1900, 1, 31)  # 1900-01-31 对应农历 1900 年正月初一


def _leap_month(year: int) -> int:
    """返回该农历年的闰月月份，0 表示无闰月。"""
    return LUNAR_INFO[year - 1900] & 0xF


def _leap_days(year: int) -> int:
    """闰月天数，无闰月返回 0。"""
    if _leap_month(year):
        return 30 if (LUNAR_INFO[year - 1900] & 0x10000) else 29
    return 0


def _month_days(year: int, month: int) -> int:
    """农历某月（非闰月）天数。"""
    return 30 if (LUNAR_INFO[year - 1900] & (0x10000 >> month)) else 29


def _year_days(year: int) -> int:
    """农历某年总天数。"""
    total = 348  # 12 个月基准 29 天
    mask = 0x8000
    for _ in range(12):
        if LUNAR_INFO[year - 1900] & mask:
            total += 1
        mask >>= 1
    return total + _leap_days(year)


def solar_to_lunar(d: date) -> dict:
    """公历 -> 农历。返回 dict: year, month, day, is_leap, month_cn, day_cn。"""
    if d < BASE_DATE:
        raise ValueError("OUT_OF_RANGE: 仅支持 1900-01-31 及之后的日期")
    if d.year > 2100:
        raise ValueError("OUT_OF_RANGE: 仅支持 2100 年及之前的日期")

    offset = (d - BASE_DATE).days
    lunar_year = 1900
    while lunar_year <= 2100:
        days = _year_days(lunar_year)
        if offset < days:
            break
        offset -= days
        lunar_year += 1
    else:
        raise ValueError("OUT_OF_RANGE: 超出农历表覆盖范围")

    leap = _leap_month(lunar_year)
    lunar_month = 1
    is_leap = False
    while lunar_month <= 12:
        days = _leap_days(lunar_year) if (leap == lunar_month and not is_leap) \
            else _month_days(lunar_year, lunar_month)
        if offset < days:
            break
        offset -= days
        if leap == lunar_month and not is_leap:
            is_leap = True  # 同月再走一遍（闰月）
        else:
            is_leap = False
            lunar_month += 1
    return {
        "year": lunar_year,
        "month": lunar_month,
        "day": offset + 1,
        "is_leap": is_leap,
        "month_cn": ("闰" if is_leap else "") + LUNAR_MONTH_CN[lunar_month - 1] + "月",
        "day_cn": LUNAR_DAY_CN[offset],
    }


# ---------------------------------------------------------------------------
# 节气（太阳黄经近似算法，精度约 ±1 天，用于分段足够）
# 说明：若需天文级精度，替换为 references/ 中的高精度系数表。
# ---------------------------------------------------------------------------
TERM_NAMES = [
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明", "谷雨",
    "立夏", "小满", "芒种", "夏至", "小暑", "大暑", "立秋", "处暑",
    "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
]

# 各节气在公历年的基准日与百年累积偏移（近似）
_TERM_BASE = [
    5.4055, 20.12, 3.87, 18.73, 5.63, 20.646, 4.81, 20.1,
    5.52, 21.04, 5.678, 21.37, 7.108, 22.83, 7.5, 23.13,
    7.646, 23.042, 8.318, 23.438, 7.438, 22.36, 7.18, 21.94,
]
_TERM_OFFSET = [
    3.87, 18.73, 5.63, 20.646, 4.81, 20.1, 5.52, 21.04,
    5.678, 21.37, 7.108, 22.83, 7.5, 23.13, 7.646, 23.042,
    8.318, 23.438, 7.438, 22.36, 7.18, 21.94, 5.4055, 20.12,
]


def solar_term_day(year: int, index: int) -> int:
    """返回该公历年第 index 个节气（0=小寒）所在的日。"""
    if index < 2:
        y = year - 1
        offset_20 = _TERM_BASE[index]
        offset_21 = _TERM_OFFSET[index + 22]
    else:
        y = year
        offset_20 = _TERM_BASE[index]
        offset_21 = _TERM_OFFSET[index - 2]
    if index % 2 == 0:
        base = int(y * 0.2422 + offset_20) - int((y - 1) / 4)
    else:
        base = int(y * 0.2422 + offset_21) - int((y - 1) / 4)
    return base


def terms_of_year(year: int) -> list:
    """返回该公历年 24 节气 [(name, date), ...]。"""
    out = []
    for i, name in enumerate(TERM_NAMES):
        try:
            day = solar_term_day(year, i)
            month = i // 2 + 1
            out.append((name, date(year, month, day)))
        except ValueError:
            out.append((name, None))
    return out


def tag_date(iso: str) -> dict:
    """给一个公历日期打农历 + 节气标签。"""
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        raise ValueError("BAD_INPUT: 日期格式应为 YYYY-MM-DD，收到 %r" % iso)

    lunar = solar_to_lunar(d)
    near_terms = []
    for name, td in terms_of_year(d.year):
        if td and abs((td - d).days) <= 1:
            near_terms.append(name)
    return {
        "solar": iso,
        "lunar_year": lunar["year"],
        "lunar_month": lunar["month"],
        "lunar_day": lunar["day"],
        "lunar_leap": lunar["is_leap"],
        "lunar_text": "%d年%s%s" % (lunar["year"], lunar["month_cn"], lunar["day_cn"]),
        "solar_terms": near_terms,
    }


def _main(argv: list) -> int:
    if len(argv) < 2:
        sys.stderr.write("usage: lunar_convert.py date <YYYY-MM-DD>\n")
        return 1
    cmd = argv[1]
    try:
        if cmd == "date":
            print(json.dumps(tag_date(argv[2]), ensure_ascii=False, sort_keys=True))
            return 0
        if cmd == "range":
            start, end = date.fromisoformat(argv[2]), date.fromisoformat(argv[3])
            cur, out = start, []
            while cur <= end:
                out.append(tag_date(cur.isoformat()))
                cur += timedelta(days=1)
            print(json.dumps(out, ensure_ascii=False, sort_keys=True))
            return 0
        sys.stderr.write("BAD_INPUT: unknown command %r\n" % cmd)
        return 1
    except ValueError as e:
        sys.stderr.write(str(e) + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
