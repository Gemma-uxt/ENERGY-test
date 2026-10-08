"""전력시장 전일실적 수집 -> power.json
- SMP·수요예측: 한국전력거래소 계통한계가격 및 수요예측(하루전 발전계획용)
- 전력수급실적: 전력거래소 홈페이지 '전력수급실적' 표
- 공휴일: 한국천문연구원 특일 정보
"""
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
SMP_URL = "https://apis.data.go.kr/B552115/SmpWithForecastDemand/getSmpWithForecastDemand"
HOLI_URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
SUPPLY_URL = "https://www.kpx.or.kr/powerDemandPerform.es?mid=a10404060000"
NOW = datetime.now(timezone(timedelta(hours=9)))
DAYS = 7


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def items_of(text):
    try:
        data = json.loads(text)
    except ValueError:
        raise RuntimeError("응답이 JSON이 아님: " + text[:200])
    items = data.get("response", {}).get("body", {}).get("items", {})
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items if isinstance(items, list) else []


def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# ---------- SMP (하루치) ----------
def smp_day(day):
    items = items_of(get(SMP_URL, {
        "serviceKey": KEY, "pageNo": 1, "numOfRows": 100,
        "dataType": "JSON", "date": day,
    }))
    land = [it for it in items
            if "육지" in str(it.get("areaName", "")) or str(it.get("areaCd", "")) == "1"]
    land = land or items
    hours = []
    for it in land:
        h, smp = num(it.get("hour")), num(it.get("smp"))
        if h is None or smp is None:
            continue
        hours.append({"h": int(h), "smp": smp, "demand": num(it.get("mlfd"))})  # mlfd = 육지 수요예측
    hours.sort(key=lambda x: x["h"])
    if not hours:
        raise RuntimeError("데이터 없음")
    smps = [x["smp"] for x in hours]
    hi = max(hours, key=lambda x: x["smp"])
    lo = min(hours, key=lambda x: x["smp"])
    pairs = [(x["smp"], x["demand"]) for x in hours if x["demand"]]
    wavg = round(sum(s * d for s, d in pairs) / sum(d for _, d in pairs), 2) if pairs else None
    dem = [x["demand"] for x in hours if x["demand"] is not None]
    return {
        "date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
        "avg": round(sum(smps) / len(smps), 2),
        "wavg": wavg,
        "max": hi["smp"], "max_h": hi["h"],
        "min": lo["smp"], "min_h": lo["h"],
        "demand_max": max(dem) if dem else None,
        "hours": hours,
    }, (land[0] if land else None)


# ---------- 전력수급실적 (전력거래소 홈페이지 표) ----------
def supply():
    html = get(SUPPLY_URL)
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [" ".join(re.sub(r"<[^>]+>|&nbsp;", " ", c).split())
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        idx = [i for i, c in enumerate(cells) if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", c)]
        if not idx:
            continue
        c = cells[idx[0]:]
        # 일시, 설비용량, 공급능력, 최대전력(전년, 금년, 증가율, 시간대), 최소전력(금년, 시간대), 공급예비력, 예비율
        if len(c) < 11:
            continue
        out[c[0].replace(".", "-")] = {
            "cap": num(c[2]),
            "peak": num(c[4]),
            "peak_h": re.sub(r"\D", "", c[6]),
            "reserve": num(c[10]),
        }
    if not out:
        raise RuntimeError("표를 찾지 못함 (페이지 구조 변경 또는 접속 차단)")
    return out


# ---------- 공휴일 ----------
def holidays(months):
    out = {}
    for y, m in months:
        for it in items_of(get(HOLI_URL, {
            "serviceKey": KEY, "solYear": y, "solMonth": f"{m:02d}",
            "numOfRows": 50, "_type": "json",
        })):
            if it.get("isHoliday") == "Y":
                s = str(it.get("locdate"))
                out[f"{s[:4]}-{s[4:6]}-{s[6:8]}"] = it.get("dateName", "")
    return out


def main():
    errors, result = [], {"updated_at": NOW.strftime("%Y-%m-%d %H:%M")}
    days = [NOW - timedelta(days=b) for b in range(1, DAYS + 1)]

    smp, sample = {}, None
    for d in days:
        key = d.strftime("%Y%m%d")
        try:
            smp[d.strftime("%Y-%m-%d")], s = smp_day(key)
            sample = sample or s
        except Exception as e:
            errors.append(f"SMP {key}: {e}")

    try:
        sup = supply()
    except Exception as e:
        sup = {}
        errors.append(f"전력수급실적: {e}")

    try:
        hol = holidays(sorted({(d.year, d.month) for d in days}))
    except Exception as e:
        hol = {}
        errors.append(f"공휴일: {e} (주말만 표시)")

    week = []
    for d in days:
        ds = d.strftime("%Y-%m-%d")
        s, p = smp.get(ds) or {}, sup.get(ds) or {}
        week.append({
            "date": ds,
            "holiday": d.weekday() >= 5 or ds in hol,
            "holiday_name": hol.get(ds, ""),
            "wavg": s.get("wavg"), "max": s.get("max"), "min": s.get("min"),
            "cap": p.get("cap"), "peak": p.get("peak"),
            "peak_h": p.get("peak_h"), "reserve": p.get("reserve"),
        })

    result["yday"] = smp.get(days[0].strftime("%Y-%m-%d"))
    result["prev"] = smp.get(days[1].strftime("%Y-%m-%d"))
    result["week"] = week
    result["sample"] = sample
    result["errors"] = errors
    with open("power.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("저장 완료. 실패:", errors or "없음")


if __name__ == "__main__":
    main()
