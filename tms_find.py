"""TMS 사업장 이름 찾기 (한 번만 돌려보는 확인용)
결과는 tms_found.json에 저장됩니다.
"""
import json
import os
import urllib.parse
import urllib.request

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
URL = "https://apis.data.go.kr/B552584/cleansys/rltmMesureResult"

# 화면에 쓸 이름 -> TMS에서 검색해 볼 단어들
SEARCH = {
    "청라에너지": ["청라에너지", "청라"],
    "SK E&S 위례": ["나래에너지", "위례"],
     }


def call(word):
    q = urllib.parse.urlencode({
        "serviceKey": KEY, "factManageNm": word,
        "type": "json", "pageNo": 1, "numOfRows": 100,
    })
    req = urllib.request.Request(URL + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8")
    try:
        return json.loads(text)
    except Exception:
        print("  JSON이 아닌 응답:", text[:300])
        return {}


def find_items(obj, out):
    """응답 안에서 사업장 정보가 든 항목을 모두 찾습니다."""
    if isinstance(obj, dict):
        if "fact_manage_nm" in obj:
            out.append(obj)
        else:
            for v in obj.values():
                find_items(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_items(v, out)


result = {}
for label, words in SEARCH.items():
    rows = []
    for w in words:
        try:
            items = []
            find_items(call(w), items)
            print(f"[{label}] '{w}' 검색: {len(items)}건")
            rows += items
        except Exception as e:
            print(f"[{label}] '{w}' 검색 실패: {e}")
    seen, clean = set(), []
    for it in rows:
        k = (it.get("fact_manage_nm"), it.get("stack_code"))
        if k in seen:
            continue
        seen.add(k)
        clean.append({
            "사업장명": it.get("fact_manage_nm"),
            "지역": it.get("area_nm"),
            "배출구": it.get("stack_code"),
            "측정시간": it.get("mesure_dt"),
            "NOx": it.get("nox_mesure_value"),
            "CO": it.get("co_mesure_value"),
        })
    result[label] = clean

with open("tms_found.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("저장 완료")
