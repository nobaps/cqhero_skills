#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行情取数（联网，公开免费接口）+ 按干支月聚合。

数据源：腾讯行情（web.ifzq.gtimg.cn），实测可用、免密钥。
        东财 push2his 在本环境实测不可达；新浪仅提供实时快照无历史 K 线。

用法:
    python fetch_data.py sh000001 2026-01-01 2026-04-01 day   # 输出 JSON
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import date

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0]
                if ("\\" in __file__ or "/" in __file__) else ".")
try:
    from ganzhi import ganzhi_month
except ImportError:
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ganzhi import ganzhi_month

TENCENT = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           "?param={code},{klt},{start},{end},{count},{fq}")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 实测确认：复权数据的键名与不复权不同（致命坑）
KEY_CANDIDATES = {
    "day": ["qfqday", "day"],
    "week": ["qfqweek", "week"],
    "month": ["qfqmonth", "month"],
}


def _fetch_segment(code: str, start: str, end: str, klt: str,
                   fq: str, count: int, timeout: int) -> list:
    """单次请求（区间内不超过 count 条时可靠）。"""
    url = TENCENT.format(code=code, klt=klt, start=start, end=end,
                         count=count, fq=fq)
    req = urllib.request.Request(url, headers=UA)
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
    except urllib.error.URLError as e:
        raise ValueError("NETWORK_FAIL: 取数失败 %s" % e.reason)
    except Exception as e:
        raise ValueError("NETWORK_FAIL: %s" % type(e).__name__)

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("BAD_RESPONSE: 返回非 JSON")
    # 实测：count 过大会导致接口返回 list 而非 dict → 属平台限制
    if not isinstance(obj, dict):
        raise ValueError("BAD_RESPONSE: 接口返回结构异常（count 可能超出上限）")
    if obj.get("code") != 0:
        raise ValueError("BAD_RESPONSE: 接口返回 code=%s" % obj.get("code"))
    node = obj.get("data", {}).get(code)
    if not node:
        raise ValueError("NO_DATA: 未找到标的 %s 的数据" % code)

    rows = None
    for k in KEY_CANDIDATES[klt]:
        if k in node and node[k]:
            rows = node[k]
            break
    if rows is None:
        raise ValueError(
            "NO_DATA: 标的 %s 无 %s 数据（已尝试键 %s）"
            % (code, klt, "/".join(KEY_CANDIDATES[klt])))
    return rows


def fetch(code: str, start: str, end: str, klt: str = "day",
          fq: str = "qfq", count: int = 2000, timeout: int = 20) -> list:
    """取行情。返回 [{date, open, close, high, low, volume, 干支标签}, ...]。

    字段顺序实测确认: [日期, 开, 收, 高, 低, 量]

    自动分段：接口单次最多可靠返回约 2000 条，超出会**静默截断为最后 2000 条**
    （实测请求 20 年只拿到 2018 年起的数据）。故按 5 年一段循环请求后合并去重。
    """
    if klt not in KEY_CANDIDATES:
        raise ValueError("BAD_INPUT: klt 仅支持 day/week/month")

    sd, ed = date.fromisoformat(start), date.fromisoformat(end)
    if sd > ed:
        raise ValueError("BAD_INPUT: 起始日期晚于结束日期")

    # 按 5 年切段（5 年约 1220 个交易日，安全低于 2000）
    segs, cur = [], sd
    while cur <= ed:
        nxt = cur.replace(year=cur.year + 5) if cur.year + 5 <= 9999 else ed
        segs.append((cur, min(nxt, ed)))
        cur = nxt
        if nxt >= ed:
            break

    rows = []
    for a, b in segs:
        rows.extend(_fetch_segment(code, a.isoformat(), b.isoformat(),
                                   klt, fq, count, timeout))

    # 去重（分段边界可能重叠）+ 按日期升序
    seen, uniq = set(), []
    for r in rows:
        if len(r) < 6:
            continue
        if r[0] in seen:
            continue
        seen.add(r[0])
        uniq.append(r)
    uniq.sort(key=lambda r: r[0])

    out = []
    for r in uniq:
        d = date.fromisoformat(r[0])
        info = ganzhi_month(d)
        out.append({
            "date": r[0], "open": float(r[1]), "close": float(r[2]),
            "high": float(r[3]), "low": float(r[4]), "volume": float(r[5]),
            "label": d.strftime("%m-%d"),
            "axis_label": info["gz_day"] + "日",   # 日K 横轴用干支日
            "label_full": "%s %s%s月" % (r[0], info["gz_year"], info["gz_month"]),
            "gz_year": info["gz_year"],
            "gz_year_num": info["gz_year_num"],
            "gz_month": info["gz_month"],
            "gz_day": info["gz_day"],
            "jie": info["jie"],
        })
    return out


def normalize_code(s: str) -> str:
    """归一化标的代码为腾讯格式。支持 000001 / sh000001 / 600519 等。"""
    s = s.strip().lower()
    if s.startswith(("sh", "sz", "bj")):
        return s
    if not s.isdigit() or len(s) != 6:
        raise ValueError("BAD_INPUT: 无法识别代码 %r（应为 6 位数字或带 sh/sz 前缀）" % s)
    if s[0] == "6":
        return "sh" + s
    if s[0] in ("0", "3"):
        return "sz" + s
    if s[0] in ("4", "8"):
        return "bj" + s
    raise ValueError("BAD_INPUT: 无法推断市场，请显式加 sh/sz 前缀：%r" % s)


def aggregate_generic(bars: list, key_fn, label_fn, extra_fn=None) -> list:
    """通用聚合：按 key_fn 分组，组内取首日开/末日收/最高/最低/量求和。

    key_fn(date) -> 分组键（可哈希）
    label_fn(info, date) -> 组标签文本
    extra_fn(info) -> 附加字段 dict（可选）
    """
    groups = {}
    order = []
    for b in bars:
        d = date.fromisoformat(b["date"])
        info = ganzhi_month(d)
        key = key_fn(info, d)
        if key not in groups:
            groups[key] = {
                "key": key, "info": info, "bars": [],
                "start": b["date"], "end": b["date"],
            }
            order.append(key)
        g = groups[key]
        g["bars"].append(b)
        g["end"] = b["date"]

    out = []
    for key in order:
        g = groups[key]
        bs = sorted(g["bars"], key=lambda x: x["date"])
        info = g["info"]
        item = {
            "date": g["start"],
            "label": label_fn(info, date.fromisoformat(g["start"])),
            "gz_year": info["gz_year"],
            "gz_month": info["gz_month"],
            "jie": info["jie"],
            "start": g["start"],
            "end": g["end"],
            "open": bs[0]["open"],
            "close": bs[-1]["close"],
            "high": max(x["high"] for x in bs),
            "low": min(x["low"] for x in bs),
            "volume": sum(x["volume"] for x in bs),
            "days": len(bs),
        }
        item["axis_label"] = item["label"]
        if extra_fn:
            item.update(extra_fn(info))
        out.append(item)
    return out


def aggregate_by_ganzhi_month(bars: list) -> list:
    """按干支月聚合为月 K：每根柱 = 一个干支月。

    聚合口径（已确认）：非交易日跳过；首日开盘为开，末日收盘为收，
    全月最高为高，全月最低为低，成交量求和。
    """
    return aggregate_generic(
        bars,
        key_fn=lambda info, d: (info["gz_year_num"], info["gz_month"]),
        label_fn=lambda info, d: info["gz_month"] + "月",
    )


def aggregate_by_ganzhi_year(bars: list) -> list:
    """按**干支年**聚合为年 K：每根柱 = 一个干支年（立春换年）。

    口径（已确认）：以立春为年界。如丙午年 = 2026-02-04 至 2027-02-03。
    """
    return aggregate_generic(
        bars,
        key_fn=lambda info, d: info["gz_year_num"],
        label_fn=lambda info, d: info["gz_year"] + "年",
        extra_fn=lambda info: {"gz_year_num": info["gz_year_num"]},
    )


def aggregate_by_solar_month(bars: list) -> list:
    """按公历月聚合（供"日K/常规"对照视图使用）。"""
    return aggregate_generic(
        bars,
        key_fn=lambda info, d: (d.year, d.month),
        label_fn=lambda info, d: "%d-%02d" % (d.year, d.month),
    )


def _main(argv):
    if len(argv) < 5:
        sys.stderr.write("usage: fetch_data.py <code> <start> <end> [day|week|month]\n")
        return 1
    code, start, end = argv[1], argv[2], argv[3]
    klt = argv[4] if len(argv) > 4 else "day"
    try:
        c = normalize_code(code)
        bars = fetch(c, start, end, klt)
        monthly = aggregate_by_ganzhi_month(bars)
        print(json.dumps({
            "code": c, "klt": klt,
            "bars": bars, "ganzhi_months": monthly,
        }, ensure_ascii=False))
        return 0
    except ValueError as e:
        sys.stderr.write(str(e) + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
