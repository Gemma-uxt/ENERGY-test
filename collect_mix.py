"""발전원별 발전량(계통기준, 5분 단위) 수집 -> power_mix.json
- 한국전력거래소_발전원별 발전량(계통기준)
- 매시간 실행해 기록을 쌓고, 시간대별 평균을 계산
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
# ▼ data.go.kr 마이페이지에서 확인한 End Point + 기능 이름
MIX_URL = "https://apis.data.go.kr/B552115/PwrAmountByGen/getPwrAmountByGen"
NOW = datetime.now(timezone(timedelta(hours=9)))
FILE = Path("power_mix.json")
KEEP_DAYS = 3

FUELS = {
    "fuelPwr1": "수력", "fuelPwr2": "유류", "fuelPwr3": "유연탄",
    "fuelPwr4": "원자력", "fuelPwr5": "양수", "fuelPwr6": "LNG",
    "fuelPwr7": "국내탄", "fuelPwr8": "신재생", "fuelPwr9": "태양광",
}

def call():
    q = urllib.parse.urlencode({
        "serviceKey": KEY, "pageNo": 1, "numOfRows": 300, "dataType": "JSON",
    })
    last = None
    for attempt in range(3):          # 실패하면 10초 쉬고 최대 3번 시도
        try:
            req = urllib.request.Request(MIX_URL + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode("utf-8")
            return json.loads(text)
        except ValueError:
            last = RuntimeError("응답이 JSON이 아님: " + text[:200])
        except Exception as e:
            last = e
        time.sleep(10)
    raise last

def find_rows(obj, out):
    if isinstance(obj, dict):
        if any(str(k).startswith("fuelPwr") for k in obj):
            out.append(obj)
        else:
            for v in obj.values():
                find_rows(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_rows(v, out)


def stamp(row):
    """행에서 'YYYYMMDDHHMM' 시각 찾기 (없으면 지금 시각)"""
    for k, v in row.items():
        if "date" in k.lower() or k.lower().endswith("dt"):
            s = re.sub(r"\D", "", str(v))
            if len(s) >= 12:
                return s[:12]
    return NOW.strftime("%Y%m%d%H%M")


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def extras(v):
    """석탄 합계, 총 발전, 순부하 추가"""
    v = dict(v)
    total = sum(max(v.get(n) or 0, 0) for n in FUELS.values())
    v["석탄"] = round((v.get("유연탄") or 0) + (v.get("국내탄") or 0), 1)
    v["합계"] = round(total, 1)
    v["순부하"] = round(total - (v.get("태양광") or 0) - (v.get("신재생") or 0), 1)
    return v


def main():
    old = {}
    if FILE.exists():
        try:
            old = json.loads(FILE.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    raw, errors, sample = old.get("raw", {}), [], old.get("sample")

    try:
        rows = []
        find_rows(call(), rows)
        if not rows:
            raise RuntimeError("발전원 데이터 없음")
        sample = rows[0]
        for row in rows:
            s = stamp(row)
            day = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            vals = {}
            for k, name in FUELS.items():
                x = num(row.get(k))
                if x is not None:
                    vals[name] = x
            raw.setdefault(day, {})[s[8:12]] = vals
        print(len(rows), "건 수집")
    except Exception as e:
        errors.append(f"발전원별 발전량 수집 실패 ({type(e).__name__}) {e}".strip())

    for d in sorted(raw)[:-KEEP_DAYS]:
        del raw[d]

    # 시간대별 평균
    days = {}
    for day, recs in raw.items():
        groups = {}
        for hm, vals in recs.items():
            groups.setdefault(hm[:2], []).append(vals)
        hours = {}
        for hh, lst in sorted(groups.items()):
            avg = {}
            for name in FUELS.values():
                xs = [v[name] for v in lst if name in v]
                if xs:
                    avg[name] = round(sum(xs) / len(xs), 1)
            hours[hh] = extras(avg)
        days[day] = hours

    latest = None
    if raw:
        d = max(raw)
        hm = max(raw[d])
        latest = {"time": f"{d} {hm[:2]}:{hm[2:]}", "values": extras(raw[d][hm])}

    result = {
        "updated_at": NOW.strftime("%Y-%m-%d %H:%M"),
        "latest": latest,
        "days": days,
        "raw": raw,
        "sample": sample,
        "errors": errors,
    }
    FILE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장 완료. 실패:", errors or "없음")


if __name__ == "__main__":
    main()
