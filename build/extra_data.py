#!/usr/bin/env python3
"""Extra dashboard data: margins, FedWatch-style odds, CNN Fear & Greed, macro gauges."""
from __future__ import annotations

import csv, json, math, re, time, datetime as dt, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
PROC = DATA / "processed"
TPE = ZoneInfo("Asia/Taipei")
NY = ZoneInfo("America/New_York")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
UA_CNN = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15")

TICKERS = ["AAPL","ACN","AFRM","AMD","AMZN","ANT","APP","AVGO","CL","CMCSA","COHR","COST","CRM","CRWD","DUOL","EBAY","FTNT","GD","GOOG","HAPN","HUBS","IBM","INTC","ITW","KO",
           "LITE","LLY","LMT","META","MRVL","MRNA","MSFT","NET","NOW","NVDA","OKTA","ORCL","PANW","PG","PGY","PINS","PLTR","RDDT","RLAY","S","SHOP","SNOW","SOFI","SOXX","SPCX","SPOT","TMDX","TSM","UPST","VEEV","ZS"]

# Official GAAP / non-GAAP from the reviewed chip6 memo dated 2026-11-14.
# Do not invent; these copy the reviewed table and citations.
CHIP6_GM = {
    "AVGO": {
        "q_pct": 69.1, "q_ng": 75.0, "ttm_pct": 68.8, "ttm_ng": 76.5,
        "q_label": "Q3 FY26（期間結束 2026-08-02）",
        "ttm_label": "近四季 TTM（Q4 FY25–Q3 FY26）",
        "source": "已審稿 chip6-valuation-20261114（2026-11-14）。取自官方新聞稿／8-K Exhibit 99.1 毛利額÷營收【估】。https://investors.broadcom.com/news-releases/news-release-details/broadcom-inc-announces-third-quarter-fiscal-year-2026-financial ；SEC https://www.sec.gov/Archives/edgar/data/1730168/000173016826000076/avgo-08022026x8kxex99.htm",
    },
    "AMD": {
        "q_pct": 54.0, "q_ng": 56.0, "ttm_pct": 53.7, "ttm_ng": 56.1,
        "q_label": "2026Q3",
        "ttm_label": "近四季 TTM",
        "source": "已審稿 chip6-valuation-20261114（2026-11-14）。單季為官方新聞稿整數百分比；TTM 為四季官方毛利÷營收【估】。",
    },
    "NVDA": {
        "q_pct": 75.0, "q_ng": 75.0, "ttm_pct": 74.7, "ttm_ng": 74.8,
        "q_label": "Q2 FY27",
        "ttm_label": "近四季 TTM",
        "source": "已審稿 chip6-valuation-20261114（2026-11-14）。官方 GAAP／non-GAAP 百分比。注意：自 FY2027 第 1 季起 non-GAAP 不再剔除股票薪酬，近四季 non-GAAP 口徑不完全一致。",
    },
    "INTC": {
        "q_pct": 43.0, "q_ng": 44.1, "ttm_pct": 39.9, "ttm_ng": 41.4,
        "q_label": "2026Q3",
        "ttm_label": "近四季 TTM",
        "source": "已審稿 chip6-valuation-20261114（2026-11-14）。單季為官方百分比；TTM 為四季官方毛利÷營收【估】。",
    },
    "MRVL": {
        "q_pct": 53.1, "q_ng": 58.9, "ttm_pct": 52.2, "ttm_ng": 59.1,
        "q_label": "Q2 FY27（期間結束 2026-08-01；完整 Q3 季報尚未公布）",
        "ttm_label": "已公布最近四季 TTM",
        "source": "已審稿 chip6-valuation-20261114（2026-11-14）。官方 GAAP／non-GAAP 百分比。",
    },
}

# Upcoming FOMC from https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
# (calendar last update 2026-11-12). Decision is the second day; new target
# typically effective the following calendar day.
FOMC_MEETINGS = [
    {"start": "2026-12-08", "end": "2026-12-09", "effective": "2026-12-10", "sep": True},
    {"start": "2027-01-26", "end": "2027-01-27", "effective": "2027-01-28", "sep": False},
    {"start": "2027-03-16", "end": "2027-03-17", "effective": "2027-03-18", "sep": True},
]

# Yahoo 30-day Fed Funds futures month codes
ZQ_CONTRACTS = {
    "2026-11": "ZQX26.CBT",
    "2026-12": "ZQZ26.CBT",
    "2027-01": "ZQF27.CBT",
    "2027-02": "ZQG27.CBT",
    "2027-03": "ZQH27.CBT",
    "2027-04": "ZQJ27.CBT",
    "2027-05": "ZQK27.CBT",
    "2027-06": "ZQM27.CBT",
}


def now_tpe() -> str:
    return dt.datetime.now(TPE).isoformat()


def http_get(url: str, dest: Path, headers: dict | None = None, timeout: int = 30) -> tuple[bool, bytes, str | None]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = {"User-Agent": UA, "Accept": "application/json,text/csv,text/html;q=0.9,*/*;q=0.8",
         "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            dest.write_bytes(body)
            return True, body, None
    except Exception as e:
        err = f"{type(e).__name__}"
        if getattr(e, "code", None):
            err = f"HTTP_{e.code}"
        try:
            b = e.read() if hasattr(e, "read") else b""
            if b:
                dest.with_suffix(dest.suffix + ".err").write_bytes(b[:8000])
        except Exception:
            pass
        return False, b"", err


def fetch_cnn_fng() -> dict:
    dest = RAW / "cnn" / "graphdata.json"
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    ok, body, err = http_get(url, dest, headers={
        "User-Agent": UA_CNN,
        "Origin": "https://www.cnn.com",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
    })
    return {"ok": ok, "error": err, "bytes": len(body), "retrieved_at_Taipei": now_tpe()}


def fetch_margins() -> dict:
    dest = RAW / "yahoo-financials"
    dest.mkdir(parents=True, exist_ok=True)
    types = ",".join([
        "quarterlyGrossProfit", "trailingGrossProfit",
        "quarterlyTotalRevenue", "trailingTotalRevenue",
        "quarterlyCostOfRevenue",
    ])
    p1, p2 = 1546300800, 1800000000
    log = {"retrieved_at_Taipei": now_tpe(), "tickers": {}}
    for i, tk in enumerate(TICKERS):
        if tk == "SOXX":
            log["tickers"][tk] = {"ok": True, "error": None, "bytes": 0, "skipped": "ETF, no company gross margin"}
            continue
        if tk == "ANT":
            log["tickers"][tk] = {"ok": True, "error": None, "bytes": 0, "skipped": "IPO; gross margin not taken from S-1 this round"}
            continue
        if i:
            time.sleep(0.35)
        q = urllib.parse.urlencode({"type": types, "period1": p1, "period2": p2})
        url = f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{tk}?{q}"
        ok, body, err = http_get(url, dest / f"{tk}.json",
                                 headers={"Referer": f"https://finance.yahoo.com/quote/{tk}/financials/"})
        log["tickers"][tk] = {"ok": ok, "error": err, "bytes": len(body)}
    (dest / "_fetch-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))
    return log


def fetch_zq_futures() -> dict:
    dest = RAW / "fedwatch"
    dest.mkdir(parents=True, exist_ok=True)
    log = {"retrieved_at_Taipei": now_tpe(), "contracts": {}}
    for month, sym in ZQ_CONTRACTS.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=10d"
        ok, body, err = http_get(url, dest / f"yahoo-{sym}.json",
                                 headers={"Referer": "https://finance.yahoo.com/"})
        log["contracts"][month] = {"symbol": sym, "ok": ok, "error": err, "bytes": len(body)}
        time.sleep(0.2)
    (dest / "_zq-fetch-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))
    return log


def fetch_fred_series(series_id: str) -> dict:
    dest = RAW / "fred" / f"{series_id}.csv"
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    ok, body, err = http_get(url, dest, headers={"User-Agent": UA_CNN})
    return {"ok": ok, "error": err, "bytes": len(body), "id": series_id}


def fetch_extra() -> dict:
    """Fetch all extra sources used by the new gauges and margin fields."""
    out = {"retrieved_at_Taipei": now_tpe()}
    out["cnn"] = fetch_cnn_fng()
    out["margins"] = fetch_margins()
    out["zq"] = fetch_zq_futures()
    out["fred"] = {}
    for sid in ("DGS10", "DFF", "VIXCLS", "DCOILWTICO", "DCOILBRENTEU", "DFEDTARU", "DFEDTARL", "RMFSL"):
        out["fred"][sid] = fetch_fred_series(sid)
    out["retail"] = fetch_retail()
    (PROC / "extra-fetch-log.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("extra fetch", {k: (v if not isinstance(v, dict) else list(v)[:8]) for k, v in out.items() if k != "retrieved_at_Taipei"})
    return out


# ---------- processors ----------

def _ts_items(data: dict, key: str) -> list[dict]:
    rows = []
    for block in (data.get("timeseries") or {}).get("result") or []:
        typ = (block.get("meta") or {}).get("type") or []
        typ = typ[0] if typ else None
        if typ != key:
            continue
        for row in block.get(key) or []:
            if not row:
                continue
            val = (row.get("reportedValue") or {}).get("raw")
            rows.append({"asOf": row.get("asOfDate"), "period": row.get("periodType"),
                         "ccy": row.get("currencyCode"), "val": val})
    rows.sort(key=lambda r: r["asOf"] or "")
    return rows


def process_margins() -> dict[str, dict]:
    dest = RAW / "yahoo-financials"
    retrieved = now_tpe()
    log_p = dest / "_fetch-log.json"
    if log_p.exists():
        try:
            retrieved = json.loads(log_p.read_text()).get("retrieved_at_Taipei") or retrieved
        except Exception:
            pass
    out = {}
    for tk in TICKERS:
        if tk == "SOXX":
            out[tk] = {
                "ok": False, "kind": "na",
                "reason": "不適用（ETF）",
                "detail": "SOXX 是追蹤半導體指數的 ETF，沒有單一公司毛利率，本頁不列。",
                "source": "iShares Semiconductor ETF（SOXX）產品說明。",
            }
            continue
        if tk == "ANT":
            out[tk] = {
                "ok": False, "kind": "na",
                "reason": "尚未自 S-1 擷取毛利率",
                "detail": "已審稿未於本輪自 S-1 擷取毛利率（缺口）。",
                "source": "ant-identity-20261119.md／anthropic-card-20261119.json（投資 CEO 已核，2026-11-19）。",
            }
            continue
        if tk in CHIP6_GM:
            c = CHIP6_GM[tk]
            out[tk] = {
                "ok": True,
                "kind": "official",
                "q_pct": c["q_pct"],
                "q_ng": c.get("q_ng"),
                "q_label": c["q_label"],
                "ttm_pct": c["ttm_pct"],
                "ttm_ng": c.get("ttm_ng"),
                "ttm_label": c["ttm_label"],
                "source": c["source"],
                "note": None,
            }
            continue
        path = dest / f"{tk}.json"
        if not path.exists():
            out[tk] = {"ok": False, "kind": "missing", "reason": "尚未取到財報彙整", "source": ""}
            continue
        data = json.loads(path.read_text())
        qgp, qrev = _ts_items(data, "quarterlyGrossProfit"), _ts_items(data, "quarterlyTotalRevenue")
        tgp, trev = _ts_items(data, "trailingGrossProfit"), _ts_items(data, "trailingTotalRevenue")
        gp = {r["asOf"]: r for r in qgp if r.get("val") is not None}
        rv = {r["asOf"]: r for r in qrev if r.get("val") is not None}
        dates = sorted(set(gp) & set(rv))
        # special cases
        if tk == "RLAY":
            last_rev = qrev[-1] if qrev else None
            ttm_rev = trev[-1] if trev else None
            out[tk] = {
                "ok": False, "kind": "na",
                "reason": "不適用／近季無產品營收",
                "detail": (
                    f"Yahoo Finance fundamentals 顯示 "
                    f"{(last_rev or {}).get('asOf') or '最近一季'} 單季營收 "
                    f"{(last_rev or {}).get('val')} 美元"
                    + (f"；近四季營收約 {ttm_rev['val']:,.0f} 美元（至 {ttm_rev['asOf']}）" if ttm_rev and ttm_rev.get('val') is not None else "")
                    + "。未提供 GrossProfit。臨床階段公司毛利率不具一般可比性。"
                ),
                "source": f"Yahoo Finance fundamentals timeseries，取數台北 {retrieved[:16]}。非正式 10-Q 原文。",
            }
            continue
        if tk in {"UPST", "PGY", "SOFI", "AFRM", "HAPN"}:
            out[tk] = {
                "ok": False, "kind": "na",
                "reason": "不適用（放貸／銀行模式）",
                "detail": "放貸或銀行類公司不以傳統毛利率衡量，本頁不以營收或淨利息充當毛利率。",
                "source": f"已審稿 ai-lending-20261114.md；取數台北 {retrieved[:16]}。",
            }
            continue
        if tk == "SPCX":
            # SpaceX is now a Nasdaq filer (CIK 0001181412) with a 10-Q for the quarter
            # ended 2026-09-30 (filed 2026-10-22, spcx-20260930.htm). Yahoo figures
            # are an unofficial aggregation of those reported amounts; not line-checked
            # against the 10-Q in this build (SEC companyfacts blocked from this host).
            pass
        lastq = dates[-1] if dates else None
        if not lastq or not rv[lastq]["val"]:
            out[tk] = {
                "ok": False, "kind": "missing",
                "reason": "Yahoo 未提供可配對的單季毛利與營收",
                "source": f"Yahoo Finance fundamentals timeseries，取數台北 {retrieved[:16]}。",
            }
            continue
        q_m = 100.0 * gp[lastq]["val"] / rv[lastq]["val"]
        ttm = ttm_date = None
        tgp_m = {r["asOf"]: r for r in tgp if r.get("val") is not None}
        trv_m = {r["asOf"]: r for r in trev if r.get("val") is not None}
        tdates = sorted(set(tgp_m) & set(trv_m))
        if tdates and trv_m[tdates[-1]]["val"]:
            ttm = 100.0 * tgp_m[tdates[-1]]["val"] / trv_m[tdates[-1]]["val"]
            ttm_date = tdates[-1]
        elif len(dates) >= 4:
            sgp = sum(gp[x]["val"] for x in dates[-4:])
            srv = sum(rv[x]["val"] for x in dates[-4:])
            if srv:
                ttm = 100.0 * sgp / srv
                ttm_date = f"{dates[-4]}～{dates[-1]}"
        ccy = rv[lastq].get("ccy") or "USD"
        note = None
        if tk == "MRNA":
            note = "單季毛利波動大（例如 2026Q1 毛利為負），近四季 TTM 較能代表近一年。"
        if tk == "TSM":
            note = "數字為新台幣、公司季報口徑（Yahoo 彙整，通常對應 TIFRS／IFRS），不是美元。"
        if tk == "SPCX":
            note = "SpaceX（CIK 0001181412）已於 Nasdaq 掛牌；最近 10-Q 期間結束 2026-09-30，送件 2026-10-22（spcx-20260930.htm）。下表為 Yahoo 彙整之 GAAP 毛利÷營收，本輪未逐項核對 10-Q 原文。"
        src = (
            f"Yahoo Finance fundamentals timeseries 的 GAAP GrossProfit ÷ TotalRevenue"
            f"（非官方重算，非正式 10-Q／20-F 原文）。取數台北 {retrieved[:16]}。"
        )
        if tk == "SPCX":
            src += " SEC 10-Q：https://www.sec.gov/Archives/edgar/data/1181412/000162828026066880/spcx-20260930.htm"
        out[tk] = {
            "ok": True,
            "kind": "yahoo",
            "q_pct": round(q_m, 2),
            "q_ng": None,
            "q_label": f"最近一季（至 {lastq}）",
            "q_gp": gp[lastq]["val"],
            "q_rev": rv[lastq]["val"],
            "q_ccy": ccy,
            "ttm_pct": None if ttm is None else round(ttm, 2),
            "ttm_ng": None,
            "ttm_label": f"近四季 TTM（至 {ttm_date}）" if ttm_date else "近四季 TTM",
            "source": src,
            "note": note,
        }
    return out


def _zq_quote(month: str) -> dict | None:
    sym = ZQ_CONTRACTS.get(month)
    if not sym:
        return None
    path = RAW / "fedwatch" / f"yahoo-{sym}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    res = ((data.get("chart") or {}).get("result") or [None])[0]
    if not res:
        return None
    meta = res["meta"]
    px = meta.get("regularMarketPrice")
    t = meta.get("regularMarketTime")
    close = None
    try:
        close = (res["indicators"]["quote"][0]["close"] or [None])[-1]
    except Exception:
        close = None
    t_tpe = t_et = None
    if t:
        ts = dt.datetime.fromtimestamp(int(t), tz=dt.timezone.utc)
        t_et = ts.astimezone(NY).isoformat()
        t_tpe = ts.astimezone(TPE).strftime("%Y-%m-%d %H:%M:%S")
    if px is None:
        return None
    return {
        "symbol": meta.get("symbol") or sym,
        "price": float(px),
        "close": None if close is None else float(close),
        "implied": 100.0 - float(px),
        "time_et": t_et,
        "time_taipei": t_tpe,
    }


def _adjacent_probs(implied: float, mid: float, step: float = 0.25) -> dict:
    """Place implied post-meeting mid between two 25 bp rungs; return bucket probs."""
    # rungs are mid + k*step
    k = math.floor((implied - mid) / step)
    lo = mid + k * step
    hi = lo + step
    if abs(implied - lo) < 1e-12:
        buckets = {round(lo, 4): 1.0}
    else:
        p_hi = (implied - lo) / step
        p_lo = 1.0 - p_hi
        buckets = {round(lo, 4): p_lo, round(hi, 4): p_hi}
    hold = cut = hike = 0.0
    dist = []
    for level, p in sorted(buckets.items()):
        move_bp = round((level - mid) * 10000) / 100  # in bp, mid is percent
        # level and mid are in percent (e.g. 3.875)
        move_bp = round((level - mid) * 100, 1)  # 0.25% -> 25.0 bp
        if abs(move_bp) < 1e-6:
            tag = "維持"
            hold += p
        elif move_bp < 0:
            tag = f"降息 {abs(move_bp):.0f} bp"
            cut += p
        else:
            tag = f"升息 {move_bp:.0f} bp"
            hike += p
        dist.append({
            "targetMid": level,
            "targetRange": f"{level-0.125:.2f}–{level+0.125:.2f}%",
            "prob": round(p * 100, 1),
            "moveBp": move_bp,
            "tag": tag,
        })
    return {
        "hold": round(hold * 100, 1),
        "cut": round(cut * 100, 1),
        "hike": round(hike * 100, 1),
        "impliedMid": round(implied, 3),
        "dist": dist,
    }


def process_fedwatch() -> dict:
    quotes = {m: _zq_quote(m) for m in ZQ_CONTRACTS}
    have = {m: q for m, q in quotes.items() if q}
    if "2026-11" not in have or "2026-12" not in have:
        return {
            "ok": False,
            "reason": "無法取得足夠的 30 日聯邦基金期貨報價（CME FedWatch 網站與 API 均被封鎖）。",
            "source": "曾嘗試 CME FedWatch（IP 封鎖）。備援 Yahoo Finance 30-Day Federal Funds futures 報價不足。",
        }
    # current official target from FRED
    def last_fred(sid):
        p = RAW / "fred" / f"{sid}.csv"
        if not p.exists():
            return None, None
        rows = []
        with p.open() as f:
            r = csv.reader(f)
            next(r, None)
            for date, val in r:
                if val and val not in (".", ""):
                    rows.append((date, float(val)))
        return rows[-1] if rows else (None, None)

    lo_d, lo_v = last_fred("DFEDTARL")
    hi_d, hi_v = last_fred("DFEDTARU")
    if lo_v is None or hi_v is None:
        return {"ok": False, "reason": "沒有現行聯邦基金目標區間。"}
    mid = (lo_v + hi_v) / 2.0
    # November implied (no meeting this month after Oct 28)
    r_before = have["2026-11"]["implied"]
    meetings = []
    # December 8-9, effective Dec 10
    m_dec = have["2026-12"]["implied"]
    days = 31
    d1, d2 = 9, 22
    r_dec = (m_dec * days - r_before * d1) / d2
    meetings.append({
        "name": "2026 年 12 月 8–9 日（含 SEP）",
        "end": "2026-12-09",
        "effective": "2026-12-10",
        "method": f"12 月合約隱含月均 {m_dec:.3f}%；假設 12/10 生效，前 {d1} 日用 11 月合約隱含 {r_before:.3f}%，後 {d2} 日反推會議後利率。",
        "contract": have["2026-12"],
        **_adjacent_probs(r_dec, mid),
    })
    # January 26-27, effective Jan 28 — only 4 days left in the month, so use
    # the February contract (no FOMC in February) as the post-meeting rate.
    if "2027-02" in have:
        r_jan = have["2027-02"]["implied"]
        jan_method = (
            f"1 月會議偏晚（1/28 生效後僅剩 4 個日曆日），會議月合約對「會議後利率」過度敏感，"
            f"改用無會議的 2 月合約隱含利率 {r_jan:.3f}% 作為 1 月會議後的目標中位。"
        )
    elif "2027-01" in have:
        m_jan = have["2027-01"]["implied"]
        r_jan = (m_jan * 31 - r_dec * 27) / 4
        jan_method = f"1 月合約隱含月均 {m_jan:.3f}%，以日數加權反推（後段僅 4 日，數字較不穩）。"
    else:
        r_jan = None
        jan_method = "缺少 1／2 月期貨。"
    if r_jan is not None:
        meetings.append({
            "name": "2027 年 1 月 26–27 日",
            "end": "2027-01-27",
            "effective": "2027-01-28",
            "method": jan_method,
            "contract": have.get("2027-02") or have.get("2027-01"),
            **_adjacent_probs(r_jan, mid),
        })
    # March 16-17, effective Mar 18
    if "2027-03" in have and r_jan is not None:
        m_mar = have["2027-03"]["implied"]
        d1, d2, days = 17, 14, 31
        r_mar = (m_mar * days - r_jan * d1) / d2
        meetings.append({
            "name": "2027 年 3 月 16–17 日（含 SEP）",
            "end": "2027-03-17",
            "effective": "2027-03-18",
            "method": f"3 月合約隱含月均 {m_mar:.3f}%；假設 3/18 生效，前 {d1} 日用 1 月會議後利率 {r_jan:.3f}%，後 {d2} 日反推。",
            "contract": have["2027-03"],
            **_adjacent_probs(r_mar, mid),
        })
    times = [q["time_taipei"] for q in have.values() if q.get("time_taipei")]
    t0 = max(times) if times else None
    return {
        "ok": True,
        "targetRange": f"{lo_v:.2f}%–{hi_v:.2f}%",
        "targetMid": mid,
        "targetAsOf": lo_d,
        "meetings": meetings,
        "quotes": {m: q for m, q in have.items()},
        "timestamp_taipei": t0,
        "source": (
            "CME FedWatch 官網與官方 API 從本機 IP 回 403（疑似封鎖爬蟲），故未使用 CME 公布的機率數字。"
            "改以 Yahoo Finance 30-Day Federal Funds futures（ZQ）延遲報價，依 CME FedWatch 公開方法："
            "隱含月均利率＝100−期貨價；會議生效日前後以日數加權，求出會議後隱含目標中位，再落在兩個相鄰 25 基點檔。"
            "1 月會議因月底過晚，改用無會議的 2 月合約代表會議後利率（方法已在該列註明）。"
            f"報價時間台北 {t0}（美東 2026-11-13 約 16:59）。屬延遲／非官方，不是 CME 官方結算或付費 FedWatch。"
            "會議日期取自聯準會年曆 https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm （頁面最後更新 2026-11-12）。"
            f"現行目標區間取自 FRED DFEDTARL／DFEDTARU，截至 {lo_d}。"
        ),
        "blurb": "以下是期貨隱含的「該次會議結束後」目標區間機率，是累計結果，不是單次會議的孤立變動。不是預測，更不是交易建議。",
    }


def process_cnn() -> dict:
    path = RAW / "cnn" / "graphdata.json"
    if not path.exists():
        return {"ok": False, "reason": "尚未取到 CNN Fear & Greed 資料。"}
    data = json.loads(path.read_text())
    fg = data.get("fear_and_greed") or {}
    score = fg.get("score")
    ts = fg.get("timestamp")
    tpe = et = None
    if ts:
        t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        et = t.astimezone(NY)
        tpe = t.astimezone(TPE)
    # CNN site typically displays a rounded integer; keep exact score too.
    rating = fg.get("rating") or ""
    rating_zh = {
        "extreme fear": "極度恐慌",
        "fear": "恐慌",
        "neutral": "中性",
        "greed": "貪婪",
        "extreme greed": "極度貪婪",
    }.get(rating.lower(), rating)
    return {
        "ok": score is not None,
        "score": None if score is None else round(float(score), 1),
        "score_int": None if score is None else int(round(float(score))),
        "rating": rating,
        "rating_zh": rating_zh,
        "previous_close": None if fg.get("previous_close") is None else round(float(fg["previous_close"]), 1),
        "previous_1_week": None if fg.get("previous_1_week") is None else round(float(fg["previous_1_week"]), 1),
        "previous_1_month": None if fg.get("previous_1_month") is None else round(float(fg["previous_1_month"]), 1),
        "previous_1_year": None if fg.get("previous_1_year") is None else round(float(fg["previous_1_year"]), 1),
        "time_et": et.strftime("%Y-%m-%d %H:%M:%S") if et else None,
        "time_taipei": tpe.strftime("%Y-%m-%d %H:%M:%S") if tpe else None,
        "last_updated_et": (
            (lambda d: f"{d.strftime('%b')} {d.day} at {((d.hour%12) or 12)}:{d.strftime('%M:%S')} {'AM' if d.hour<12 else 'PM'} ET")(et)
            if et else None
        ),
        "zones": [
            {"id": "ef", "label": "極度恐慌", "lo": 0, "hi": 25},
            {"id": "f", "label": "恐慌", "lo": 25, "hi": 45},
            {"id": "n", "label": "中性", "lo": 45, "hi": 55},
            {"id": "g", "label": "貪婪", "lo": 55, "hi": 75},
            {"id": "eg", "label": "極度貪婪", "lo": 75, "hi": 100},
        ],
        "source": (
            "CNN Fear & Greed Index，production.dataviz.cnn.io/index/fearandgreed/graphdata。"
            + (f"更新時間美東 {et.strftime('%Y-%m-%d %H:%M:%S')}（台北 {tpe.strftime('%Y-%m-%d %H:%M:%S')}）。" if et else "")
            + "分數為 API 原始值（本輪 38.6，CNN 頁面通常四捨五入顯示為 39）。分區沿用 CNN 常用切點：0–25 極度恐慌、25–45 恐慌、45–55 中性、55–75 貪婪、75–100 極度貪婪。"
        ),
    }


def _read_fred(path: Path, date_fmt=None) -> list[tuple[dt.date, float]]:
    if not path.exists():
        return []
    rows = []
    text = path.read_text()
    # FRED: DATE,SERIES  or Cboe: DATE,OPEN,HIGH,LOW,CLOSE
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    close_idx = 1
    date_idx = 0
    up = [h.upper() for h in header]
    if "CLOSE" in up:
        close_idx = up.index("CLOSE")
    if "DATE" in up:
        date_idx = up.index("DATE")
    for ln in lines[1:]:
        parts = [p.strip().strip('"') for p in ln.split(",")]
        if len(parts) <= max(date_idx, close_idx):
            continue
        ds, vs = parts[date_idx], parts[close_idx]
        if vs in (".", "", "null"):
            continue
        try:
            if "-" in ds:
                d = dt.date.fromisoformat(ds[:10])
            else:
                d = dt.datetime.strptime(ds, "%m/%d/%Y").date()
            rows.append((d, float(vs)))
        except ValueError:
            continue
    rows.sort()
    return rows


def _lookbacks(series: list[tuple[dt.date, float]]) -> dict | None:
    if not series:
        return None
    last_d, last_v = series[-1]

    def ago(days: int):
        target = last_d - dt.timedelta(days=days)
        prev = [r for r in series if r[0] <= target]
        return prev[-1] if prev else None

    w1, m1, y1 = ago(7), ago(30), ago(365)
    win = [r for r in series if r[0] >= last_d - dt.timedelta(days=365)]
    if not win:
        win = series
    low = min(win, key=lambda r: r[1])
    high = max(win, key=lambda r: r[1])
    span = high[1] - low[1]
    pos = None if span <= 0 else (last_v - low[1]) / span
    return {
        "latest": last_v,
        "latestDate": last_d.isoformat(),
        "low52": low[1],
        "low52Date": low[0].isoformat(),
        "high52": high[1],
        "high52Date": high[0].isoformat(),
        "pos": None if pos is None else round(pos, 4),
        "ago1w": None if not w1 else w1[1],
        "ago1wDate": None if not w1 else w1[0].isoformat(),
        "ago1m": None if not m1 else m1[1],
        "ago1mDate": None if not m1 else m1[0].isoformat(),
        "ago1y": None if not y1 else y1[1],
        "ago1yDate": None if not y1 else y1[0].isoformat(),
    }


def process_gauges() -> dict:
    # VIX: prefer Cboe file (has 11/13) when present, else FRED VIXCLS
    cboe = _read_fred(RAW / "fred" / "VIX_CBOE.csv")
    fred_vix = _read_fred(RAW / "fred" / "VIXCLS.csv")
    if cboe and (not fred_vix or cboe[-1][0] >= fred_vix[-1][0]):
        vix_series, vix_src = cboe, (
            "Cboe VIX 日收盤（本機已存檔，含 2026-11-13；本輪再向 cdn.cboe.com 更新時回 403，故沿用 12:45 台北已下載檔）。"
            "FRED VIXCLS 同期至 2026-11-12 為 18.70，與該檔 11/12 收盤相符。"
        )
        vix_short = "Cboe VIX"
    else:
        vix_series, vix_src = fred_vix, "FRED VIXCLS https://fred.stlouisfed.org/series/VIXCLS"
        vix_short = "FRED VIXCLS"
    wti = _read_fred(RAW / "fred" / "DCOILWTICO.csv")
    brent = _read_fred(RAW / "fred" / "DCOILBRENTEU.csv")
    dgs10 = _read_fred(RAW / "fred" / "DGS10.csv")
    dff = _read_fred(RAW / "fred" / "DFF.csv")
    return {
        "vix": {**( _lookbacks(vix_series) or {}), "ok": bool(vix_series),
                "source": vix_src, "sourceShort": vix_short,
                "zones": [
                    {"id": "calm", "label": "平靜", "lo": 0, "hi": 15},
                    {"id": "mod", "label": "15–20", "lo": 15, "hi": 20},
                    {"id": "elev", "label": "警戒", "lo": 20, "hi": 30},
                    {"id": "panic", "label": "恐慌", "lo": 30, "hi": 80},
                ],
                "zoneMax": 80},
        "wti": {**( _lookbacks(wti) or {}), "ok": bool(wti),
                "source": "FRED DCOILWTICO（WTI Cushing，美元／桶）https://fred.stlouisfed.org/series/DCOILWTICO",
                "sourceShort": "FRED WTI", "unit": "美元／桶"},
        "brent": {**( _lookbacks(brent) or {}), "ok": bool(brent),
                  "source": "FRED DCOILBRENTEU（Brent，美元／桶）https://fred.stlouisfed.org/series/DCOILBRENTEU",
                  "sourceShort": "FRED Brent", "unit": "美元／桶"},
        "dgs10": {**( _lookbacks(dgs10) or {}), "ok": bool(dgs10),
                  "source": "FRED DGS10（美國 10 年期公債市場殖利率，%）https://fred.stlouisfed.org/series/DGS10",
                  "sourceShort": "FRED DGS10", "unit": "%"},
        "dff": {**( _lookbacks(dff) or {}), "ok": bool(dff),
                "source": "FRED DFF（有效聯邦基金利率，%）https://fred.stlouisfed.org/series/DFF",
                "sourceShort": "FRED DFF", "unit": "%"},
    }



# ---------- retail money / sentiment indicators ----------

def _pct_change(new, old):
    if new is None or old in (None, 0):
        return None
    return 100.0 * (new / old - 1.0)


def fetch_retail() -> dict:
    """Fetch official retail-sentiment / money pages. Failures are recorded, never invented."""
    dest = RAW / "retail"
    dest.mkdir(parents=True, exist_ok=True)
    log = {"retrieved_at_Taipei": now_tpe(), "sources": {}}
    pages = {
        "aaii": ("https://www.aaii.com/sentiment-survey", dest / "aaii-sentiment-survey.html"),
        "cboe": ("https://www.cboe.com/us/options/market_statistics/daily/", dest / "cboe-daily-market-statistics.html"),
        "finra": ("https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics", dest / "finra-margin-statistics.html"),
        "ici": ("https://www.ici.org/research/stats/mmf", dest / "ici-mmf.html"),
    }
    for key, (url, path) in pages.items():
        ok, body, err = http_get(url, path, headers={"User-Agent": UA, "Referer": url})
        log["sources"][key] = {"ok": ok, "error": err, "bytes": len(body), "url": url}
        time.sleep(0.25)
    # Optional monthly retail MMF from FRED H.6 (ICI weekly is the primary cash series).
    log["fred_rmfsl"] = fetch_fred_series("RMFSL")
    (dest / "_fetch-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2))
    return log


def _parse_aaii(path: Path) -> dict:
    html = path.read_text(errors="replace")
    week = None
    m = re.search(r"Week ending\s+([A-Za-z]+ \d{1,2}, \d{4})", html)
    if m:
        week = dt.datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    def grab(label):
        pat = (
            rf'<div class="ssv2-slabel {label}">.*?</div>\s*'
            rf'<div class="ssv2-snum {label}">([0-9.]+)%</div>\s*'
            rf'<div class="ssv2-savg">Avg\s+([0-9.]+)%</div>'
        )
        mm = re.search(pat, html, re.S | re.I)
        if not mm:
            return None, None
        return float(mm.group(1)), float(mm.group(2))
    bull, bull_avg = grab("bull")
    neut, neut_avg = grab("neut")
    bear, bear_avg = grab("bear")
    sm = re.search(r"Bull\s*[–—-]\s*Bear Spread:\s*([+\-−]?\s*[0-9.]+)\s*pp", html)
    spread = None
    if sm:
        spread = float(sm.group(1).replace("−", "-").replace(" ", ""))
    weeks = []
    for wm in re.finditer(
        r'<div class="date">(\d{1,2}/\d{1,2}/\d{4})</div>\s*<div class="bars">\s*'
        r'<div class="bar bullish"[^>]*>\s*([0-9.]+)%\s*</div>\s*'
        r'<div class="bar neutral"[^>]*>\s*([0-9.]+)%\s*</div>\s*'
        r'<div class="bar bearish"[^>]*>\s*([0-9.]+)%\s*</div>',
        html,
    ):
        md, y = wm.group(1).rsplit("/", 1)[0], wm.group(1).rsplit("/", 1)[1]
        mm, dd = md.split("/")
        weeks.append({
            "week_ending": f"{y}-{int(mm):02d}-{int(dd):02d}",
            "bull": float(wm.group(2)),
            "neutral": float(wm.group(3)),
            "bear": float(wm.group(4)),
        })
    if bull is None or bear is None or week is None:
        return {"ok": False, "reason": "AAII 頁面未能解析出本週看多／看空比例"}
    if spread is None:
        spread = round(bull - bear, 1)
    return {
        "ok": True,
        "week_ending": week,
        "bull": bull, "neutral": neut, "bear": bear,
        "avg_bull": bull_avg, "avg_neutral": neut_avg, "avg_bear": bear_avg,
        "spread": spread,
        "weeks": weeks,
        "source": "AAII Investor Sentiment Survey，https://www.aaii.com/sentiment-survey",
        "sourceShort": "AAII",
    }


def _parse_cboe(path: Path) -> dict:
    html = path.read_text(errors="replace")
    # The daily-stats payload is JSON-in-a-string, often with escaped quotes.
    text = html.replace("\\\"", '"')
    date = None
    m = re.search(r'"selectedDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', text)
    if m:
        date = m.group(1)
    ratios = {}
    for name, val in re.findall(r'"name"\s*:\s*"([^"]*PUT/CALL RATIO)"\s*,\s*"value"\s*:\s*"([0-9.]+)"', text):
        ratios[name] = float(val)
    eq = ratios.get("EQUITY PUT/CALL RATIO")
    tot = ratios.get("TOTAL PUT/CALL RATIO")
    if eq is None or date is None:
        return {"ok": False, "reason": "Cboe 每日市場統計未能解析出權益賣權／買權比或日期"}
    return {
        "ok": True,
        "date": date,
        "equity": eq,
        "total": tot,
        "index": ratios.get("INDEX PUT/CALL RATIO"),
        "source": "Cboe Daily Market Statistics，https://www.cboe.com/us/options/market_statistics/daily/",
        "sourceShort": "Cboe",
    }


def _parse_rmfsl() -> dict:
    path = RAW / "fred" / "RMFSL.csv"
    if not path.exists():
        return {"ok": False, "reason": "沒有 FRED RMFSL 檔"}
    rows = []
    with path.open() as f:
        r = csv.DictReader(f)
        for row in r:
            v = row.get("RMFSL")
            if v in (None, "", "."):
                continue
            try:
                rows.append((row["observation_date"], float(v)))
            except ValueError:
                continue
    if not rows:
        return {"ok": False, "reason": "FRED RMFSL 無有效列"}
    last_d, last_v = rows[-1]
    prev_d, prev_v = (rows[-2] if len(rows) >= 2 else (None, None))
    yoy_v = None
    yoy_d = None
    # same month prior year
    y, m, _ = last_d.split("-")
    target = f"{int(y)-1}-{m}-01"
    for d, v in rows:
        if d.startswith(target[:7]):
            yoy_d, yoy_v = d, v
    return {
        "ok": True,
        "date": last_d[:7],
        "value": last_v,  # billions, seasonally adjusted monthly
        "prev": prev_v,
        "prev_date": (prev_d or "")[:7],
        "mom": None if prev_v is None else _pct_change(last_v, prev_v),
        "yoy": None if yoy_v is None else _pct_change(last_v, yoy_v),
        "yoy_date": (yoy_d or "")[:7],
        "yoy_value": yoy_v,
        "source": "FRED RMFSL（H.6 零售貨幣基金，月、季調，十億美元）https://fred.stlouisfed.org/series/RMFSL",
        "sourceShort": "FRED RMFSL",
        "note": "這是聯準會 H.6 的月頻、季調零售貨幣基金，和 ICI 每週（未季調、週三截止）口徑不同，只作年增對照，不可直接相加減。",
    }


def process_retail() -> dict:
    raw = RAW / "retail"
    out = {"ok": False, "retrieved_at_Taipei": now_tpe()}
    aaii_path = raw / "aaii-sentiment-survey.html"
    cboe_path = raw / "cboe-daily-market-statistics.html"
    finra_path = raw / "finra-margin-statistics.json"
    ici_path = raw / "ici-mmf.json"

    aaii = _parse_aaii(aaii_path) if aaii_path.exists() else {"ok": False, "reason": "尚未取到 AAII 頁面"}
    cboe = _parse_cboe(cboe_path) if cboe_path.exists() else {"ok": False, "reason": "尚未取到 Cboe 每日市場統計"}
    finra = {"ok": False, "reason": "尚未取到 FINRA 融資統計"}
    if finra_path.exists():
        blob = json.loads(finra_path.read_text())
        rows = blob.get("rows") or []
        if rows:
            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else None
            yoy = next((r for r in rows if r.get("month") == _month_shift(latest["month"], -12)), None)
            debit = latest["debit_margin"]
            finra = {
                "ok": True,
                "month": latest["month"],
                "debit": debit,
                "debit_trillion": debit / 1_000_000.0,  # table is $ millions
                "free_credit_cash": latest.get("free_credit_cash"),
                "free_credit_margin": latest.get("free_credit_margin"),
                "prev_month": (prev or {}).get("month"),
                "prev_debit": (prev or {}).get("debit_margin"),
                "mom": None if not prev else _pct_change(debit, prev["debit_margin"]),
                "yoy_month": (yoy or {}).get("month"),
                "yoy_debit": (yoy or {}).get("debit_margin"),
                "yoy": None if not yoy else _pct_change(debit, yoy["debit_margin"]),
                "rows": rows,
                "unit": blob.get("unit") or "million USD",
                "source": f"{blob.get('source_name')}，{blob.get('source_url')}",
                "sourceShort": "FINRA",
                "retrieved_at_Taipei": blob.get("retrieved_at_Taipei"),
            }

    ici = {"ok": False, "reason": "尚未取到 ICI 貨幣基金週報"}
    if ici_path.exists():
        blob = json.loads(ici_path.read_text())
        tab = (blob.get("table") or {})
        tot = tab.get("total") or {}
        ret = tab.get("total_retail") or {}
        inst = tab.get("total_institutional") or {}
        if tot.get("latest") is not None:
            ici = {
                "ok": True,
                "week_ending": blob.get("week_ended"),
                "released": blob.get("released"),
                "total": tot.get("latest"),
                "total_prev": tot.get("prev"),
                "total_change": tot.get("change"),
                "retail": ret.get("latest"),
                "retail_prev": ret.get("prev"),
                "retail_change": ret.get("change"),
                "institutional": inst.get("latest"),
                "institutional_change": inst.get("change"),
                "source": f"{blob.get('source_name')}，{blob.get('source_url')}",
                "sourceShort": "ICI",
                "retrieved_at_Taipei": blob.get("retrieved_at_Taipei"),
                "note": blob.get("note"),
            }

    rm = _parse_rmfsl()

    # Plain-language read from AAII vs its own published averages. Not a trade instruction.
    read = "資料不足，暫不判斷"
    if aaii.get("ok"):
        bull, bear = aaii["bull"], aaii["bear"]
        ab, ae = aaii.get("avg_bull"), aaii.get("avg_bear")
        spread = aaii["spread"]
        if ab is not None and ae is not None and bull < ab and bear > ae and spread < 0:
            read = "偏悲觀"
        elif ab is not None and ae is not None and bull > ab and bear < ae and spread > 0:
            read = "偏樂觀"
        else:
            read = "情緒分歧、沒有一面倒"
    headline = read
    bits = []
    if aaii.get("ok"):
        bits.append(f"AAII 多空差 {aaii['spread']:+.1f} 個百分點".replace("+", "＋").replace("＋-", "−").replace("-", "−") if False else None)
    # simpler headline composition
    parts = [read] if aaii.get("ok") else []
    if ici.get("ok"):
        parts.append("場邊現金仍高")
    if finra.get("ok"):
        parts.append("融資餘額仍高")
    headline = "；".join(parts) if parts else "資料暫缺"

    missing = []
    if not aaii.get("ok"):
        missing.append("AAII：" + (aaii.get("reason") or "暫缺"))
    if not finra.get("ok"):
        missing.append("FINRA：" + (finra.get("reason") or "暫缺"))
    if not ici.get("ok"):
        missing.append("ICI：" + (ici.get("reason") or "暫缺"))
    if not cboe.get("ok"):
        missing.append("Cboe 賣權／買權比：" + (cboe.get("reason") or "暫缺"))

    out.update({
        "ok": any(x.get("ok") for x in (aaii, finra, ici, cboe)),
        "read": read,
        "headline": headline,
        "aaii": aaii,
        "finra": finra,
        "ici": ici,
        "cboe": cboe,
        "rmfsl": rm,
        "missing": missing,
        "blurb": (
            "這組指標描述散戶情緒與場邊現金、融資使用的背景，不是買進或賣出指令。"
            "AAII 是會員自願填答的每週調查（問未來六個月股市方向），不是全體散戶的普查；"
            "FINRA 融資餘額涵蓋會員券商客戶保證金帳戶，不限散戶；"
            "ICI 零售／法人分類依公開說明書，不是帳戶層級的身分。"
        ),
    })
    return out


def _month_shift(ym: str, delta_months: int) -> str:
    y, m = [int(x) for x in ym.split("-")[:2]]
    m0 = y * 12 + (m - 1) + delta_months
    y2, m2 = divmod(m0, 12)
    return f"{y2}-{m2+1:02d}"


def process_extra() -> dict:
    margins = process_margins()
    fedwatch = process_fedwatch()
    cnn = process_cnn()
    gauges = process_gauges()
    retail = process_retail()
    payload = {
        "margins": margins,
        "fedwatch": fedwatch,
        "cnn": cnn,
        "gauges": gauges,
        "retail": retail,
        "processed_at_Taipei": now_tpe(),
    }
    PROC.mkdir(parents=True, exist_ok=True)
    (PROC / "extra.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    if not args.offline:
        fetch_extra()
    print(json.dumps({k: ("ok" if (v or {}).get("ok") else v) for k, v in process_extra().items() if k != "margins"}, ensure_ascii=False)[:2000])
