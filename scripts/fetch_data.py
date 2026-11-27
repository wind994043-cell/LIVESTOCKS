#!/usr/bin/env python3
"""하루 한 번 실행되어 축산 데이터를 모아 data/data.json 으로 저장합니다.
표준 라이브러리만 사용합니다. 한 출처가 실패해도 이전 데이터는 그대로 유지됩니다."""
import json, os, re, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

KST = timezone(timedelta(hours=9))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "data.json")
UA = {"User-Agent": "Mozilla/5.0 (livestock-dashboard)"}
DISEASES = ["구제역", "아프리카돼지열병", "고병원성 조류인플루엔자", "럼피스킨"]


def get(url, timeout=30, tries=3):
    """요청 한도(429) 등 일시적 오류는 잠시 쉬었다가 다시 시도합니다."""
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and n < tries - 1:
                time.sleep(10 * (n + 1))
                continue
            raise


def clean_msg(msg):
    """오류 메시지에 섞인 주소·인증키는 가려서 공개 화면에 노출되지 않게 합니다."""
    msg = re.sub(r"https?://\S+", "[주소 생략]", msg)
    msg = re.sub(r"/openapi/\S+", "[주소 생략]", msg)
    msg = re.sub(r"(?i)apikey=[^&\s]*", "apiKey=***", msg)
    return msg[:160]


def google_news(query, days, limit):
    q = f"{query} when:{days}d"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    items = []
    time.sleep(2)  # 구글 뉴스 요청 한도 방지
    for it in ET.fromstring(get(url)).iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
        except Exception:
            continue
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        items.append({"title": title, "link": it.findtext("link") or "",
                      "source": src, "date": dt.isoformat()})
    return items[:limit]


def dedupe_sort(items):
    seen, out = set(), []
    for i in sorted(items, key=lambda x: x["date"], reverse=True):
        if i["title"] not in seen:
            seen.add(i["title"])
            out.append(i)
    return out


def fetch_news():
    items = []
    for q in ["축산", "축산 수급 가격", "한우 한돈 양계"]:
        items += google_news(q, 7, 20)
    return dedupe_sort(items)[:24]


def fetch_disease():
    week_ago = datetime.now(KST) - timedelta(days=7)
    counts, merged = {}, []
    for name in DISEASES:
        found = google_news(name, 30, 40)
        counts[name] = sum(1 for i in found if datetime.fromisoformat(i["date"]) >= week_ago)
        for i in found[:6]:
            merged.append({**i, "tag": name})
    return {"counts": counts, "items": dedupe_sort(merged)[:16]}


def num(s):
    s = re.sub(r"[^\d.]", "", str(s or ""))
    return float(s) if s else None


def fetch_prices(key, uid):
    """KAMIS 일별 부류별 도소매가격(축산물 500). 당일 자료가 없으면 최대 4일 전까지 거슬러 올라갑니다."""
    today = datetime.now(KST).date()
    for back in range(5):
        d = today - timedelta(days=back)
        qs = urllib.parse.urlencode({
            "action": "dailyPriceByCategoryList", "p_cert_key": key, "p_cert_id": uid,
            "p_returntype": "json", "p_product_cls_code": "01", "p_item_category_code": "500",
            "p_country_code": "1101", "p_regday": d.isoformat(), "p_convert_kg_yn": "N"})
        data = json.loads(get("http://www.kamis.or.kr/service/price/xml.do?" + qs))
        body = data.get("data") if isinstance(data, dict) else None
        if not isinstance(body, dict) or body.get("error_code") != "000":
            continue
        items = body.get("item") or []
        if isinstance(items, dict):
            items = [items]
        rows = []
        for i in items:
            p = num(i.get("dpr1"))
            if p is None:
                continue
            rows.append({"item": i.get("item_name"), "kind": i.get("kind_name"),
                         "rank": i.get("rank"), "unit": i.get("unit"), "price": p,
                         "prev_day": num(i.get("dpr2")), "prev_month": num(i.get("dpr3")),
                         "prev_year": num(i.get("dpr4"))})
        if rows:
            return {"date": d.isoformat(), "market": "서울 소매", "rows": rows}
    raise RuntimeError("KAMIS 응답에 가격 데이터가 없습니다 (인증키/ID 확인)")


def fetch_stats_one(url):
    """KOSIS 통계표 API 주소(JSON) 하나를 받아 시계열별 최근 6개 값으로 정리합니다."""
    data = json.loads(get(url))
    if isinstance(data, dict):
        raise RuntimeError(data.get("errMsg") or "KOSIS 오류")
    series = {}
    for r in data:
        name = " ".join(x for x in (r.get("C1_NM"), r.get("C2_NM"), r.get("ITM_NM")) if x) or r.get("TBL_NM", "")
        v = num(r.get("DT"))
        if v is None:
            continue
        s = series.setdefault(name, {"name": name, "unit": r.get("UNIT_NM", ""), "points": []})
        s["points"].append({"period": r.get("PRD_DE"), "value": v})
    out = []
    for s in list(series.values())[:10]:
        s["points"] = sorted(s["points"], key=lambda p: p["period"])[-6:]
        out.append(s)
    return out


def fetch_stats(urls):
    """KOSIS_URL에 주소가 여러 개(줄바꿈/공백으로 구분) 들어 있어도 모두 읽어 합칩니다."""
    out = []
    for u in urls.split():
        out += fetch_stats_one(u)
    if not out:
        raise RuntimeError("KOSIS 주소에서 읽은 데이터가 없습니다")
    return out


def main():
    try:
        with open(OUT, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.setdefault("news", []); data.setdefault("disease", {"counts": {}, "items": []})
    data.setdefault("prices", None); data.setdefault("stats", [])
    status = {}

    def run(name, fn, enabled=True, why=""):
        if not enabled:
            status[name] = {"state": "skipped", "msg": why}
            return
        try:
            data[name] = fn()
            status[name] = {"state": "ok"}
        except Exception as e:  # 실패해도 이전 값 유지
            status[name] = {"state": "error", "msg": clean_msg(f"{type(e).__name__}: {e}")}

    kk, ki, ku = os.getenv("KAMIS_KEY"), os.getenv("KAMIS_ID"), os.getenv("KOSIS_URL")
    run("news", fetch_news)
    run("disease", fetch_disease)
    run("prices", lambda: fetch_prices(kk, ki), bool(kk and ki), "KAMIS_KEY / KAMIS_ID 미설정")
    run("stats", lambda: fetch_stats(ku), bool(ku), "KOSIS_URL 미설정")

    data["updated"] = datetime.now(KST).isoformat(timespec="minutes")
    data["status"] = status
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for k, v in status.items():
        print(k, v)


if __name__ == "__main__":
    main()
