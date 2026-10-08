"""TMS 굴뚝 측정값으로 발전기 가동 상태·발전시간 수집
-> tms.json (화면용), tms_hours.json (가동한 시간 기록)
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
URL = "https://apis.data.go.kr/B552584/cleansys/rltmMesureResult"
NOW = datetime.now(timezone(timedelta(hours=9)))
TODAY = NOW.strftime("%Y-%m-%d")
YDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")
HOURS_FILE = Path("tms_hours.json")

# (id, 검색어 목록, TMS 등록명, 배출구 번호들)
#  - 등록명이 "글자"면 이름이 정확히 같은 것만
#  - 등록명이 ["단어", ...]면 그 단어가 모두 들어간 이름
UNITS = [
    ("에스파워", ["에스파워"], "㈜에스파워", ["1", "2"]),
    ("광명사업단", ["삼천리"], "㈜삼천리", ["1", "2"]),
    ("안산도시개발", ["안산도시개발"], "안산도시개발㈜", ["2"]),
    ("GS파워 안양 1호기", ["GS파워"], "GS파워㈜안양열병합발전처", ["7"]),
    ("GS파워 안양 2호기", ["GS파워"], "GS파워㈜안양열병합발전처", ["8"]),
    ("GS파워 부천", ["GS파워"], "GS파워㈜부천열병합발전처", ["1", "2", "3"]),
    ("청라에너지", ["청라"], "청라자원환경센터", ["1", "2"]),
    ("인천종합에너지", ["인천종합에너지"], "인천종합에너지㈜", ["1", "2"]),
    ("위드인천에너지", ["위드인천"], "위드인천에너지(주)", ["1"]),
    ("GS E&R 반월 배출구1", ["지에스반월"], "㈜지에스반월열병합발전", ["1"]),
    ("GS E&R 반월 배출구2", ["지에스반월"], "㈜지에스반월열병합발전", ["2"]),
    ("GS E&R 반월 배출구3", ["지에스반월"], "㈜지에스반월열병합발전", ["3"]),
    ("GS E&R 반월 배출구4", ["지에스반월"], "㈜지에스반월열병합발전", ["4"]),
    ("GS E&R 반월 배출구11", ["지에스반월"], "㈜지에스반월열병합발전", ["11"]),
    ("위례열병합", ["나래에너지"], "나래에너지서비스㈜", ["1"]),
    ("하남열병합", ["나래에너지"], "나래에너지서비스㈜하남사업소", ["1"]),
    ("DS파워", ["디에스파워"], "디에스파워㈜", ["1", "2"]),
    ("평택에너지앤파워(E1)", ["평택에너지"], "평택에너지앤파워(주)", ["1", "2", "3"]),
    ("포천파워 1호기", ["포천파워"], "포천파워㈜", ["1", "2"]),
    ("포천파워 2호기", ["포천파워"], "포천파워㈜", ["3", "4"]),
    ("포천민자발전", ["포천민자"], "포천민자발전㈜", ["1", "2", "3"]),
    ("동두천드림파워 1호기", ["동두천"], "동두천드림파워㈜", ["1", "2"]),
    ("동두천드림파워 2호기", ["동두천"], "동두천드림파워㈜", ["3", "4"]),
    ("통영에코파워", ["통영에코"], "통영에코파워(주)", ["1", "2"]),
    ("울산GPS(SK가스)", ["지피에스"], "울산 지피에스 주식회사", ["6", "7"]),
]


def call(word):
    q = urllib.parse.urlencode({
        "serviceKey": KEY, "factManageNm": word,
        "type": "json", "pageNo": 1, "numOfRows": 100,
    })
    req = urllib.request.Request(URL + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def find_items(obj, out):
    if isinstance(obj, dict):
        if "fact_manage_nm" in obj:
            out.append(obj)
        else:
            for v in obj.values():
                find_items(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_items(v, out)


def match(name, rule):
    name = name.strip()
    if isinstance(rule, str):
        return name == rule
    return all(w in name for w in rule)


def stack_state(value):
    """굴뚝 하나의 상태: on(가동) / off(가동중지) / idle(정지 추정) / nodata"""
    if value is None:
        return "nodata"
    s = str(value)
    if "가동중지" in s:
        return "off"
    try:
        x = float(s)
    except ValueError:
        return "nodata"
    return "on" if x >= 1 else "idle"


def main():
    cache, errors, units, times = {}, [], [], []

    # 지난 기록 불러오기
    hist = {}
    if HOURS_FILE.exists():
        try:
            hist = json.loads(HOURS_FILE.read_text(encoding="utf-8"))
        except Exception:
            hist = {}

    for uid, words, rule, stacks in UNITS:
        items = []
        for w in words:
            if w not in cache:
                try:
                    got = []
                    find_items(call(w), got)
                    cache[w] = got
                    print(f"[{w}] {len(got)}건")
                except Exception as e:
                    cache[w] = []
                    errors.append(f"{uid}: {e}")
            items += cache[w]

        mine = [it for it in items if match(str(it.get("fact_manage_nm", "")), rule)]
        if not items:
            errors.append(f"{uid}: 검색 결과 0건")
        elif not mine:
            names = sorted({str(it.get("fact_manage_nm")) for it in items})
            errors.append(f"{uid}: 등록명 못 찾음 (검색 결과: {', '.join(names)})")
        found = {str(it.get("stack_code")): it for it in mine}

        states, unit_dt = [], None
        for no in stacks:
            it = found.get(no, {})
            states.append(stack_state(it.get("nox_mesure_value")))
            dt = it.get("mesure_dt")
            if dt:
                times.append(dt)
                unit_dt = max(unit_dt or dt, dt)

        if "on" in states:
            status = "on"
        elif states and all(s in ("off", "idle") for s in states):
            status = "off"
        else:
            status = "nodata"

        # 가동 중이면 그 '시간대'를 기록 (같은 시간은 한 번만)
        if status == "on" and unit_dt:
            day, hour = unit_dt[:10], unit_dt[11:13]
            lst = hist.setdefault(day, {}).setdefault(uid, [])
            if hour not in lst:
                lst.append(hour)
        hist.setdefault(TODAY, {})

        units.append({"id": uid, "status": status})

    # 발전시간 계산
    def hours(day, uid):
        if day not in hist:
            return None
        return len(hist[day].get(uid, []))

    for u in units:
        u["today_h"] = hours(TODAY, u["id"])
        u["yday_h"] = hours(YDAY, u["id"])

    # 최근 7일만 보관
    for d in sorted(hist)[:-7]:
        del hist[d]
    HOURS_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")

    result = {
        "updated_at": NOW.strftime("%Y-%m-%d %H:%M"),
        "measured_at": max(times) if times else None,
        "units": units,
        "errors": errors,
    }
    with open("tms.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("저장 완료. 실패:", errors or "없음")


if __name__ == "__main__":
    main()
