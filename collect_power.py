"""전력시장 전일실적 수집 -> power.json
- 한국전력거래소 계통한계가격 및 수요예측(하루전 발전계획용)
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
URL = "https://apis.data.go.kr/B552115/SmpWithForecastDemand/getSmpWithForecastDemand"
NOW = datetime.now(timezone(timedelta(hours=9)))


def call(day):
    q = urllib.parse.urlencode({
        "serviceKey": KEY, "pageNo": 1, "numOfRows": 100,
        "dataType": "JSON", "date": day,
    })
    req = urllib.request.Request(URL + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8")
    try:
        data = json.loads(text)
    except ValueError:
        raise RuntimeError("응답이 JSON이 아님: " + text[:200])
    items = data.get("response", {}).get("body", {}).get("items", {})
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items or []


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def demand_of(it):
    # mlfd = 육지 수요예측(MW), jlfd = 제주, slfd = 합계
    return num(it.get("mlfd"))

def summarize(day):
    items = call(day)
    land = [it for it in items
            if "육지" in str(it.get("areaName", "")) or str(it.get("areaCd", "")) == "1"]
    land = land or items
    hours = []
    for it in land:
        h, smp = num(it.get("hour")), num(it.get("smp"))
        if h is None or smp is None:
            continue
        hours.append({"h": int(h), "smp": smp, "demand": demand_of(it)})
    hours.sort(key=lambda x: x["h"])
    if not hours:
        raise RuntimeError(f"{day} 데이터 없음")
    smps = [x["smp"] for x in hours]
    hi = max(hours, key=lambda x: x["smp"])
    lo = min(hours, key=lambda x: x["smp"])
    dem = [x["demand"] for x in hours if x["demand"] is not None]
    return {
        "date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
        "avg": round(sum(smps) / len(smps), 2),
        "max": hi["smp"], "max_h": hi["h"],
        "min": lo["smp"], "min_h": lo["h"],
        "demand_max": max(dem) if dem else None,
        "hours": hours,
    }, (land[0] if land else None)


def main():
    errors, result = [], {"updated_at": NOW.strftime("%Y-%m-%d %H:%M")}
    for key, back in (("yday", 1), ("prev", 2)):
        day = (NOW - timedelta(days=back)).strftime("%Y%m%d")
        try:
            result[key], sample = summarize(day)
            if key == "yday":
                result["sample"] = sample   # 칸 이름 확인용
            print(key, day, "평균", result[key]["avg"])
        except Exception as e:
            result[key] = None
            errors.append(f"{day}: {e}")
    result["errors"] = errors
    with open("power.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("저장 완료. 실패:", errors or "없음")


if __name__ == "__main__":
    main()
