"""TMS 굴뚝 측정값으로 발전기 가동 상태 수집 -> tms.json
- 한국환경공단 굴뚝자동측정기기 측정결과 (DATA_GO_KR_KEY)
- 가동 판단: '가동중지' 표시 -> 정지 / NOx 1 미만 -> 정지 추정 / 그 외 -> 가동
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
URL = "https://apis.data.go.kr/B552584/cleansys/rltmMesureResult"
NOW = datetime.now(timezone(timedelta(hours=9)))

# (화면 이름, 검색어, TMS 등록명, 배출구 번호들)
UNITS = [
    ("에스파워", "에스파워", "㈜에스파워", ["1", "2"]),
    ("삼천리", "삼천리", "㈜삼천리", ["1", "2"]),
    ("안산도시개발", "안산도시개발", "안산도시개발㈜", ["2"]),
    ("GS파워 안양 1호기", "GS파워", "GS파워㈜안양열병합발전처", ["7"]),
    ("GS파워 안양 2호기", "GS파워", "GS파워㈜안양열병합발전처", ["8"]),
    ("GS파워 부천", "GS파워", "GS파워㈜부천열병합발전처", ["1", "2", "3"]),
    ("청라에너지", None, None, []),
    ("인천종합에너지", "인천종합에너지", "인천종합에너지㈜", ["1", "2"]),
    ("위드인천에너지", "위드인천", "위드인천에너지(주)", ["1"]),
    ("SK E&S 위례", "나래에너지", "나래에너지서비스㈜", ["1"]),
    ("SK E&S 하남", "나래에너지", "나래에너지서비스㈜하남사업소", ["1"]),
    ("DS파워", "디에스파워", "디에스파워㈜", ["1", "2"]),
    ("평택에너지앤파워(E1)", "평택에너지", "평택에너지앤파워(주)", ["1", "2", "3"]),
    ("포천파워 1호기", "포천파워", "포천파워㈜", ["1", "2"]),
    ("포천파워 2호기", "포천파워", "포천파워㈜", ["3", "4"]),
    ("포천민자발전", "포천민자", "포천민자발전㈜", ["1", "2", "3"]),
    ("동두천드림파워 1호기", "동두천", "동두천드림파워㈜", ["1", "2"]),
    ("동두천드림파워 2호기", "동두천", "동두천드림파워㈜", ["3", "4"]),
    ("통영에코파워", "통영에코", "통영에코파워(주)", ["1", "2"]),
    ("울산GPS(SK가스)", "지피에스", "울산 지피에스 주식회사", ["6", "7"]),
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


def stack_state(value):
    """굴뚝 하나의 상태: on(가동) / off(가동중지) / idle(정지 추정) / nodata"""
    if value is None:
        return "nodata", None
    s = str(value)
    if "가동중지" in s:
        return "off", None
    try:
        x = float(s)
    except ValueError:
        return "nodata", None
    return ("on" if x >= 1 else "idle"), x


def main():
    cache, errors, units, times = {}, [], [], []

    for name, word, fact, stacks in UNITS:
        if not word:
            units.append({"name": name, "status": "hidden", "stacks": []})
            continue

        # 같은 검색어는 한 번만 호출
        if word not in cache:
            try:
                items = []
                find_items(call(word), items)
                cache[word] = items
                print(f"[{word}] {len(items)}건")
            except Exception as e:
                cache[word] = []
                errors.append(f"{name}: {e}")
                print(f"[경고] {word} 검색 실패: {e}")

        # 등록명이 정확히 같은 것만 (예: '에스파워' 검색에 섞인 '디에스파워' 제외)
        found = {str(it.get("stack_code")): it for it in cache[word]
                 if it.get("fact_manage_nm") == fact}

        rows = []
        for no in stacks:
            it = found.get(no, {})
            state, nox = stack_state(it.get("nox_mesure_value"))
            if it.get("mesure_dt"):
                times.append(it["mesure_dt"])
            rows.append({
                "no": no, "state": state, "nox": nox,
                "std": it.get("nox_exhst_perm_stdr_value"),
            })

        on = sum(r["state"] == "on" for r in rows)
        if on == len(rows):
            status = "on"
        elif on > 0:
            status = "partial"
        elif all(r["state"] in ("off", "idle") for r in rows):
            status = "off"
        else:
            status = "nodata"
        units.append({"name": name, "status": status, "stacks": rows})

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
