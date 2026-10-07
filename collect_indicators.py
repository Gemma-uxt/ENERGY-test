"""시장지표 수집 -> indicators.json / history.json 저장
- 환율: 한국수출입은행 (KOREAEXIM_KEY)
- 국제유가·JKM: OilPriceAPI (OILPRICE_API_KEY)
- 별도 설치가 필요 없는 파이썬 기본 기능만 사용합니다.
- 한 항목이 실패해도 나머지는 저장하고, 실패 내용은 errors에 기록합니다.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
TODAY = NOW.strftime("%Y-%m-%d")

EXIM_KEY = os.environ.get("KOREAEXIM_KEY", "").strip()
OIL_KEY = os.environ.get("OILPRICE_API_KEY", "").strip()

EXIM_URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
OIL_URL = "https://api.oilpriceapi.com/v1/prices/latest"
OIL_CODES = {  # OilPriceAPI 코드 -> 화면에서 쓰는 이름
    "DUBAI_CRUDE_USD": "dubai",
    "BRENT_CRUDE_USD": "brent",
    "WTI_USD": "wti",
    "JKM_LNG_USD": "jkm",
}


def http_json(url, headers=None):
    h = {"User-Agent": "Mozilla/5.0"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def num(x):
    return float(str(x).replace(",", ""))


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ---------- 환율 ----------
def get_fx():
    found = []  # (날짜, {통화: 값}) 최신 -> 과거 순으로 2개
    for back in range(14):
        day = (NOW - timedelta(days=back)).strftime("%Y%m%d")
        rows = http_json(EXIM_URL + "?" + urllib.parse.urlencode(
            {"authkey": EXIM_KEY, "searchdate": day, "data": "AP01"}))
        n = len(rows) if isinstance(rows, list) else rows
        print(f"[환율] {day}: 응답 {n}건")
        if isinstance(rows, list) and rows:
            rates = {r["cur_unit"]: num(r["deal_bas_r"]) for r in rows
                     if r.get("cur_unit") in ("USD", "JPY(100)") and r.get("deal_bas_r")}
            if rates:
                found.append((f"{day[:4]}-{day[4:6]}-{day[6:]}", rates))
        if len(found) == 2:
            break
    if not found:
        raise RuntimeError("환율 데이터를 가져오지 못했습니다(인증키·주소 확인).")
    (d, cur), prev = found[0], (found[1][1] if len(found) > 1 else {})
    out = {"date": d}
    for cur_unit, name in (("USD", "usd"), ("JPY(100)", "jpy")):
        if cur_unit in cur:
            out[name] = {"value": cur[cur_unit], "prev": prev.get(cur_unit), "date": d}
    return out


# ---------- 국제유가·JKM ----------
def find_prices(obj, out):
    """응답 안에서 code와 price가 함께 있는 항목을 모두 찾습니다."""
    if isinstance(obj, dict):
        if "code" in obj and "price" in obj:
            out[obj["code"]] = obj
        for v in obj.values():
            find_prices(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_prices(v, out)


def price_date(item):
    for k in ("created_at", "updated_at", "time", "timestamp"):
        s = item.get(k)
        if s:
            try:
                return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m-%d")
            except Exception:
                pass
    return TODAY


def get_oil(history):
    url = OIL_URL + "?by_code=" + ",".join(OIL_CODES)
    data = http_json(url, {"Authorization": "Token " + OIL_KEY})
    found = {}
    find_prices(data, found)
    print("[유가] 응답에서 찾은 코드:", sorted(found))
    if not found:
        print("[유가] 응답 앞부분:", json.dumps(data, ensure_ascii=False)[:400])
        raise RuntimeError("유가 응답에서 가격을 찾지 못했습니다.")
    out = {}
    for code, name in OIL_CODES.items():
        item = found.get(code)
        if not item:
            continue
        value, d = num(item["price"]), price_date(item)
        hist = history.setdefault(name, [])
        hist[:] = [h for h in hist if h["date"] != d] + [{"date": d, "value": value}]
        hist.sort(key=lambda h: h["date"])
        del hist[:-40]
        earlier = [h for h in hist if h["date"] < d]
        out[name] = {"value": value, "prev": earlier[-1]["value"] if earlier else None, "date": d}
    return out


def main():
    result = load("indicators.json", {})
    history = load("history.json", {})
    errors = []
    for label, key, fn, slot in (
        ("환율", EXIM_KEY, get_fx, "fx"),
        ("국제유가", OIL_KEY, lambda: get_oil(history), "oil"),
    ):
        try:
            if not key:
                raise RuntimeError("인증키가 비어 있습니다(Secrets 이름 확인).")
            result[slot] = fn()
        except Exception as e:  # 한 항목이 실패해도 계속 진행
            print(f"[경고] {label} 수집 실패: {e}")
            errors.append(f"{label}: {e}")
    result["updated_at"] = NOW.strftime("%Y-%m-%d %H:%M")
    result["errors"] = errors
    with open("indicators.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print("저장 완료. 실패 항목:", errors or "없음")


if __name__ == "__main__":
    main()
