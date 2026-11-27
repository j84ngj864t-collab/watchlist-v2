#!/usr/bin/env python3
"""Build a self-contained watchlist dashboard (index.html).

Usage:
  python3 build.py             # fetch stale/missing data, then render
  python3 build.py --offline   # render from cache only
  python3 build.py --force     # refetch all sources
  python3 build.py --wait-eod  # wait until Massive may have the prior NY session, then refetch dailies

Massive Stocks Basic: 5 calls/min. Throttle >=13s. Never log the API key.
Read the key from the MASSIVE_API_KEY environment variable (never hardcode).
Optional: MASSIVE_KEY_PATH may point to a local 0600 key file if the env var is unset.
"""
from __future__ import annotations

import argparse
import subprocess, csv, json, os, re, stat, time, datetime as dt, urllib.request, urllib.parse, urllib.error
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
from extra_data import fetch_extra, process_extra
DATA = ROOT / "data"
RAW = DATA / "raw"
PROC = DATA / "processed"
TPL = ROOT / "templates"
NY = ZoneInfo("America/New_York")
TPE = ZoneInfo("Asia/Taipei")
HOST = "api.massive.com"
# Do not hardcode a key or a machine-specific path. See read_key().
KEY_PATH = None  # unused; kept so older comments still parse. Prefer MASSIVE_API_KEY.
MIN_GAP = 13.0
TICKERS = ["AAPL","ACN","AFRM","AMD","AMZN","ANT","APP","AVGO","CL","CMCSA","COHR","COST","CRM","CRWD","DUOL","EBAY","FTNT","GD","GOOG","HAPN","HUBS","IBM","INTC","ITW","KO","LITE","LLY","LMT","META","MRVL","MRNA","MSFT","NET","NOW","NVDA","OKTA","ORCL","PANW","PG","PGY","PINS","PLTR","QCOM","RDDT","RLAY","S","SHOP","SNOW","SOFI","SOXX","SPCX","SPOT","TMDX","TSM","UPST","VEEV","ZS"]
SPCX_START = "2026-06-12"
DAILY_START = "2024-11-01"
UA = "WatchlistDashboard/1.0 (personal research; local offline page)"
UA_WEB = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"

VALUE_HEADER = """
<p>已審篩選（value-stocks-20261114，投資 CEO 已核）。初選 26 檔，用 SEC 一手 5 年 FCF（OCF−資本支出）：5 年皆正、最低／最高 ≥ 0.5、最近一年 ≥ 5 年均值 0.7 倍；4 年營收 CAGR ≥ 0%；股息／FCF ≤ 75%；淨負債／TTM EBITDA ≤ 3.0x。估值閘門：forward PE ≤ 20x 且 FCF yield ≥ 4%。<strong>本輪沒有一檔達「分批」</strong>，全部是條件式判斷，不是買進指令。</p>
<p>LMT、ACN 估值已過閘門，只差價量條件，稿中屬「接近分批」觀察，目前判斷仍是<strong>觀望</strong>。CMCSA 列<strong>可能價值陷阱</strong>（NBCU 與 Sky 預計 2027 年中分拆，TTM FCF 含將分出的業務，FCF yield 可能高估）。ITW、IBM 為備選；IBM 因淨負債／EBITDA 3.08x 超過 3.0x，在本框架下列「不建議」，不是對 IBM 整體的判斷。</p>
<p>口徑：市值＝SEC 10-Q／10-K 封面股數 × 11/13 收盤（封面早約 4–6 週，沒用 Massive 股數）；殖利率＝最新季配 × 4 ÷ 收盤；EBITDA＝GAAP 營業利益＋折舊攤銷（IBM 改用稅前利益＋利息＋折舊攤銷，口徑不同）。Forward PE 無免費共識 NTM，改用公司當年度指引；CMCSA、IBM 為 TTM GAAP，非 forward。GD 的 2026 EPS 指引來源為媒體【媒】，未核 IR 原文。追價區（距 SMA20 &gt;3% 且距 SMA50 &gt;8%）與縮量回測是稿中已標明的自訂規則。Massive 為拆股調整日線，非官方收盤、非含息總報酬。不保證報酬，追蹤清單不等於持倉或交易授權。</p>
<p>KO、COST 為使用者指定加入、未通過篩選，判斷為<strong>不建議（本框架）</strong>，不是對這兩家公司整體的評價。KO 未過 G1、G3、G5、G6；COST 未過 G1、G6，屬優質成長而非價值股。詳見 value-stocks-ko-cost-20261114.md。</p>
"""

CATS = [
  {"id":"all","name":"全部","blurb":"56 檔關注持股；價量美東 2026-11-23（Massive，DELAYED）。11/24 晚間已依統一趨勢規則（收盤低於 SMA50 且 SMA20 低於 SMA50 → 不建議）重算，基本面未重審。條件式研究，不是交易指令。"},
  {"id":"chip","name":"AI 晶片","blurb":"價量美東 11/23。ANT 仍未滿 20 交易日，暫不判定。AMD、AVGO、LITE、SPCX 因統一趨勢規則由觀望改為不建議（價格規則，非基本面否決）。AAPL、AMZN 觀望。TSM、NVDA 等仍為不建議。不是交易指令。"},
  {"id":"pharma","name":"AI 醫療","blurb":"價量美東 11/23。TMDX 持有中（新資金觀望）。RLAY 今早曾因站回前 20 日低改回觀望，套用統一趨勢規則後再改為不建議（價格規則，非基本面否決）。MRNA、LLY 觀望。不是交易指令。"},
  {"id":"lending","name":"AI 借貸","blurb":"價量美東 11/23。HAPN 觀望，PGY、SOFI、UPST、AFRM 維持不建議。依目前判斷排序，非交易先後。不是交易指令。"},
  {"id":"security","name":"AI 資安","blurb":"價量美東 11/23。CRWD 今早已因帶量跌破前 20 日低改為不建議（維持）。NET、PANW 因統一趨勢規則由觀望改為不建議（價格規則，非基本面否決）。ZS、OKTA、S 觀望，FTNT 不建議。不是交易指令。"},
  {"id":"apps","name":"AI 應用","blurb":"價量美東 11/23。PLTR、SNOW 今早曾因站回前 20 日低改回觀望，套用統一趨勢規則後再改為不建議（價格規則，非基本面否決）。EBAY、APP、SPOT、DUOL 觀望。其餘多檔仍為不建議。依目前判斷排序，非交易先後。不是交易指令。"},
  {"id":"value","name":"價值股","blurb":"價量美東 11/23。GD 改回觀望（價格規則解除）。觀望：CL、PG、LMT、GD；不建議：ACN；不建議（本框架）：CMCSA、KO、COST；備選：ITW、IBM。本輪無分批，不是買進指令。","header": VALUE_HEADER},
  {"id":"macro","name":"總經","blurb":"恐慌指數、散戶資金、升息押注、點陣圖、油價、國債拍賣，以及聯準會廣義美元指數（DTWEXBGS，不是 ICE DXY）。"},
]

PRESS_DEF = (
  "<p>壓力價是技術參考，<strong>不是預測</strong>，也不是進出場指令。只標現價上方、最多 3 條，選取規則如下：</p>"
  "<ol>"
  "<li>近 252 個交易日的日內高點（約 52 週高）。若上市不足 252 日（例如 SPCX），改用上市以來高點，並在標籤註明。不接上已更名為 SPCK 的舊 ETF 歷史。</li>"
  "<li>近 60 個交易日的日內高點。若與上一項是同一根 K 線或價位差距不到 0.5%，則跳過以免重複。</li>"
  "<li>最近一個已確認的擺盪高點：日內高點為前後各 5 根（共 11 根）的最高，且嚴格高於現價、與已選價位差距超過 0.5%。</li>"
  "</ol>"
  "<p>現價若已接近或高於近 52 週／上市以來高點，現價上方可能沒有獨立壓力價，卡片會直接註明。圖表的月線是 SMA20、季線是 SMA60，皆為含當日的收盤算術平均。</p>"  "<p>另外，當常規收盤低於月線（SMA20）或季線（SMA60，約 60 個交易日）時，卡片正面會顯示該均線數值作為壓力價，並標距收盤百分比。兩者皆在上方則標「站上月線/季線」。上市未滿 20 或 60 根（例如 ANT）則標「資料不足」。這是技術參考，<strong>不是</strong>進出場指令，也不改判斷。</p>"
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def now_tpe() -> dt.datetime:
    return dt.datetime.now(TPE)


def now_pair():
    t = now_tpe()
    return t.isoformat(), t.astimezone(NY).isoformat()


def num(x):
    if x is None or x == "" or str(x).strip().upper() in {"UNCH", "N/A", "NA", ".", "NULL"}:
        return None
    try:
        return float(str(x).replace(",", "").replace("%", "").replace("+", "").replace("$", "").strip())
    except ValueError:
        return None


def money(n, d=2):
    if n is None or not isinstance(n, (int, float)):
        return "—"
    return f"{n:,.{d}f}"


def read_key():
    """Return the Massive API key. Prefer MASSIVE_API_KEY; never log the value."""
    env = (os.environ.get("MASSIVE_API_KEY") or "").strip()
    if env:
        if len(env) > 4096 or not env.isascii() or any(c.isspace() for c in env):
            raise RuntimeError("credential_format")
        return env
    key_path = (os.environ.get("MASSIVE_KEY_PATH") or "").strip()
    if not key_path:
        raise RuntimeError("missing_MASSIVE_API_KEY")
    parent = os.lstat(os.path.dirname(key_path))
    info = os.lstat(key_path)
    if not (stat.S_ISDIR(parent.st_mode) and stat.S_IMODE(parent.st_mode) == 0o700 and parent.st_uid == os.getuid()
            and stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid()):
        raise RuntimeError("credential_metadata")
    fd = os.open(key_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8-sig") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600:
            raise RuntimeError("credential_fstat")
        token = f.read(4097).strip()
    if not token or len(token) > 4096 or not token.isascii() or any(c.isspace() for c in token):
        raise RuntimeError("credential_format")
    return token


def http_get(url, headers=None, timeout=30, max_bytes=5_000_000):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise RuntimeError("size_limit")
        return getattr(resp, "status", None) or resp.getcode(), body, resp.headers


def last_weekday_before(d: dt.date) -> dt.date:
    cand = d - dt.timedelta(days=1)
    while cand.weekday() >= 5:
        cand -= dt.timedelta(days=1)
    return cand


def last_completed_session(now_ny: dt.datetime | None = None) -> str:
    """Most recent regular US cash session that has already closed (ignores holidays)."""
    now_ny = now_ny or dt.datetime.now(NY)
    d = now_ny.date()
    if d.weekday() < 5 and (now_ny.hour > 16 or (now_ny.hour == 16 and now_ny.minute >= 5)):
        return d.isoformat()
    return last_weekday_before(d).isoformat()


def expected_massive_eod(now_ny: dt.datetime | None = None) -> str:
    """Date Massive Basic is expected to have as a complete daily bar.

    Basic typically publishes the prior session after NY midnight. If it is
    still the same NY calendar day as the session (even after the close),
    that session's bar is not expected yet.
    """
    now_ny = now_ny or dt.datetime.now(NY)
    return last_weekday_before(now_ny.date()).isoformat()


def ticker_last_daily(tk: str) -> str | None:
    p = RAW / "massive" / f"{tk}.json"
    if not p.exists():
        return None
    bars = bars_from_massive(p)
    return bars[-1]["d"] if bars else None


def tickers_behind(expected: str) -> list[str]:
    lagging = []
    for tk in TICKERS:
        d = ticker_last_daily(tk)
        if not d or d < expected:
            lagging.append(tk)
    return lagging


def latest_cached_daily_date() -> str | None:
    """Oldest last-bar date among all watchlist tickers; None if any file is missing."""
    dates = []
    for tk in TICKERS:
        d = ticker_last_daily(tk)
        if not d:
            return None
        dates.append(d)
    return min(dates) if dates else None


def bars_from_massive(path: Path):
    data = json.loads(path.read_text())
    out = []
    for r in data.get("results") or []:
        day = dt.datetime.fromtimestamp(r["t"] / 1000, NY).date().isoformat()
        out.append({"d": day, "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r.get("v") or 0, "t": r["t"]})
    out.sort(key=lambda b: b["d"])
    # de-dup
    seen = {}
    for b in out:
        seen[b["d"]] = b
    return [seen[k] for k in sorted(seen)]


def fetch_massive_daily(tickers=None, force=False, expected=None):
    tickers = list(tickers or TICKERS)
    RAW.joinpath("massive").mkdir(parents=True, exist_ok=True)
    expected = expected or expected_massive_eod()
    need = []
    for tk in tickers:
        p = RAW / "massive" / f"{tk}.json"
        if force or not p.exists():
            need.append(tk)
            continue
        bars = bars_from_massive(p)
        if not bars or bars[-1]["d"] < expected:
            need.append(tk)
    if not need:
        print(f"massive daily cache ok through {expected}")
        return {"skipped": True, "expected": expected}
    token = read_key()
    opener = urllib.request.build_opener(NoRedirect())
    last = None
    manifest = {"started_at_Taipei": now_pair()[0], "calls": 0, "tickers": {}, "expected": expected}
    for i, sym in enumerate(need):
        if last is not None:
            time.sleep(max(0, MIN_GAP - (time.monotonic() - last)))
        start = SPCX_START if sym == "SPCX" else DAILY_START
        end = dt.datetime.now(NY).date().isoformat()
        params = urllib.parse.urlencode({"adjusted": "true", "sort": "asc", "limit": "5000"})
        url = f"https://{HOST}/v2/aggs/ticker/{sym}/range/1/day/{start}/{end}?{params}"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json", "User-Agent": UA})
        last = time.monotonic()
        manifest["calls"] += 1
        retrieved_t, retrieved_n = now_pair()
        entry = {"ticker": sym, "retrieved_at_Taipei": retrieved_t, "retrieved_at_NY": retrieved_n,
                 "url_no_key": f"https://{HOST}/v2/aggs/ticker/{sym}/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=5000"}
        ok = False
        last_err = None
        for attempt in range(3):
            if attempt:
                time.sleep(max(MIN_GAP, 5 * attempt))
                last = time.monotonic()
                retrieved_t, retrieved_n = now_pair()
                entry["retrieved_at_Taipei"] = retrieved_t
                entry["retrieved_at_NY"] = retrieved_n
                manifest["calls"] += 1
            try:
                with opener.open(req, timeout=60) as resp:
                    body = resp.read(5_000_001)
                    http = getattr(resp, "status", 200)
                data = json.loads(body)
                (RAW / "massive" / f"{sym}.json").write_text(json.dumps(data, ensure_ascii=False))
                bars = bars_from_massive(RAW / "massive" / f"{sym}.json")
                entry.update({"ok": True, "http": http, "api_status": data.get("status"), "adjusted": data.get("adjusted"),
                              "n": len(bars), "last": bars[-1]["d"] if bars else None, "attempts": attempt + 1})
                ok = True
                break
            except urllib.error.HTTPError as e:
                last_err = f"HTTP_{e.code}"
                # 403/401 will not recover by retrying immediately
                if e.code in (401, 403, 404):
                    break
            except Exception as e:
                last_err = type(e).__name__
        if not ok:
            entry.update({"ok": False, "error": last_err})
        manifest["tickers"][sym] = entry
        print(f"massive [{i+1}/{len(need)}] {sym} {entry.get('last') or entry.get('error')}", flush=True)
    manifest["ended_at_Taipei"] = now_pair()[0]
    (RAW / "massive" / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def fetch_cnbc_quotes(tickers=None):
    tickers = list(tickers or TICKERS)
    dest = RAW / "cnbc"
    dest.mkdir(parents=True, exist_ok=True)
    joined = "|".join(tickers)
    url = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?"
           + urllib.parse.urlencode({"symbols": joined, "requestMethod": "itv", "noform": "1",
                                     "partnerId": "2", "fund": "1", "exthrs": "1", "extMode": "all", "output": "json"}))
    req = urllib.request.Request(url, headers={"User-Agent": UA_WEB, "Accept": "application/json", "Referer": "https://www.cnbc.com/quotes/AAPL"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        data = json.loads(body)
    prev_path = dest / "_summary.json"
    prev_map = {}
    if prev_path.exists():
        try:
            prev_rows = json.loads(prev_path.read_text())
            if isinstance(prev_rows, list):
                prev_map = {r.get("symbol"): r for r in prev_rows if r.get("symbol")}
            (dest / "_summary.prev.json").write_text(json.dumps(prev_rows, ensure_ascii=False, indent=2))
        except Exception:
            prev_map = {}
    (dest / "batch.json").write_text(json.dumps(data, ensure_ascii=False))
    quotes = (data.get("FormattedQuoteResult") or {}).get("FormattedQuote") or []
    retrieved = now_pair()[0]
    rows = []
    for q in quotes:
        rows.append(_cnbc_row(q, retrieved))
    # fill missing with singles
    have = {r["symbol"] for r in rows}
    for sym in tickers:
        if sym in have:
            continue
        time.sleep(0.4)
        url = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?"
               + urllib.parse.urlencode({"symbols": sym, "requestMethod": "itv", "noform": "1",
                                         "partnerId": "2", "fund": "1", "exthrs": "1", "extMode": "all", "output": "json"}))
        req = urllib.request.Request(url, headers={"User-Agent": UA_WEB, "Accept": "application/json", "Referer": f"https://www.cnbc.com/quotes/{sym}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            (dest / f"{sym}.json").write_text(json.dumps(data, ensure_ascii=False))
            q = ((data.get("FormattedQuoteResult") or {}).get("FormattedQuote") or [None])[0]
            if q:
                rows.append(_cnbc_row(q, retrieved))
        except Exception as e:
            rows.append({"symbol": sym, "ok": False, "reason": type(e).__name__})
    rows = merge_cnbc_clocks(rows, prev_map)
    (dest / "_summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print("cnbc quotes", len(rows), "ok", sum(1 for r in rows if r.get("ok")))
    return rows


def _almost_price(a, b) -> bool:
    try:
        return a is not None and b is not None and abs(float(a) - float(b)) < 0.0005
    except (TypeError, ValueError):
        return False


def merge_cnbc_clocks(rows, prev_map):
    """After the extended session ends, CNBC often returns a date-only last_time.
    Keep the earlier trade clock when the price has not changed."""
    for r in rows:
        old = prev_map.get(r.get("symbol")) or {}
        if not old:
            continue
        if _almost_price(r.get("ah_price"), old.get("ah_price")):
            new_lacks = not cnbc_has_clock(r.get("ah_time")) or not r.get("ah_time_taipei") or "T00:00:00" in str(r.get("ah_time_et") or "")
            old_has = cnbc_has_clock(old.get("ah_time") or old.get("ah_time_et") or "") or (old.get("ah_time_taipei") and "T00:00:00" not in str(old.get("ah_time_taipei") or ""))
            if new_lacks and old_has:
                for k in ("ah_time", "ah_time_et", "ah_time_taipei"):
                    if old.get(k):
                        r[k] = old[k]
        if _almost_price(r.get("regular_close"), old.get("regular_close")):
            new_lacks = not cnbc_has_clock(r.get("regular_time")) or not r.get("regular_time_taipei") or "T00:00:00" in str(r.get("regular_time_et") or "")
            old_has = cnbc_has_clock(old.get("regular_time") or old.get("regular_time_et") or "")
            if new_lacks and old_has:
                for k in ("regular_time", "regular_time_et", "regular_time_taipei"):
                    if old.get(k):
                        r[k] = old[k]
    return rows


def cnbc_has_clock(s) -> bool:
    s = str(s or "")
    return "T" in s and ":" in s


def parse_cnbc_time(s):
    if not s:
        return None
    s = str(s).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        # Date only — not a trade clock; callers must not treat this as midnight.
        return None
    if len(s) >= 5 and s[-5] in "+-" and ":" not in s[-5:]:
        s = s[:-2] + ":" + s[-2:]
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_cnbc_timedate(date_s, timedate_s):
    """Combine CNBC last_time + last_timedate (e.g. '7:59 PM EST')."""
    t = parse_cnbc_time(date_s)
    if t:
        return t
    import re as _re
    m = _re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)\s*(EST|EDT|ET)?", str(timedate_s or ""), _re.I)
    if not m or not date_s:
        return None
    hour = int(m.group(1)) % 12
    if m.group(3).upper() == "PM":
        hour += 12
    minute = int(m.group(2))
    raw = str(date_s)
    day_s = raw[:10] if len(raw) >= 10 and raw[4] == "-" else None
    if not day_s:
        return None
    try:
        day = dt.date.fromisoformat(day_s)
    except ValueError:
        return None
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=NY)


def cnbc_session_day(q) -> str | None:
    for key in ("regular_time_et", "regular_time", "regular_time_taipei"):
        s = q.get(key)
        if not s:
            continue
        t0 = parse_cnbc_time(s)
        if t0:
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=NY)
            return t0.astimezone(NY).date().isoformat()
        raw = str(s).strip()
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            return raw[:10]
    return None


def _cnbc_row(q, retrieved):
    ext = q.get("ExtendedMktQuote") or {}
    rt = parse_cnbc_timedate(q.get("last_time"), q.get("last_timedate"))
    at = parse_cnbc_timedate(ext.get("last_time"), ext.get("last_timedate")) if ext else None
    return {
        "ok": True,
        "symbol": q.get("symbol"),
        "name": q.get("name"),
        "exchange": q.get("exchange"),
        "cnbc_source": q.get("source"),
        "provider": q.get("provider"),
        "curmktstatus": q.get("curmktstatus"),
        "regular_close": num(q.get("last")),
        "regular_time": q.get("last_time"),
        "regular_time_et": rt.isoformat() if rt else None,
        "regular_time_taipei": rt.astimezone(TPE).isoformat() if rt else None,
        "regular_change": num(q.get("change")) if q.get("change") not in (None, "UNCH") else (0.0 if q.get("change") == "UNCH" else None),
        "regular_change_pct": num(q.get("change_pct")) if q.get("change_pct") not in (None, "UNCH") else (0.0 if q.get("change_pct") == "UNCH" else None),
        "previous_close": num(q.get("previous_day_closing")),
        "volume": q.get("volume"),
        "ah_type": ext.get("type"),
        "ah_price": num(ext.get("last")),
        "ah_time": ext.get("last_time"),
        "ah_time_et": at.isoformat() if at else None,
        "ah_time_taipei": at.astimezone(TPE).isoformat() if at else None,
        "ah_change": num(ext.get("change")) if ext.get("change") not in (None, "UNCH") else (0.0 if ext.get("change") == "UNCH" else None),
        "ah_change_pct": num(ext.get("change_pct")) if ext.get("change_pct") not in (None, "UNCH") else (0.0 if ext.get("change_pct") == "UNCH" else None),
        "ah_volume": ext.get("volume"),
        "ah_source": ext.get("source"),
        "pe": num(q.get("pe")),
        "eps": num(q.get("eps")),
        "fpe": num(q.get("fpe")),
        "feps": num(q.get("feps")),
        "retrieved_at_Taipei": retrieved,
    }



def format_pe_ratio(pe, eps=None):
    """Display trailing or forward P/E. Negative EPS or PE -> 虧損; missing -> N/A."""
    pe_n = num(pe)
    eps_n = num(eps)
    if pe_n is None and eps_n is None:
        return {"label": "N/A", "kind": "na", "value": None}
    if eps_n is not None and eps_n <= 0:
        return {"label": "虧損", "kind": "loss", "value": None, "eps": eps_n}
    if pe_n is not None and pe_n < 0:
        return {"label": "虧損", "kind": "loss", "value": None}
    if pe_n is None:
        return {"label": "N/A", "kind": "na", "value": None}
    label = f"{pe_n:,.1f}x" if pe_n >= 100 else f"{pe_n:.1f}x"
    return {"label": label, "kind": "ok", "value": round(pe_n, 2)}


def stock_quote_pe(tk, q):
    if tk == "SOXX":
        p = RAW / "ishares" / "soxx-pe.json"
        if p.exists():
            info = json.loads(p.read_text())
            as_of = info.get("as_of") or ""
            pe_n = num(info.get("pe"))
            if pe_n is None:
                trailing = {"label": "N/A", "kind": "na", "value": None}
            else:
                # Keep the official iShares two-decimal formatted value from the cached product page.
                trailing = {"label": f"{pe_n:.2f}x", "kind": "ok", "value": round(pe_n, 2)}
            return {
                "trailing": trailing,
                "forward": {"label": "N/A", "kind": "na", "value": None},
                "sourceShort": f"iShares 持股加權，截至 {as_of}" if as_of else "iShares 持股加權",
                "source": info.get("source") or "",
            }
        return {
            "trailing": {"label": "N/A", "kind": "na", "value": None},
            "forward": {"label": "N/A", "kind": "na", "value": None},
            "sourceShort": "未取到基金本益比",
            "source": "",
        }
    return {
        "trailing": format_pe_ratio((q or {}).get("pe"), (q or {}).get("eps")),
        "forward": format_pe_ratio((q or {}).get("fpe"), (q or {}).get("feps")),
        "sourceShort": "CNBC Quote（延遲／非官方）",
        "source": "CNBC Quote Cache 的 pe／fpe，與盤後價同一批",
    }


def fetch_macro():
    RAW.joinpath("fred").mkdir(parents=True, exist_ok=True)
    log = []
    for sid in ["VIXCLS", "DCOILWTICO", "DCOILBRENTEU", "DFEDTARU", "DFEDTARL", "DTWEXBGS", "NASDAQCOM"]:
        dest = RAW / "fred" / f"{sid}.csv"
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        try:
            code, body, _ = http_get(url, timeout=25)
            dest.write_bytes(body)
            log.append({"series": sid, "ok": True, "http": code, "bytes": len(body)})
            print("FRED", sid, "ok", len(body))
        except Exception as e:
            log.append({"series": sid, "ok": False, "error": type(e).__name__})
            print("FRED", sid, "fail", e)
    # treasury
    RAW.joinpath("treasury").mkdir(parents=True, exist_ok=True)
    today = dt.datetime.now(NY).date().isoformat()
    q = urllib.parse.urlencode({
        "filter": f"auction_date:gte:2025-01-01,auction_date:lte:{today}",
        "sort": "-auction_date",
        "page[size]": "10000",
    })
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?" + q
    try:
        code, body, _ = http_get(url, timeout=40)
        (RAW / "treasury" / "auctions.json").write_bytes(body)
        log.append({"series": "treasury", "ok": True, "http": code, "bytes": len(body)})
        print("treasury ok", len(body))
    except Exception as e:
        log.append({"series": "treasury", "ok": False, "error": type(e).__name__})
        print("treasury fail", e)
    (PROC / "macro-fetch-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))
    return log


def sma(vals, n):
    if len(vals) < n:
        return [None] * len(vals)
    out = [None] * (n - 1)
    s = sum(vals[:n])
    out.append(s / n)
    for i in range(n, len(vals)):
        s += vals[i] - vals[i - n]
        out.append(s / n)
    return out



def ma_pressure(close, s20, s60):
    """Monthly/quarterly MA resistance vs regular close. Display only; not a call rule."""
    def one(val):
        if close is None or val is None or close == 0:
            return {"status": "insufficient", "value": None, "pct": None}
        pct = round(100 * (val / close - 1), 2)
        status = "below" if close < val else "above"
        return {"status": status, "value": val, "pct": pct}
    return {"sma20": one(s20), "sma60": one(s60)}


def pressure_levels(bars, close):
    if not bars or close is None:
        return [], "價格不足，無法計算壓力價。"
    w252 = bars[-252:] if len(bars) >= 252 else bars
    h52 = max(b["h"] for b in w252)
    d52 = next(b["d"] for b in reversed(w252) if b["h"] == h52)
    label52 = "近252日高（約52週）" if len(bars) >= 252 else "上市以來高點"
    w60 = bars[-60:] if len(bars) >= 60 else bars
    h60 = max(b["h"] for b in w60)
    d60 = next(b["d"] for b in reversed(w60) if b["h"] == h60)
    swings = []
    n = len(bars)
    for i in range(5, n - 5):
        window = bars[i - 5:i + 6]
        if bars[i]["h"] == max(b["h"] for b in window) and bars[i]["h"] > close:
            swings.append((bars[i]["h"], bars[i]["d"]))
    selected = []

    def add(price, date, label):
        if price is None or price <= close:
            return
        for p, _, _ in selected:
            if abs(price - p) / p < 0.005:
                return
        if len(selected) >= 3:
            return
        selected.append((price, date, label))

    add(h52, d52, label52)
    if not (d60 == d52 and abs(h60 - h52) / h52 < 0.005):
        add(h60, d60, "近60日高")
    for h, d in reversed(swings):
        add(h, d, "近期擺盪高點")
        if len(selected) >= 3:
            break
    note = None if selected else "現價已位於近 52 週（或上市以來）高點附近，現價上方暫無獨立壓力價。"
    return [{"price": p, "date": d, "label": lab} for p, d, lab in selected], note


def process_stock(research, cnbc_map):
    tk = research["ticker"]
    path = RAW / "massive" / f"{tk}.json"
    out = dict(research)
    out.setdefault("callNote", None)
    if not path.exists():
        out.update({"bars": [], "chartReason": "尚未取到 Massive 日線", "price": None, "date": None,
                    "sma20": None, "sma60": None, "smaPct": None, "smaPos": "down",
                    "maPress": ma_pressure(None, None, None)})
    else:
        raw = json.loads(path.read_text())
        bars = bars_from_massive(path)
        closes = [b["c"] for b in bars]
        s20 = sma(closes, 20)
        s60 = sma(closes, 60)
        for b, a, c in zip(bars, s20, s60):
            b["s20"] = None if a is None else round(a, 4)
            b["s60"] = None if c is None else round(c, 4)
        # chart window ~1y
        chart = bars[-252:] if len(bars) > 252 else bars
        last = bars[-1]
        dist = None if last["s20"] in (None, 0) else 100 * (last["c"] / last["s20"] - 1)
        if dist is None:
            pos = "down"
        elif abs(dist) <= 1.0:
            pos = "mid"
        elif dist > 0:
            pos = "up"
        else:
            pos = "down"
        press, pnote = pressure_levels(bars, last["c"])
        out.update({
            "price": last["c"],
            "date": last["d"],
            "sma20": last["s20"],
            "sma60": last["s60"],
            "smaPct": None if dist is None else round(dist, 2),
            "smaPos": pos,
            "maPress": ma_pressure(last["c"], last["s20"], last["s60"]),
            "bars": [{"d": b["d"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"],
                      "s20": b["s20"], "s60": b["s60"]} for b in chart],
            "pressure": press,
            "pressNote": pnote,
            "rows_total": len(bars),
            "series_start": bars[0]["d"],
            "api_status": raw.get("status"),
        })
        if tk == "SPCX":
            out["seriesNote"] = f"SPCX 自 2026-06-12 上市至 {last['d']} 共 {len(bars)} 個交易日；未接 SPCK 歷史。"
        if tk == "HAPN":
            out["seriesNote"] = (
                f"HAPN 自 2026-06-22 更名起至 {last['d']} 共 {len(bars)} 根日線，"
                "未與舊代碼 LC 歷史拼接；SMA200 不可算。"
            )
        if tk == "ANT":
            out["seriesNote"] = (
                f"ANT（Anthropic, PBC）自 2026-11-19 上市至 {last['d']} 共 {len(bars)} 個交易日；"
                "不足 20 根，不計算 SMA20／SMA60 與前 20 日高低，也不做三選一價量判斷。"
                "Massive 拆股調整日線，DELAYED，不是官方收盤，也不是總報酬。"
            )

    # after-hours + regular close from CNBC
    q = cnbc_map.get(tk) or {}
    if q.get("ok") and q.get("ah_price") is not None:
        tpe = q.get("ah_time_taipei") or ""
        tpe_short = tpe.replace("T", " ")[:19] if tpe else ""
        chg = q.get("ah_change_pct")
        chg_s = "" if chg is None else f"（相對常規收盤 {chg:+.2f}%）"
        out["ahPrice"] = q["ah_price"]
        out["ahChangePct"] = chg
        if tpe_short:
            time_s = f"台北 {tpe_short}"
        else:
            day = str(q.get("ah_time") or "")[:10]
            time_s = (
                f"台北時點未提供（CNBC 僅給日期 {day}）"
                if len(day) == 10 else "台北時點未提供（CNBC 週末只剩日期、沒有鐘點）"
            )
        out["ahHint"] = f"{time_s}{chg_s}。來源：CNBC Quote（{q.get('ah_source') or q.get('cnbc_source') or 'ExtendedMktQuote'}，延遲／非官方），不是交易所官方收盤。"
        out["ahTimeTaipei"] = tpe_short
    else:
        out["ahPrice"] = None
        out["ahHint"] = "資料暫缺：" + (q.get("reason") or "沒有取到盤後成交")
    # regular close: prefer Massive unless CNBC already has a newer completed session
    completed = last_completed_session()
    cnbc_day = cnbc_session_day(q)
    massive_date = out.get("date")
    cnbc_is_newer = bool(cnbc_day and massive_date and cnbc_day > massive_date and cnbc_day == completed)
    reg_day = (cnbc_day if cnbc_is_newer else None) or massive_date or completed
    if massive_date and not cnbc_is_newer:
        prev = None
        # previous massive close
        path = RAW / "massive" / f"{tk}.json"
        bars = bars_from_massive(path)
        if len(bars) >= 2:
            prev = bars[-2]["c"]
        chg_pct = None if not prev else 100 * (out["price"] / prev - 1)
        out["regClose"] = out["price"]
        out["regChangePct"] = None if chg_pct is None else round(chg_pct, 2)
        chg_s = "—" if chg_pct is None else f"{chg_pct:+.2f}%"
        out["regLabel"] = f"{reg_day[5:].replace('-','/')} 常規收盤"
        out["regHint"] = f"{chg_s}　Massive 拆股調整日線，不是官方收盤"
        out["regSource"] = "Massive"
    elif q.get("ok") and q.get("regular_close") is not None:
        out["regClose"] = q["regular_close"]
        out["regChangePct"] = q.get("regular_change_pct")
        chg_s = "—" if q.get("regular_change_pct") is None else f"{q['regular_change_pct']:+.2f}%"
        label_day = (reg_day[5:].replace("-", "/") + " ") if reg_day else ""
        out["regLabel"] = f"{label_day}常規收盤"
        tpe = (q.get("regular_time_taipei") or "").replace("T", " ")[:19]
        out["regHint"] = f"{chg_s}　台北 {tpe}。來源：CNBC Quote（延遲／非官方），Massive 完整日線尚未包含該日"
        out["regSource"] = "CNBC"
    else:
        out["regClose"] = out.get("price")
        out["regLabel"] = f"{(out.get('date') or '')[5:].replace('-','/')} 常規收盤" if out.get("date") else "常規收盤"
        out["regHint"] = "盤後來源未取到該日收盤；圖表仍用 Massive 最新完整日"
        out["regChangePct"] = None
        out["regSource"] = "Massive" if out.get("price") is not None else None
    # Prefer reviewed Massive open-close afterHours (11/21 refresh) over a stale CNBC cache.
    px = research.get("px") or {}
    if px.get("afterHours") is not None:
        ah = px["afterHours"]
        close = out.get("regClose")
        if close is None:
            close = px.get("close") if px.get("close") is not None else out.get("price")
        chg = None if not close else round(100.0 * (float(ah) / float(close) - 1.0), 2)
        day = px.get("date") or out.get("date") or ""
        chg_s = "" if chg is None else f"（相對常規收盤 {chg:+.2f}%）"
        out["ahPrice"] = ah
        out["ahChangePct"] = chg
        out["ahTimeTaipei"] = ""
        out["ahSource"] = "massive-open-close"
        out["ahHint"] = (
            f"美東 {day} 盤後，無鐘點{chg_s}。"
            "來源：Massive Stocks Basic open-close afterHours（adjusted=true），"
            "延遲／非官方，不是交易所官方收盤；盤後價不用於進場判定。"
            "當日日線 API status DELAYED，數值可能修正。"
        )
    out["quotePE"] = stock_quote_pe(tk, q)
    return out


def fred_series(sid, start="2024-11-01"):
    p = RAW / "fred" / f"{sid}.csv"
    if not p.exists():
        return None
    rows = []
    with p.open() as f:
        r = csv.DictReader(f)
        # first col date, second value
        date_key = r.fieldnames[0]
        val_key = r.fieldnames[1]
        for row in r:
            v = num(row[val_key])
            d = row[date_key]
            if v is None or not d or d < start:
                continue
            rows.append({"d": d, "v": v})
    return rows



def attach_sma_points(rows):
    vals = [p["v"] for p in rows]
    s20 = sma(vals, 20)
    s60 = sma(vals, 60)
    pts20 = [{"d": p["d"], "v": None if a is None else round(a, 4)} for p, a in zip(rows, s20)]
    pts60 = [{"d": p["d"], "v": None if a is None else round(a, 4)} for p, a in zip(rows, s60)]
    last20 = next((x["v"] for x in reversed(pts20) if x["v"] is not None), None)
    last60 = next((x["v"] for x in reversed(pts60) if x["v"] is not None), None)
    return pts20, pts60, last20, last60


def rebase_pair(a, b):
    """Inner-join two {d,v} series and rebase both to 100 at the first common date."""
    mb = {p["d"]: p["v"] for p in b}
    pairs = [(p["d"], p["v"], mb[p["d"]]) for p in a if p["d"] in mb]
    if len(pairs) < 2 or not pairs[0][1] or not pairs[0][2]:
        return None
    a0, b0 = pairs[0][1], pairs[0][2]
    ra = [{"d": d, "v": round(100.0 * va / a0, 4)} for d, va, _ in pairs]
    rb = [{"d": d, "v": round(100.0 * vb / b0, 4)} for d, _, vb in pairs]
    # daily returns on raw values
    rets_a, rets_b, ret_dates = [], [], []
    for i in range(1, len(pairs)):
        d, va, vb = pairs[i]
        pa, pb = pairs[i - 1][1], pairs[i - 1][2]
        if pa and pb and pa != 0 and pb != 0:
            rets_a.append(va / pa - 1.0)
            rets_b.append(vb / pb - 1.0)
            ret_dates.append(d)

    def pearson(xs, ys):
        n = len(xs)
        if n < 3:
            return None
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = sum((x - mx) ** 2 for x in xs) ** 0.5
        dy = sum((y - my) ** 2 for y in ys) ** 0.5
        if dx == 0 or dy == 0:
            return None
        return num / (dx * dy)

    corr = pearson(rets_a, rets_b)
    roll = []
    win = 60
    for i in range(len(rets_a)):
        if i + 1 < win:
            roll.append({"d": ret_dates[i], "v": None})
        else:
            c = pearson(rets_a[i + 1 - win:i + 1], rets_b[i + 1 - win:i + 1])
            roll.append({"d": ret_dates[i], "v": None if c is None else round(c, 4)})
    last_roll = next((x["v"] for x in reversed(roll) if x["v"] is not None), None)
    return {
        "startDate": pairs[0][0],
        "endDate": pairs[-1][0],
        "n": len(pairs),
        "a0": a0,
        "b0": b0,
        "aRebased": ra,
        "bRebased": rb,
        "corrDaily": None if corr is None else round(corr, 4),
        "corr60": roll,
        "corr60Last": last_roll,
        "corr60LastDate": next((x["d"] for x in reversed(roll) if x["v"] is not None), None),
    }


def process_macro():
    out = {}
    # VIX from FRED, optionally note if last < expected
    vix = fred_series("VIXCLS", "2024-01-01")
    if vix:
        last = vix[-1]
        out["vix"] = {
            "ok": True,
            "latest": last["v"],
            "latestDate": last["d"],
            "points": vix,
            "sourceShort": "FRED VIXCLS",
            "blurb": "芝加哥選擇權交易所波動率指數的日收盤。FRED 數列 VIXCLS。",
            "source": f"FRED VIXCLS（https://fred.stlouisfed.org/series/VIXCLS），截至 {last['d']}。取數台北 {now_pair()[0][:16]}。",
        }
    else:
        out["vix"] = {"ok": False, "reason": "FRED VIXCLS 檔案不存在或沒有有效觀測值。"}

    wti = fred_series("DCOILWTICO", "2024-01-01")
    brent = fred_series("DCOILBRENTEU", "2024-01-01")
    if wti or brent:
        last_d = max([x[-1]["d"] for x in (wti, brent) if x])
        wti_l = next((x["v"] for x in reversed(wti or []) if x["d"] == last_d), (wti or [{}])[-1].get("v") if wti else None)
        br_l = next((x["v"] for x in reversed(brent or []) if x["d"] == last_d), (brent or [{}])[-1].get("v") if brent else None)
        # if last days differ, show each series' own last in blurb
        wti_last = wti[-1] if wti else None
        br_last = brent[-1] if brent else None
        asof = min([d for d in [wti_last and wti_last["d"], br_last and br_last["d"]] if d]) if (wti_last or br_last) else last_d
        # display latest available of each
        out["oil"] = {
            "ok": True,
            "wti": wti or [],
            "brent": brent or [],
            "wtiLatest": wti_last["v"] if wti_last else None,
            "brentLatest": br_last["v"] if br_last else None,
            "latestDate": f"WTI {wti_last['d'] if wti_last else '—'}／Brent {br_last['d'] if br_last else '—'}",
            "sourceShort": "FRED DCOILWTICO、DCOILBRENTEU",
            "blurb": "現貨價格，單位為美元／桶。EIA 透過 FRED 轉載，通常會晚 1 至 2 個交易日。",
            "source": "FRED DCOILWTICO（WTI Cushing）、DCOILBRENTEU（Brent）。https://fred.stlouisfed.org/series/DCOILWTICO 、 https://fred.stlouisfed.org/series/DCOILBRENTEU",
        }
    else:
        out["oil"] = {"ok": False, "reason": "FRED 油價數列讀取失敗。"}

    # Fed dots + target
    dots_path = PROC / "sep-dots-20260916.htm"  # may not exist
    # parse from saved HTML each time (source of truth)
    html_path = RAW / "fed" / "fomcprojtabl20260916.htm"
    fed = {"ok": False, "reason": "未找到 2026-09-16 SEP 頁面存檔。"}
    if html_path.exists():
        fed = parse_sep_dots(html_path)
    # target range from statement + FRED
    upper = fred_series("DFEDTARU", "2026-01-01")
    lower = fred_series("DFEDTARL", "2026-01-01")
    if fed.get("ok"):
        fed["targetLow"] = 3.75
        fed["targetHigh"] = 4.00
        fed["targetRange"] = "3.75%–4.00%"
        asof = "2026-10-28 FOMC 聲明：維持聯邦基金利率目標區間 3-3/4 至 4%"
        if upper and lower:
            asof += f"；FRED DFEDTARL／DFEDTARU 截至 {lower[-1]['d']} 仍為 3.75／4.00。"
        fed["targetAsOf"] = asof
        fed["blurb"] = "最新官方經濟預測摘要是 2026 年 9 月 15–16 日會議（9 月 16 日下午 2 點 EDT 公布）。其後 10 月 27–28 日會議沒有新的 SEP。下一次 SEP 預定 12 月 8–9 日。"
        fed["source"] = (
            "點陣圖：https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm （Figure 2）。"
            "中位數見同頁 Table 1。現行目標區間：https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm 。"
        )
        fed["years"] = ["2026", "2027", "2028", "2029", "Longer run"]
    out["fed"] = fed


    # Broad dollar index (NOT ICE DXY) + Nasdaq Composite comparison
    # Load a short SMA lookback so early-2022 SMA20/SMA60 are complete; display from 2022-01-03.
    CHART_START = "2022-01-03"
    dollar_full = fred_series("DTWEXBGS", "2021-10-01") or []
    nasdaq_full = fred_series("NASDAQCOM", "2021-10-01") or []
    if dollar_full:
        pts20_full, pts60_full, last20, last60 = attach_sma_points(dollar_full)
        dollar = [p for p in dollar_full if p["d"] >= CHART_START]
        pts20 = [p for p in pts20_full if p["d"] >= CHART_START]
        pts60 = [p for p in pts60_full if p["d"] >= CHART_START]
    else:
        dollar, pts20, pts60, last20, last60 = [], [], [], None, None
    nasdaq = [p for p in nasdaq_full if p["d"] >= CHART_START]
    if dollar:
        last = dollar[-1]
        out["dollar"] = {
            "ok": True,
            "seriesId": "DTWEXBGS",
            "title": "聯準會廣義美元指數",
            "latest": last["v"],
            "latestDate": last["d"],
            "points": dollar,
            "sma20": pts20,
            "sma60": pts60,
            "sma20Latest": last20,
            "sma60Latest": last60,
            "sourceShort": "FRED DTWEXBGS",
            "blurb": "這不是 ICE 美元指數 DXY。本圖使用聯準會廣義美元指數 DTWEXBGS（對一籃子貨物貿易對手貨幣的名目貿易加權指數），日線自 2022-01-03 起。FRED 轉載 Fed H.10，通常會晚數個交易日，不是即時行情，也不是 ICE 官方收盤。圖上月線為 SMA20、季線為 SMA60，皆為含當日的收盤算術平均。",
            "source": f"FRED DTWEXBGS（https://fred.stlouisfed.org/series/DTWEXBGS），截至 {last['d']}。取數台北 {now_pair()[0][:16]}。",
        }
    else:
        out["dollar"] = {"ok": False, "reason": "FRED DTWEXBGS 檔案不存在或沒有有效觀測值。"}

    if nasdaq:
        nlast = nasdaq[-1]
        out["nasdaq"] = {
            "ok": True,
            "seriesId": "NASDAQCOM",
            "latest": nlast["v"],
            "latestDate": nlast["d"],
            "points": nasdaq,
            "sourceShort": "FRED NASDAQCOM",
            "source": f"FRED NASDAQCOM（那斯達克綜合指數，https://fred.stlouisfed.org/series/NASDAQCOM），截至 {nlast['d']}。取數台北 {now_pair()[0][:16]}。",
        }
    else:
        out["nasdaq"] = {"ok": False, "reason": "FRED NASDAQCOM 檔案不存在或沒有有效觀測值。"}

    if dollar and nasdaq:
        cmp = rebase_pair(dollar, nasdaq)
        if cmp:
            out["dollarNasdaq"] = {
                "ok": True,
                "startDate": cmp["startDate"],
                "endDate": cmp["endDate"],
                "n": cmp["n"],
                "dollarStart": cmp["a0"],
                "nasdaqStart": cmp["b0"],
                "dollarRebased": cmp["aRebased"],
                "nasdaqRebased": cmp["bRebased"],
                "corrDaily": cmp["corrDaily"],
                "corr60": cmp["corr60"],
                "corr60Last": cmp["corr60Last"],
                "corr60LastDate": cmp["corr60LastDate"],
                "dollarRebasedEnd": cmp["aRebased"][-1]["v"] if cmp.get("aRebased") else None,
                "nasdaqRebasedEnd": cmp["bRebased"][-1]["v"] if cmp.get("bRebased") else None,
                "dollarRebasedHigh": max(cmp["aRebased"], key=lambda p: p["v"]) if cmp.get("aRebased") else None,
                "dollarRebasedLow": min(cmp["aRebased"], key=lambda p: p["v"]) if cmp.get("aRebased") else None,
                "nasdaqRebasedHigh": max(cmp["bRebased"], key=lambda p: p["v"]) if cmp.get("bRebased") else None,
                "nasdaqRebasedLow": min(cmp["bRebased"], key=lambda p: p["v"]) if cmp.get("bRebased") else None,
                "dollarLatest": dollar[-1]["v"],
                "dollarLatestDate": dollar[-1]["d"],
                "nasdaqLatest": nasdaq[-1]["v"],
                "nasdaqLatestDate": nasdaq[-1]["d"],
                "sourceShort": "FRED DTWEXBGS、NASDAQCOM",
                "blurb": "兩條線都以 2022-01-03（2022 年第一個共同交易日）收盤設為 100，方便比較走勢；不是 ICE DXY，那斯達克為綜合指數（NASDAQCOM），不是那斯達克 100。日報酬相關係數與 60 日滾動相關皆用原始指數日漲跌幅計算。FRED 轉載，通常會晚數個交易日。",
                "source": (
                    f"FRED DTWEXBGS（https://fred.stlouisfed.org/series/DTWEXBGS，截至 {dollar[-1]['d']}）與 "
                    f"FRED NASDAQCOM（https://fred.stlouisfed.org/series/NASDAQCOM，截至 {nasdaq[-1]['d']}）。"
                    f"對照區間 {cmp['startDate']} 至 {cmp['endDate']}（取兩數列共同交易日）。取數台北 {now_pair()[0][:16]}。"
                ),
            }
        else:
            out["dollarNasdaq"] = {"ok": False, "reason": "廣義美元指數與那斯達克綜合指數沒有足夠的共同交易日可對照。"}
    else:
        out["dollarNasdaq"] = {"ok": False, "reason": "缺少 DTWEXBGS 或 NASDAQCOM，無法對照。"}


    # auctions
    out["auctions"] = process_auctions()
    return out


def parse_sep_dots(html_path: Path):
    t = html_path.read_text(errors="replace")
    i = t.find("Figure 2. FOMC participants")
    j = t.find("Figure 3.A")
    if i < 0 or j < 0:
        return {"ok": False, "reason": "SEP 頁面找不到 Figure 2 表格。"}
    sec = t[i:j]
    counts = {}
    for tr in re.findall(r"(?is)<tr>\s*(.*?)</tr>", sec):
        stub = re.search(r'(?is)<th[^>]*class="stub"[^>]*>(.*?)</th>', tr)
        tds = re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)
        if stub and len(tds) == 5:
            def cell(x):
                x = re.sub(r"<[^>]+>", "", x).replace("&nbsp;", "").strip()
                return int(x) if x.isdigit() else 0
            level = re.sub(r"<[^>]+>", "", stub.group(1)).strip()
            counts[f"{float(level):.3f}"] = [cell(x) for x in tds]
    if not counts:
        return {"ok": False, "reason": "Figure 2 表格解析後沒有列。"}
    return {
        "ok": True,
        "counts": counts,
        "medians": {"2026": 4.1, "2027": 4.1, "2028": 3.9, "2029": 3.6, "Longer run": 3.2},
    }


def process_auctions():
    p = RAW / "treasury" / "auctions.json"
    if not p.exists():
        return {"ok": False, "reason": "未取得 Fiscal Data 國債拍賣資料。"}
    try:
        rows = json.loads(p.read_text()).get("data") or []
    except Exception:
        return {"ok": False, "reason": "國債拍賣 JSON 無法解析。"}
    if not rows:
        return {"ok": False, "reason": "拍賣資料沒有列。"}

    wanted = [
        ("4 週票據", "Bill", "4-Week", "high_investment_rate", "投資利率（債券等值）"),
        ("13 週票據", "Bill", "13-Week", "high_investment_rate", "投資利率（債券等值）"),
        ("26 週票據", "Bill", "26-Week", "high_investment_rate", "投資利率（債券等值）"),
        ("2 年期票據", "Note", "2-Year", "high_yield", "得標殖利率"),
        ("5 年期票據", "Note", "5-Year", "high_yield", "得標殖利率"),
        ("10 年期票據", "Note", "10-Year", "high_yield", "得標殖利率"),
        ("30 年期公債", "Bond", "30-Year", "high_yield", "得標殖利率"),
    ]

    def match(r, typ, term):
        if r.get("security_type") != typ:
            return False
        if typ == "Bill":
            return r.get("security_term") == term and r.get("cash_management_bill_cmb") in ("No", "N", None, "")
        # notes/bonds: original term, exclude TIPS/FRN
        if r.get("inflation_index_security") not in ("No", "N", None, ""):
            return False
        if r.get("floating_rate") not in ("No", "N", None, ""):
            return False
        return (r.get("original_security_term") or r.get("security_term")) == term

    latest = []
    series = []
    colors = {"13 週票據": None, "2 年期票據": "var60", "10 年期票據": "press", "30 年期公債": "press"}
    dashed = {"30 年期公債": True}
    for label, typ, term, field, rate_label in wanted:
        cand = [r for r in rows if match(r, typ, term) and num(r.get(field)) is not None and r.get("auction_date")]
        cand.sort(key=lambda r: r["auction_date"])
        if not cand:
            latest.append({"tenor": label, "auctionDate": "—", "rate": None, "rateLabel": rate_label, "btc": None})
            continue
        last = cand[-1]
        latest.append({
            "tenor": label,
            "auctionDate": last["auction_date"],
            "rate": num(last.get(field)),
            "rateLabel": rate_label,
            "btc": num(last.get("bid_to_cover_ratio")),
        })
        if label in colors or label == "13 週票據":
            series.append({
                "name": label,
                "color": colors.get(label),
                "dashed": dashed.get(label, False),
                "points": [{"d": r["auction_date"], "v": num(r.get(field))} for r in cand if r["auction_date"] >= "2025-01-01"],
            })
    max_d = max((r.get("auction_date") or "" for r in rows), default="")
    lag_note = f"此資料集目前最新拍賣日為 {max_d}，其後的標售若尚未入庫，表中不會出現。" if max_d else ""
    return {
        "ok": True,
        "latest": latest,
        "series": series,
        "blurb": "票據與公債列得標最高殖利率（high yield）；國庫券列投資利率（high investment rate，債券等值），不是貼現率。不含 TIPS、浮動利率券與現金管理票據。同一期限若有再發行，國庫券以本次剩餘期限（security_term）為準，票據／公債以原始期限為準。" + lag_note,
        "source": "U.S. Treasury Fiscal Data「Treasury Securities Auctions Data」https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query 。資料集內最新拍賣日見表；本輪檔案的拍賣日起迄以原始 JSON 為準。取數台北 " + now_pair()[0][:16] + "。",
    }


def fmt_tpe_short(iso):
    if not iso:
        return ""
    return iso.replace("T", " ")[:19]


def render(stocks, macro, meta):
    css = (TPL / "styles.css").read_text()
    js = (TPL / "app.js").read_text()
    cnn_dial = (TPL / "cnn-fng-dial.svg").read_text()
    cnn_needle = (TPL / "cnn-fng-needle.svg").read_text()
    payload = {"cats": CATS, "stocks": stocks, "macro": macro, "pressDef": PRESS_DEF, "meta": meta}
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    banner = ""
    if meta.get("daily_lag_note"):
        banner = f'<aside class="lag-note"><strong>日線更新說明：</strong>{escape(meta["daily_lag_note"])}</aside>'
    footer_items = meta["footer"]
    lis = "\n          ".join(f"<li>{item}</li>" for item in footer_items)
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark light">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <meta http-equiv="refresh" content="300">
  <title>關注持股看板｜僅供本人自用</title>
  <style>
{css}
  </style>
</head>
<body>
  <template id="tpl-cnn-dial">{cnn_dial}</template>
  <template id="tpl-cnn-needle">{cnn_needle}</template>
  <div class="app">
    <aside class="sidebar" id="sidebar">
      <div class="brand-row">
        <div class="brand-head">
          <div class="brand">
            <div class="brand-kicker">Watchlist</div>
            <h1>關注持股看板</h1>
            <p>陳煒川　僅供本人自用<br>研究用途，不是下單指令</p>
          </div>
          <button class="menu-toggle" id="menuToggle" type="button" aria-expanded="false" aria-controls="navPanel">分類</button>
        </div>
        <div class="ask-box">
          <form class="ask-form" role="search">
            <input class="ask-input" type="search" name="q" placeholder="問 Google AI…" autocomplete="off" enterkeyhint="search" aria-label="問 Google AI">
            <button class="ask-btn" type="submit">ASK</button>
            <a class="ask-alt" href="https://gemini.google.com/app" target="_blank" rel="noopener">Gemini</a>
          </form>
          <div class="ask-meta">
            <p class="ask-hint">在新分頁開啟</p>
            <button type="button" class="ask-hist-toggle" id="askHistToggle" aria-expanded="false" aria-controls="askHistory">
              <span class="full">搜尋紀錄</span><span class="short">紀錄</span>
            </button>
          </div>
          <div class="ask-history" id="askHistory" hidden>
            <div class="ask-history-head">
              <span>搜尋紀錄</span>
              <button type="button" class="ask-hist-clear" id="askHistClear">清除全部</button>
            </div>
            <ul class="ask-history-list" id="askHistoryList"></ul>
            <p class="ask-history-empty" id="askHistoryEmpty">尚無搜尋紀錄</p>
          </div>
        </div>
        <div class="reports-box">
          <div class="reports-label">研究報告</div>
          <ul class="reports-list">
            <li><a href="reports/ai-disruption-20261123.html">AI 時代產業金流轉移</a></li>
            <li><a href="reports/agentic-commerce-20261123.html">Agent 消費端口的受益者</a></li>
            <li><a href="reports/spacex-tsla-cashflow-20261117.html">SpaceX／Tesla 現金流與 Terafab</a></li>
            <li><a href="reports/ai-apps-shop-20261117.html">AI 應用：SHOP 與初選 12 檔</a></li>
            <li><a href="reports/hyperscalers-4-20261117.html">四大雲：MSFT、AMZN、META、ORCL</a></li>
            <li><a href="reports/midterm-election-20261115.html">期中選舉後一年報酬</a></li>
            <li><a href="reports/midterm-entry-timing-20261116.html">期中選後進場時點</a></li>
          </ul>
        </div>
      </div>
      <div class="nav-panel" id="navPanel">
        <div class="nav-label">分類</div>
        <div class="nav-wrap" id="nav"></div>
      </div>
      <p class="sidebar-note">點選分類後會列出該類股票或總經圖表。盤後價是延遲／非官方報價；圖表與均線用完整日線。已開著的分頁約每 5 分鐘會重新整理。</p>
    </aside>
    <main class="main">
      <div class="topbar">
        <div>
          <h2 id="title">AI 晶片</h2>
          <p class="sub" id="subtitle"></p>
          <p class="data-stamp" id="dataStamp"></p>
        </div>
        <div class="toolbar">
          <button class="ghost" id="themeBtn" type="button" aria-label="切換主題">切換深淺色</button>
        </div>
      </div>
      <div id="banner">{banner}</div>
      <div id="extra"></div>
      <div class="grid" id="grid"></div>
      <footer>
        <p class="footer-lead"><strong>研究用途，非下單指令；不承諾報酬。</strong>判斷不是「現在買」或「現在賣」。分批一律指「符合所列條件才分批」。</p>
        <details class="docs">
          <summary>資料說明</summary>
          <div class="docs-body">
            <h3>價值股篩選</h3>
            {VALUE_HEADER}
            <h3>壓力價怎麼選（技術參考，不是預測）</h3>
            {PRESS_DEF}
            <h3>資料來源與限制</h3>
            <ul>
          {lis}
            </ul>
          </div>
        </details>
      </footer>
    </main>
  </div>
  <script type="application/json" id="payload">{payload_json}</script>
  <script>
{js}
  </script>
</body>
</html>
"""
    dest = ROOT / "index.html"
    dest.write_text(html)
    print("wrote", dest, "bytes", dest.stat().st_size)
    return dest


def _raw_cnbc_quotes():
    quotes = []
    seen = set()
    paths = []
    batch = RAW / "cnbc" / "batch.json"
    if batch.exists():
        paths.append(batch)
    if (RAW / "cnbc").exists():
        paths.extend(sorted(p for p in (RAW / "cnbc").glob("*.json")
                            if p.name not in {"batch.json", "sample-3.json"} and not p.name.startswith("_")))
    for path in paths:
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        for q in (data.get("FormattedQuoteResult") or {}).get("FormattedQuote") or []:
            sym = q.get("symbol")
            # later files (e.g. SOXX.json) override earlier batch rows
            key = (path.name, sym)
            quotes.append(q)
            seen.add(key)
    return quotes


def load_cnbc():
    p = RAW / "cnbc" / "_summary.json"
    out = {}
    if p.exists():
        rows = json.loads(p.read_text())
        for r in rows:
            if "regular_close" in r and isinstance(r.get("regular_close"), str):
                r = dict(r)
                for k in ("regular_close", "regular_change", "regular_change_pct", "previous_close", "ah_price", "ah_change", "ah_change_pct"):
                    r[k] = num(r.get(k)) if r.get(k) not in (None, "UNCH") else (0.0 if r.get(k) == "UNCH" else num(r.get(k)))
            if r.get("symbol"):
                out[r["symbol"]] = r
    # Backfill pe/eps/fpe/feps (and any missing symbol such as SOXX) from raw
    # CNBC files without refetching, so existing after-hours clocks stay intact.
    retrieved = now_pair()[0]
    by_sym = {}
    for q in _raw_cnbc_quotes():
        if q.get("symbol"):
            by_sym[q["symbol"]] = q
    for sym, q in by_sym.items():
        row = _cnbc_row(q, retrieved)
        if sym in out and out[sym].get("ok"):
            cur = out[sym]
            for k in ("pe", "eps", "fpe", "feps"):
                if cur.get(k) is None and row.get(k) is not None:
                    cur[k] = row[k]
        elif sym not in out:
            out[sym] = row
    return out


def build_footer(stocks, macro, meta):
    daily_dates = sorted({s.get("date") for s in stocks if s.get("date")})
    daily_s = "、".join(daily_dates) if daily_dates else "—"
    items = [
        "本頁 2026-11-25 12:26 後更新：總經區廣義美元指數（FRED DTWEXBGS，<strong>不是</strong> ICE DXY）與那斯達克綜合指數（FRED NASDAQCOM）對照圖改自 2022-01-03 起畫，起始日收盤＝100。股票卡片價量與判斷仍為美東 2026-11-23 bar，本輪<strong>未</strong>改判斷、也未改用 11/24 收盤。條件式研究，不是交易指令。",
        "本頁 2026-11-25 更新：總經區新增聯準會廣義美元指數（FRED DTWEXBGS，<strong>不是</strong> ICE 美元指數 DXY）日線圖，含月線 SMA20 與季線 SMA60；並附與那斯達克綜合指數（FRED NASDAQCOM）以起始日＝100 的對照圖。取數通常會晚數個交易日。股票卡片的價量與判斷仍為美東 2026-11-23 bar，本輪<strong>未</strong>改判斷、也未改用 11/24 收盤。條件式研究，不是交易指令。",
        "本頁 2026-11-24 21:27 後更新：依使用者要求，當收盤低於月線（SMA20）或季線（SMA60）時，卡片正面顯示該均線為壓力價及距收盤百分比；兩者皆在上則標「站上月線/季線」；資料不足（例如 ANT 未滿 60 根）則標「資料不足」。價量與判斷仍為美東 2026-11-23 bar，未改判斷、未改用 11/24。壓力價是技術參考，不是進出場指令。",
        "本頁 2026-11-24 晚間更新：依使用者同意，將趨勢規則統一為「收盤低於 SMA50 且 SMA20 低於 SMA50 → 不建議」，套用美東 2026-11-23 bar（未改用 11/24；當日美股交易時段尚未結束）。9 檔由觀望改為不建議：AMD、AVGO、LITE、SPCX、NET、PANW、RLAY、PLTR、SNOW（價格規則，非基本面否決，不是賣出指令）；OKTA、S、CRWD 不變。此規則不再要求收盤低於 SMA200；SPCX 因不足 200 根原先未套用趨勢規則，現已納入。較 11/24 上午看板有變的卡片標「較11/24上午變動」。價量未重抓，基本面未重審。本輪分批 0。條件式研究，不是交易指令，不承諾報酬。",
        "本頁 2026-11-24 上午更新：56 檔價量已換成 Massive 美東 2026-11-23（週一）拆股調整日線，API status DELAYED，可能修正；<strong>不是</strong>官方收盤，<strong>也不是</strong>含息總報酬。判斷依當時已審規則重算（量比 b≥1.0；已公告線與重算前 20 日低取較嚴者）；基本面否決與價值框架<strong>未</strong>重審。較 11/21 判斷有變的卡片標「較11/21變動」。本輪分批 0。盤後價取自 CNBC Quote Cache（延遲／非官方，時間已換算台北），不用於進場判定。條件式研究，不是交易指令，不承諾報酬。",
        "本頁 2026-11-21 更新：56 檔判斷已全部重審（投資 CEO 已核）。價量為 Massive 拆股調整日線，美東 2026-11-20（週五）bar，API status DELAYED，可能修正；<strong>不是</strong>官方收盤，<strong>也不是</strong>含息總報酬。量比一律採「當日量÷不含當日前 20 日均量」。卡上已公告的觸發線與重算前 20 日低取較嚴者。27 檔較 11/17 判斷有變，卡片標「較11/17變動」，原因寫在「詳細」。本輪分批 0。條件式研究，不是交易指令，不承諾報酬。",
        f"圖表、月線（SMA20）與季線（SMA60）：Massive Stocks Basic 拆股調整日彙總（adjusted=true，API status DELAYED），<strong>不是</strong>官方 regular-session close，<strong>也不是</strong>含息總報酬；成交量調整算法未獨立核對。最新完整交易日：{daily_s}。本輪日線由已審的分組日線檔合併寫入各標的快取（10/21–11/17 為 OK，11/18–11/19 為 OK，11/20 為 DELAYED），未對 56 檔逐一重打即時 API；各檔最後收盤已對過已審 px.close。",
        "本輪卡片上的最新盤後價改用 Massive Stocks Basic 的 open-close afterHours（adjusted=true，美東 2026-11-20），屬<strong>延遲／非官方</strong>報價，沒有鐘點，不是交易所官方收盤，也不用於進場判定。當日日線 API status DELAYED，數值可能修正。若 Massive 日線尚未包含最新完整交易日，常規收盤仍可能改列既有 CNBC Quote Cache（延遲／非官方）；本輪 56 檔日線均已含 11/20，常規收盤改用 Massive。",
        "卡片上的本益比與未來本益比：個股多數仍取自先前 CNBC Quote Cache 的 pe（落後／TTM）與 fpe（預估），以及對應的 eps／feps，屬延遲／非官方，不是公司指引或已審估值。本益比與未來本益比本輪已隨 CNBC Quote Cache 一併更新（2026-11-23 報價，延遲／非官方），仍不是公司指引或已審估值。本益比為負或 TTM／預估 EPS 為負時標「虧損」，沒有數字時標「N/A」，未發明或推算。已審估值仍只寫在「詳細」，口徑可能與卡片上的 CNBC 本益比／未來本益比不同。SOXX 的本益比取自 iShares 官網產品頁 Portfolio Characteristics 的 P/E Ratio（持股加權；最新收盤價÷最近一會計年度 EPS，負值排除），引用 11/19 存檔頁面，截至 2026-11-17，數值 35.27；官網未提供未來本益比，故未來本益比標 N/A。進場判斷不會因價格或本益比顯示自動改寫。",
        "價值股分類的本益比、FCF yield、殖利率、淨負債／EBITDA、五年 FCF 與毛利率（GD、CMCSA 改列營業利益率）全部引用已審稿 value-stocks-20261114.md、value-stocks-ko-cost-20261114.md 與對應 JSON（投資 CEO 已核，2026-11-14）。不是共識 forward PE，也不是 Yahoo 非官方彙整。",
        "AI 借貸五檔的估值口徑、研究背景與風險仍引用已審稿 ai-lending-20261114.md 與 ai-lending-20261114.json（投資 CEO 已核，2026-11-14）。2026-11-21 重審後：HAPN 由分批改觀望，PGY、SOFI 改不建議，UPST、AFRM 維持不建議；價量已更新至美東 11/20。看板依目前判斷排序，不是稿中的研究優先順序，也不代表交易先後。OPFI、FICO 落選（理由見該稿）。不是共識 forward PE。HAPN 線圖僅自 2026-06-22 更名起的日線，未與 LC 歷史拼接。",
        "AI 資安七檔的判斷、估值口徑、升降級條件、風險與缺口全部引用已審稿 ai-security-20261114.md 與 ai-security-20261114.json（投資 CEO 已核，2026-11-14；主責跨產業研究員，行情為數據專員）。看板依目前判斷排序：ZS、CRWD、OKTA、NET、PANW、S、FTNT，不是交易先後。預估本益比為公司 non-GAAP 全年指引中點，不是共識，與卡片上 CNBC 的本益比／未來本益比口徑不同。EV/Sales 為 TTM。市值＝SEC 封面股數×11/13 收盤。量比採 a 版（分母含當日）。11/14 稿的行情截至美東 11/13，量比當時採 a 版（分母含當日）。2026-11-21 重審維持六檔觀望、FTNT 不建議；價量已更新至美東 11/20，量比改採 b 版（分母不含當日）。FTNT 當時由觀望改為不建議，是因為「SMA20＜SMA50 且收盤＜SMA200」的價格規則，不是基本面否決。財報日：PANW 11/18、CRWD／OKTA 12/1、ZS 12/2、S 12/3（均為公司已公告、美東盤後）；FTNT、NET 未公告，依去年同季推估 2027/2 上中旬。Massive 為拆股調整日線，非官方收盤、非總報酬。條件式研究，不是交易指令。",
        "COHR 內部人買入因素引用已審稿 cohr-insider-20261115.md 與 cohr-insider-20261115.json（投資 CEO 已核，2026-11-15）。兩筆公開市場買入來自 SEC Form 4（11/12 申報），均非 10b5-1：CEO 11/9 買 5,000 股、申報價 199.48；獨立董事會主席 11/10 買 1,000 股、申報價 222.885。近 12 個月董事與高管仍淨賣出約 3,187 萬美元。訊號為中等偏正，只當輔助加分。CEO 買價 199.48 是觀察線，不是支撐，也不構成觸發。2026-11-21 重審因放量跌破前 20 日低，由觀望改為不建議（價格規則，非基本面否決）；價量已更新至美東 11/20，Massive 拆股調整日線，不是官方收盤，也不是總報酬。",
        "MSFT、AMZN、META、ORCL 為使用者指定加入 AI 晶片。判斷、估值口徑、升降級條件與風險全部引用已審稿 hyperscalers-4-20261117.md 與 hyperscalers-4-20261117.json（投資 CEO 已核，2026-11-17；主責 AI 晶片研究員，價量為數據專員 hyperscalers-prices-20261117）。11/17 初審四檔皆為觀望，稿內相對排序（非配置）為 MSFT、AMZN、META、ORCL，不是交易先後，也不是現在買進。2026-11-21 重審後 MSFT、META、ORCL 因放量跌破前 20 日低改為不建議（價格規則，非基本面否決），AMZN 維持觀望；價量已更新至美東 11/20。已審遠期本益比為指定財年、收盤÷Yahoo 共識 EPS（MSFT／ORCL 偏非GAAP，AMZN／META 偏GAAP），不是 NTM，也不是卡片上 CNBC 的未來本益比。加入當時的價量為 Massive 美東 2026-11-16 拆股調整日線；本輪已與 56 檔一併更新至美東 2026-11-20，API status DELAYED，不是官方收盤，也不是總報酬。",
        "毛利率：AVGO、AMD、NVDA、INTC、MRVL 用已審稿 chip6-valuation-20261114 的官方新聞稿／8-K 數字；其餘能計算者（含新加入的 MSFT、AMZN、META、ORCL）用 Yahoo Finance fundamentals timeseries 的 GAAP 毛利÷營收（非正式 10-Q 原文）。RLAY 近季無產品營收；UPST、PGY、SOFI、AFRM、HAPN 為放貸／銀行模式，標為不適用。SpaceX 已有 10-Q（至 2026-09-30，送件 2026-10-22），Yahoo 數字未逐項核對原文。",
        "升降息押注機率：CME FedWatch 官網從本機被封鎖，改以 Yahoo 30-Day Federal Funds futures 依公開日數加權方法推算，屬延遲／非官方，不是 CME 官方機率。",
        "CNN 恐慌與貪婪指數：production.dataviz.cnn.io/index/fearandgreed/graphdata。油價與公債／基金利率的 52 週位置取自 FRED；VIX 儀表用已存的 Cboe 日收盤（含 11/13）。",
        "散戶資金：AAII 散戶情緒調查取自官網 https://www.aaii.com/sentiment-survey（週截至 2026-11-11）；FINRA 融資餘額取自官方 Margin Statistics 表（2026 年 10 月，Rule 4521(d)）；ICI 貨幣基金規模取自官方週報 https://www.ici.org/research/stats/mmf（週截至 2026-11-11，2026-11-12 發布）。Cboe 權益賣權／買權比取自 Daily Market Statistics（2026-11-13）。本機直接抓 FINRA／ICI 網頁曾回 403，改以同一官方網址的備用抓取取得頁面，沒有使用付費或需登入來源。未取得 Nasdaq 等散戶淨流入公開數列，故未列入。這組數字是背景描述，不是交易指令。",
        f"恐慌指數線圖：{macro.get('vix',{}).get('source') or '資料暫缺'}。",
        f"利率點陣圖與目標區間：{macro.get('fed',{}).get('source') or '資料暫缺'}。",
        f"油價：{macro.get('oil',{}).get('source') or '資料暫缺'}。",
        f"廣義美元指數（不是 ICE DXY）：{(macro.get('dollar') or {}).get('source') or '資料暫缺'}。",
        f"美元指數對照那斯達克：{(macro.get('dollarNasdaq') or {}).get('source') or '資料暫缺'}。",
        f"國債拍賣：{macro.get('auctions',{}).get('source') or '資料暫缺'}。",
        "AI 應用 13 檔的估值口徑、研究背景與風險仍引用已審稿 ai-apps-shop-20261117.md 與 ai-apps-shop-20261117.json（投資 CEO 已核，2026-11-17；主責跨產業研究員）。11/17 初審為觀望 11 檔、不建議 2 檔（NOW、RDDT，當時為趨勢降級規則，不是基本面否決）。2026-11-21 重審後觀望僅 APP、SPOT、DUOL，其餘 10 檔為不建議（多數為放量跌破前 20 日低或趨勢降級，非基本面否決）；價量已更新至美東 11/20。看板依目前判斷排序，不是交易先後，也不是現在買進。已審遠期本益比僅 CRM、HUBS、VEEV、EBAY 有公司 EPS 指引，其餘標「不適用」（公司未給指引，無免費共識），都不是卡片上 CNBC 的未來本益比；已審 trailing 為收盤÷最近四季 GAAP 稀釋 EPS（虧損則不適用）。加入當時的價量為 Massive 美東 2026-11-16 拆股調整日線；本輪已與 56 檔一併更新至美東 2026-11-20，API status DELAYED，不是官方收盤，也不是總報酬。NOW 已核 2025-12-17 的 5:1 拆股。",
        "研究報告頁（左欄「研究報告」）：已審正文的網頁版，路徑 /reports/。目前有 AI 時代產業金流轉移（2026-11-23）、Agent 消費端口的受益者（2026-11-23）、SpaceX／Tesla 現金流與 Terafab（2026-11-17）、AI 應用 SHOP 與初選 12 檔（2026-11-17）、四大雲 MSFT／AMZN／META／ORCL（2026-11-17）、期中選舉後一年報酬（2026-11-15）、期中選後進場時點（2026-11-16）。僅供本人自用，不是交易指令。本站不公開原始指數數列、代碼表 json 或內部計算檔。",
        "ANT（Anthropic, PBC）為使用者指定加入 AI 晶片，卡片註明非晶片公司（模型公司）。身分與 IPO 事實引用已審稿 anthropic-card-20261119.json、ant-identity-20261119.md（投資 CEO 已核，2026-11-19；主責跨產業研究員），2026-11-21 重審維持「上市未滿20交易日，不判定」，不做分批／觀望／不建議。僅 2 根日線（11/19 收 97.17、11/20 收 88.91）。IPO 定價 83 美元（公司 11/18 公告）。價格為 Massive 拆股調整日線，DELAYED，不是官方收盤，也不是總報酬。本輪盤後價改用 Massive open-close afterHours。未自 S-1 擷取毛利率；市值為已審估數。",
        "SPCX 的現金流、合併現況、Terafab 與升降級條件引用已審稿 spacex-tsla-cashflow-20261117.md 與 spacex-tsla-cashflow-20261117.json（投資 CEO 已核，2026-11-17；主責跨產業研究員）。2026-11-21 重審維持觀望，不是分批或不建議，也不是現在買進。合併尚未成案；公告線 120.39 未觸發。價量與線圖已更新至 Massive 美東 2026-11-20 拆股調整日線，API status DELAYED，不是官方收盤，也不是總報酬。TSLA 僅研究性質，未加入看板。",
        "SPCX 是 Space Exploration Technologies Corp. Class A（SpaceX），不是已更名為 SPCK 的舊 SPAC ETF，歷史不可接上。Massive 同一代碼下 344 根上市前異常 bar 已排除、沒有拼接。本頁約每 5 分鐘重新整理一次（meta refresh），方便手機瀏覽器讀到更新後的內容。",
    ]
    return items


def maybe_wait_for_eod(args):
    now_ny = dt.datetime.now(NY)
    expected = expected_massive_eod(now_ny)
    cached = latest_cached_daily_date()
    completed = last_completed_session(now_ny)
    print(f"NY now={now_ny.isoformat()} expected_eod={expected} completed={completed} cached={cached}")
    if not args.wait_eod and not args.force:
        return expected
    # Wait until shortly after NY midnight so Basic can publish the session that already closed today.
    need = completed
    if args.wait_eod and (not cached or cached < need):
        target_ny = dt.datetime.combine(now_ny.date() + dt.timedelta(days=1), dt.time(0, 3), tzinfo=NY)
        if now_ny < target_ny:
            sec = (target_ny - now_ny).total_seconds()
            if 0 < sec <= 2 * 3600:
                print(f"waiting {sec:.0f}s until {target_ny.astimezone(TPE).isoformat()} for Massive EOD")
                time.sleep(sec)
            elif sec > 2 * 3600:
                print(f"not sleeping {sec:.0f}s; run closer to NY midnight")
    return expected_massive_eod()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--wait-eod", action="store_true")
    ap.add_argument("--no-publish", action="store_true", help="do not copy/commit/push to GitHub Pages")
    args = ap.parse_args()
    PROC.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    if not args.offline:
        expected = maybe_wait_for_eod(args)
        # retry dailies up to 3 times if still lagging after wait
        for attempt in range(3):
            fetch_massive_daily(force=args.force and attempt == 0, expected=expected)
            cached = latest_cached_daily_date()
            lagging = tickers_behind(expected)
            if not lagging:
                break
            if args.offline:
                break
            if attempt < 2:
                # If some tickers already have the bar, remaining misses are usually network; retry sooner.
                delay = 600 if len(lagging) == len(TICKERS) else 20
                print(f"Massive still missing {expected} for {', '.join(lagging)}; wait {delay}s then retry")
                time.sleep(delay)
                expected = expected_massive_eod()
        try:
            fetch_cnbc_quotes()
        except Exception as e:
            print("cnbc fetch failed", type(e).__name__, e)
        try:
            fetch_macro()
        except Exception as e:
            print("macro fetch failed", type(e).__name__, e)
        try:
            fetch_extra()
        except Exception as e:
            print("extra fetch failed", type(e).__name__, e)
    else:
        expected = expected_massive_eod()

    research = json.loads((DATA / "research.json").read_text())
    cnbc_map = load_cnbc()
    stocks = [process_stock(r, cnbc_map) for r in research]
    macro = process_macro()
    try:
        extra = process_extra()
    except Exception as e:
        print("extra process failed", type(e).__name__, e)
        extra = {"margins": {}, "fedwatch": {"ok": False, "reason": str(e)}, "cnn": {"ok": False}, "gauges": {}}
    margins = extra.get("margins") or {}
    for s in stocks:
        if s["ticker"] in margins:
            s["margin"] = margins[s["ticker"]]
        vm = s.get("valueMetrics") or {}
        if vm.get("margin"):
            s["margin"] = vm["margin"]
    macro["cnn"] = extra.get("cnn") or {"ok": False}
    macro["fedwatch"] = extra.get("fedwatch") or {"ok": False}
    macro["gauges"] = extra.get("gauges") or {}
    macro["retail"] = extra.get("retail") or {"ok": False}
    gv = (macro["gauges"].get("vix") or {})
    if gv.get("ok") and gv.get("latest") is not None:
        cur = macro.get("vix") or {}
        if not cur.get("latestDate") or gv["latestDate"] >= cur.get("latestDate", ""):
            cur["latest"] = gv["latest"]
            cur["latestDate"] = gv["latestDate"]
            cur["sourceShort"] = gv.get("sourceShort") or cur.get("sourceShort")
            if gv.get("source"):
                cur["source"] = (cur.get("source") or "") + " " + gv["source"]
            macro["vix"] = cur
    cached = latest_cached_daily_date()
    completed = last_completed_session()
    lagging = tickers_behind(completed)
    daily_lag_note = None
    if lagging and len(lagging) < len(TICKERS):
        daily_lag_note = (
            f"以下標的的圖表、月線與季線目前使用 Massive 較早的完整日線（尚未含美東 {completed}）："
            f"{', '.join(lagging)}。"
            f"其餘標的已使用 {completed} 日線。"
            f"未到齊標的的常規收盤改列 CNBC 延遲／非官方報價。"
        )
    elif lagging and cached and cached < completed:
        daily_lag_note = (
            f"股票卡片價量與判斷仍為 Massive 美東 {cached}（拆股調整日線，DELAYED，不是官方收盤，也不是總報酬）。"
            f"美東 {completed} 交易日已結束，本輪未改用該日、也未改判斷。"
        )
    bar_shown = cached or completed or "—"
    meta = {
        "built_at_Taipei": now_pair()[0],
        "expected_eod": expected,
        "completed_session": completed,
        "cached_eod": cached,
        "daily_lag_note": daily_lag_note,
        "priceStamp": (
            f"價量：美東 {bar_shown}（Massive 拆股調整日線，DELAYED，不是官方收盤，也不是總報酬）"
            f"｜判斷依統一趨勢規則重算 2026-11-24 台北（收盤低於 SMA50 且 SMA20 低於 SMA50；基本面未重審；bar 仍為美東 11/23）"
            f"｜月線／季線壓力依 11/23 收盤顯示，判斷未改"
            f"｜頁面產生 {now_pair()[0][:16].replace('T', ' ')} 台北"
        ),
        "reviewAsOf": "2026-11-24 台北（價量規則重算＋趨勢規則統一；基本面未重審；bar 仍為美東 11/23）",
        "priceBar": f"美東 {bar_shown}" if bar_shown != "—" else "美東 2026-11-23",
    }
    meta["footer"] = build_footer(stocks, macro, meta)
    dest = render(stocks, macro, meta)
    from reports import build_reports
    report_paths = build_reports(ROOT / "reports")
    if not args.no_publish:
        publish_gh_site(dest, reports=report_paths)
    # write a compact after-hours report for the parent agent
    report = []
    for s in stocks:
        q = cnbc_map.get(s["ticker"]) or {}
        report.append({
            "ticker": s["ticker"],
            "ah_price": s.get("ahPrice"),
            "ah_time_taipei": s.get("ahTimeTaipei") or q.get("ah_time_taipei"),
            "ah_time_et": q.get("ah_time_et") or q.get("ah_time"),
            "reg_close": s.get("regClose"),
            "reg_change_pct": s.get("regChangePct"),
            "reg_source": s.get("regSource"),
            "reg_label": s.get("regLabel"),
            "massive_daily": s.get("date"),
            "massive_close": s.get("price"),
        })
    (PROC / "prices-report.json").write_text(json.dumps({
        "built_at_Taipei": meta["built_at_Taipei"],
        "ah_source": "Massive open-close afterHours (reviewed 2026-11-20), delayed unofficial; not used for calls",
        "massive_extended": "this refresh used reviewed open-close afterHours; snapshot/last trade still unused",
        "expected_eod": expected,
        "cached_eod": cached,
        "rows": report,
    }, ensure_ascii=False, indent=2))
    print("done", meta["built_at_Taipei"])


def publish_gh_site(src: Path, *, push: bool = True, reports=None):
    """Copy index.html and rendered report pages into the GitHub Pages repo."""
    site = Path("/workspace/gh-site")
    if not (site / ".git").exists():
        print("publish skipped: /workspace/gh-site is not a git repo")
        return None
    dest = site / "index.html"
    dest.write_text(src.read_text())
    # Only the rendered report HTML — never copy raw index CSVs/JSON or memo data files.
    report_dir = site / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = list(reports or [])
    if not paths:
        local = Path(__file__).resolve().parent / "reports"
        paths = sorted(local.glob("*.html"))
    want = set()
    for p in paths:
        p = Path(p)
        if p.suffix.lower() != ".html":
            continue
        want.add(p.name)
        (report_dir / p.name).write_text(p.read_text())
    for extra in report_dir.glob("*"):
        if extra.name not in want:
            extra.unlink()
    def git(*args, check=True):
        return subprocess.run(["git", "-C", str(site), *args], check=check, capture_output=True, text=True)
    git("add", "index.html", "reports")
    st = git("status", "--porcelain")
    if not st.stdout.strip():
        print("publish: nothing to commit")
        return None
    when = now_pair()[0][:16]
    git("commit", "-m", f"Update watchlist dashboard ({when} Taipei)")
    sha = git("rev-parse", "HEAD").stdout.strip()
    if push:
        pushed = git("push", "origin", "HEAD", check=False)
        if pushed.returncode != 0:
            subprocess.run(["gh", "auth", "setup-git"], check=False, capture_output=True, text=True)
            pushed = git("push", "origin", "HEAD", check=False)
        if pushed.returncode != 0:
            print("publish push failed:", (pushed.stderr or pushed.stdout or "").strip())
            print("committed locally", sha)
            return sha
        if pushed.stderr:
            print(pushed.stderr.strip())
        print("published", sha)
    else:
        print("committed", sha, "(push skipped)")
    return sha


if __name__ == "__main__":
    main()
