"""환율(한국수출입은행) 수집 -> indicators.json 저장
- 별도 설치가 필요 없는 파이썬 기본 기능만 사용합니다.
- API 키는 환경변수 KOREAEXIM_KEY(= GitHub Secrets)에서 읽습니다.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
KEY = os.environ.get("KOREAEXIM_KEY", "").strip()
URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
WANT = ["USD", "JPY(100)", "EUR", "CNH"]  # 가져올 통화


def fetch(day):
    query = urllib.parse.urlencode({"authkey": KEY, "searchdate": day, "data": "AP01"})
    req = urllib.request.Request(URL + "?" + query, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def get_fx():
    now = datetime.now(KST)
    # 주말·공휴일·고시 전에는 빈 값이 오므로, 오늘부터 최대 7일 전까지 거슬러 올라가 가장 최근 값을 사용
    for back in range(8):
        day = (now - timedelta(days=back)).strftime("%Y%m%d")
        data = fetch(day)
        print(f"{day}: 응답 {len(data) if isinstance(data, list) else data}건")
        if not isinstance(data, list) or not data:
            continue
        rates = {r["cur_unit"]: r.get("deal_bas_r") for r in data if r.get("cur_unit") in WANT}
        if rates:
            return {"date": day, "rates": rates}
        print("응답 내용(앞부분):", str(data)[:300])
    raise RuntimeError("최근 8일간 환율 데이터를 가져오지 못했습니다. 인증키와 주소를 확인하세요.")


def main():
    if not KEY:
        sys.exit("KOREAEXIM_KEY가 비어 있습니다. GitHub Secrets 이름을 확인하세요.")
    result = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "fx": get_fx(),
    }
    with open("indicators.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("저장 완료: indicators.json")


if __name__ == "__main__":
    main()
