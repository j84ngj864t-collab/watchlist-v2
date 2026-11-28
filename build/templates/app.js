(() => {
  const payload = JSON.parse(document.getElementById("payload").textContent);
  const CATS = payload.cats;
  const META = payload.meta || {};
  const STOCKS = payload.stocks;
  const MACRO = payload.macro;
  const PRESS_DEF = payload.pressDef;

  const navEl = document.getElementById("nav");
  const gridEl = document.getElementById("grid");
  const titleEl = document.getElementById("title");
  const subEl = document.getElementById("subtitle");
  const extraEl = document.getElementById("extra");
  let current = "chip";
  const charts = [];

  function count(id) {
    if (id === "all") return STOCKS.length;
    if (id === "macro") return 4;
    return STOCKS.filter(s => s.cat === id).length;
  }

  function pctClass(pos) { return pos === "up" ? "up" : pos === "mid" ? "mid" : "down"; }
  function pctText(p, pos) {
    if (p == null || !Number.isFinite(Number(p))) return { n: "—", tag: "月線資料不足" };
    const n = (p > 0 ? "+" : "") + p.toFixed(2) + "%";
    const tag = pos === "up" ? "站上月線" : pos === "mid" ? "臨界" : "月線下方";
    return { n, tag };
  }
  function cssVar(name, fb) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fb;
  }
  function money(n, d) {
    if (n == null || !Number.isFinite(n)) return "—";
    return n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function fmtVol(n) {
    if (n == null || !Number.isFinite(n)) return "—";
    if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
    return String(Math.round(n));
  }

  function renderNav() {
    navEl.innerHTML = CATS.map(c =>
      `<button type="button" class="nav-btn${c.id===current?" active":""}" data-id="${c.id}" aria-current="${c.id===current?"page":"false"}">
        <span class="name">${c.name}</span><span class="count">${count(c.id)}</span>
      </button>`
    ).join("");
  }


  function marginBox(s) {
    const m = s.margin || {};
    if (m.kind === "op") {
      return `<div class="gm-box">
        <div class="gm-title">毛利率／營業利益率</div>
        <div class="gm-na">${m.reason || "不適用（公司不揭露毛利）"}</div>
        <div class="gm-grid">
          <div>
            <div class="lbl">營業利益率</div>
            <div class="val">${m.op_pct != null ? money(m.op_pct, 1) + "%" : "—"}</div>
            <div class="hint">${m.op_label || ""}</div>
          </div>
        </div>
        <div class="src">${m.detail ? m.detail + " " : ""}${m.source || s.gmHint || ""}</div>
      </div>`;
    }
    if (m.kind === "na" || (m.ok === false && m.reason)) {
      return `<div class="gm-box">
        <div class="gm-title">毛利率</div>
        <div class="gm-na">${m.reason || "—"}</div>
        <div class="src">${m.detail ? m.detail + " " : ""}${m.source || s.gmHint || ""}</div>
      </div>`;
    }
    const q = m.q_pct != null ? money(m.q_pct, 1) + "%" : (s.gm || "—");
    const qng = m.q_ng != null ? `／non-GAAP ${money(m.q_ng, 1)}%` : "";
    const ttm = m.ttm_pct != null ? money(m.ttm_pct, 1) + "%" : "—";
    const tng = m.ttm_ng != null ? `／non-GAAP ${money(m.ttm_ng, 1)}%` : "";
    return `<div class="gm-box">
      <div class="gm-title">毛利率</div>
      <div class="gm-grid">
        <div>
          <div class="lbl">最近一季 GAAP</div>
          <div class="val">${q}${qng ? `<span class="ng">${qng}</span>` : ""}</div>
          <div class="hint">${m.q_label || ""}</div>
        </div>
        <div>
          <div class="lbl">近四季 TTM GAAP</div>
          <div class="val">${ttm}${tng ? `<span class="ng">${tng}</span>` : ""}</div>
          <div class="hint">${m.ttm_label || ""}</div>
        </div>
      </div>
      <div class="src">${m.note ? m.note + " " : ""}${m.source || s.gmHint || ""}</div>
    </div>`;
  }

  const ZONE_COLORS = {
    ef: "#b42318", f: "#dc6803", n: "#ca8a04", g: "#12b981", eg: "#0f766e",
    calm: "#12b981", mod: "#ca8a04", elev: "#dc6803", panic: "#b42318"
  };

  function polar(cx, cy, r, deg) {
    const rad = deg * Math.PI / 180;
    return [cx + r * Math.cos(rad), cy - r * Math.sin(rad)];
  }
  function arcPath(cx, cy, r, a0, a1) {
    const [x0, y0] = polar(cx, cy, r, a0);
    const [x1, y1] = polar(cx, cy, r, a1);
    const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
    const sweep = a1 < a0 ? 1 : 0; // clockwise from left (180) to right (0)
    return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} ${sweep} ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }
  function semiGauge(g) {
    const min = g.min ?? 0, max = g.max ?? 100;
    const score = g.score;
    const cx = 160, cy = 138, r = 112, rInner = 78;
    const toAng = v => 180 - 180 * Math.max(0, Math.min(1, (v - min) / (max - min)));
    const zones = g.zones || [];
    const arcs = zones.map(z => {
      const a0 = toAng(z.lo), a1 = toAng(z.hi);
      const color = ZONE_COLORS[z.id] || "#888";
      return `<path d="${arcPath(cx, cy, r, a0, a1)}" fill="none" stroke="${color}" stroke-width="22" stroke-linecap="butt"/>`;
    }).join("");
    const labels = zones.map(z => {
      const mid = toAng((z.lo + z.hi) / 2);
      const [x, y] = polar(cx, cy, r + 22, mid);
      return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle" class="g-zone">${z.label}</text>`;
    }).join("");
    let needle = "";
    if (score != null && Number.isFinite(score)) {
      const ang = toAng(score);
      const [nx, ny] = polar(cx, cy, r - 8, ang);
      needle = `<line x1="${cx}" y1="${cy}" x2="${nx.toFixed(1)}" y2="${ny.toFixed(1)}" class="g-needle"/>
        <circle cx="${cx}" cy="${cy}" r="6" class="g-hub"/>`;
    }
    const main = score == null ? "—" : (g.scoreFmt || String(score));
    return `<div class="gauge-semi">
      <svg viewBox="0 -6 320 214" class="gauge-svg" role="img" aria-label="${g.title || ""} ${main}">
        ${arcs}${labels}${needle}
        <text x="${cx}" y="170" text-anchor="middle" class="g-score">${main}</text>
        <text x="${cx}" y="196" text-anchor="middle" class="g-sub">${g.caption || ""}</text>
      </svg>
    </div>`;
  }
  function cmpLine(label, val, date, unit) {
    if (val == null) return "";
    const u = unit || "";
    return `<span class="cmp"><em>${label}</em> ${money(val, gDigits(val))}${u}${date ? `<small>${date}</small>` : ""}</span>`;
  }
  function gDigits(v) {
    return Math.abs(v) >= 20 ? 2 : 2;
  }
  function rangeGauge(g) {
    if (!g || g.latest == null || g.low52 == null || g.high52 == null) {
      return `<div class="missing">52 週區間資料不足。</div>`;
    }
    const unit = g.unit || "";
    const pos = g.pos == null ? 0.5 : g.pos;
    const pct = Math.max(0, Math.min(1, pos)) * 100;
    function mark(val, lab) {
      if (val == null || g.high52 === g.low52) return "";
      const p = (val - g.low52) / (g.high52 - g.low52);
      const left = Math.max(0, Math.min(1, p)) * 100;
      return `<span class="tick" style="left:${left}%" title="${lab} ${money(val,2)}${unit}"><i></i><b>${lab}</b></span>`;
    }
    return `<div class="range-gauge">
      <div class="range-head">
        <strong>${money(g.latest, 2)}${unit}</strong>
        <span class="hint">截至 ${g.latestDate || ""}　近 52 週位置 ${money(pct, 0)}%</span>
      </div>
      <div class="range-bar-wrap">
        <div class="range-ends"><span>低 ${money(g.low52, 2)}${unit}<small>${g.low52Date || ""}</small></span>
        <span>高 ${money(g.high52, 2)}${unit}<small>${g.high52Date || ""}</small></span></div>
        <div class="range-bar"><span class="fill" style="width:${pct}%"></span>
          ${mark(g.ago1y, "1年")}
          ${mark(g.ago1m, "1月")}
          ${mark(g.ago1w, "1週")}
          <span class="now" style="left:${pct}%"></span>
        </div>
      </div>
      <div class="cmp-row">
        ${cmpLine("前一週", g.ago1w, g.ago1wDate, unit)}
        ${cmpLine("前一月", g.ago1m, g.ago1mDate, unit)}
        ${cmpLine("前一年", g.ago1y, g.ago1yDate, unit)}
      </div>
    </div>`;
  }


  function fcfSpark(series) {
    if (!series || series.length < 2) return "";
    const vals = series.map(p => Number(p.v)).filter(Number.isFinite);
    if (!vals.length) return "";
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const w = 220, h = 44, padX = 10, padY = 6;
    const xs = series.map((_, i) => padX + i * (w - 2 * padX) / Math.max(1, series.length - 1));
    const ys = series.map(pt => {
      const t = hi === lo ? 0.5 : (Number(pt.v) - lo) / (hi - lo);
      return h - padY - t * (h - 2 * padY);
    });
    const line = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(" ");
    const area = `${line} L ${xs[xs.length-1].toFixed(1)} ${h} L ${xs[0].toFixed(1)} ${h} Z`;
    const dots = xs.map((x, i) => `<circle cx="${x.toFixed(1)}" cy="${ys[i].toFixed(1)}" r="2.2"/>`).join("");
    const labs = series.map((pt, i) => `<text x="${xs[i].toFixed(1)}" y="${h + 11}" text-anchor="middle">${pt.y || ""}</text>`).join("");
    return `<svg class="fcf-spark" viewBox="0 0 ${w} ${h+18}" width="100%" height="64" role="img" aria-label="五年自由現金流">
      <path class="spark-area" d="${area}"></path>
      <path class="spark-line" d="${line}" fill="none"></path>
      ${dots}${labs}
    </svg>`;
  }
  function valueBox(s) {
    const v = s.valueMetrics;
    if (!v) return "";
    const pe = v.pe != null ? money(v.pe, 1) + "x" : "—";
    const fy = v.fcfYield != null ? money(v.fcfYield, 2) + "%" : "—";
    const dy = v.divYield != null ? money(v.divYield, 2) + "%" : "—";
    const nd = v.ndEbitdaLabel || (v.ndEbitda != null ? money(v.ndEbitda, 2) + "x" : "—");
    return `<div class="value-box">
      <div class="gm-title">已審估值（11/13 收盤推算）</div>
      <div class="value-grid">
        <div><div class="lbl">本益比</div><div class="val">${pe}</div><div class="hint">${v.peBasis || s.peHint || ""}</div></div>
        <div><div class="lbl">FCF yield</div><div class="val">${fy}</div><div class="hint">${v.fcfYieldLabel || ""}</div></div>
        <div><div class="lbl">股息殖利率</div><div class="val">${dy}</div><div class="hint">最新季配 × 4 ÷ 收盤</div></div>
        <div><div class="lbl">淨負債／EBITDA</div><div class="val" style="font-size:21px">${nd}</div><div class="hint">已審稿口徑</div></div>
      </div>
      <div class="fcf-wrap">
        <div class="lbl">5 年 FCF（${v.fcfUnit || "百萬美元"}）</div>
        ${fcfSpark(v.fcfSeries)}
        <div class="hint">${v.fcfTrend || ""} ${v.fcfSeriesNote || ""}</div>
      </div>
    </div>`;
  }

  function lendingBox(s) {
    const v = s.lendingMetrics;
    if (!v) return "";
    const src = [v.source, v.date].filter(Boolean).join("　");
    return `<div class="value-box lending-box">
      <div class="gm-title">已審估值（11/13 收盤推算）</div>
      <div class="val" style="font-size:21px">${v.value || "—"}</div>
      <div class="hint">${v.metric || ""}</div>
      <div class="src">${v.basis || ""}</div>
      ${src ? `<div class="src">${src}</div>` : ""}
    </div>`;
  }
  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function ttmPeLabel(v) {
    const p = v && v.ttmPe;
    if (p == null || p === "") return "—";
    if (typeof p === "number" && Number.isFinite(p)) return money(p, 1) + "x";
    const s = String(p);
    if (/^-?\d+(\.\d+)?$/.test(s)) return money(Number(s), 1) + "x";
    if (s.startsWith("不適用")) return "不適用";
    return s;
  }
  function securityBox(s) {
    const v = s.securityMetrics;
    if (!v) return "";
    const src = [v.source, v.date].filter(Boolean).join("　");
    const fcf = v.fcfYieldPct != null ? money(v.fcfYieldPct, 2) + "%" : "—";
    return `<div class="value-box security-box">
      <div class="gm-title">已審估值（11/13 收盤推算）</div>
      <div class="value-grid">
        <div>
          <div class="lbl">預估本益比</div>
          <div class="val">${esc(v.fwdPeLabel || "—")}</div>
          <div class="hint">公司 non-GAAP 全年指引中點，不是共識</div>
        </div>
        <div>
          <div class="lbl">EV/Sales（TTM）</div>
          <div class="val">${esc(v.evSalesLabel || "—")}</div>
          <div class="hint">${esc(v.evSalesHint || "")}</div>
        </div>
        <div>
          <div class="lbl">TTM GAAP 本益比</div>
          <div class="val" style="font-size:21px">${esc(ttmPeLabel(v))}</div>
          <div class="hint">虧損則不適用</div>
        </div>
        <div>
          <div class="lbl">FCF yield</div>
          <div class="val">${fcf}</div>
          <div class="hint">已審稿推算</div>
        </div>
      </div>
      <div class="src">${esc(v.basis || "")}</div>
      ${src ? `<div class="src">${esc(src)}</div>` : ""}
      <div class="src pe-basis-note">卡片上的本益比與未來本益比來自 CNBC Quote（延遲／非官方），口徑與本段已審估值不同，不會被改寫。</div>
    </div>`;
  }
  function cardHighlight(s) {
    if (!s.reasonLine && !s.earnLine) return "";
    return `<div class="card-highlight">
      ${s.earnLine ? `<div class="earn">${esc(s.earnLine)}</div>` : ""}
      ${s.reasonLine ? `<div class="reason">${esc(s.reasonLine)}</div>` : ""}
    </div>`;
  }
    function shortTaipei(s) {
    const t = s.ahTimeTaipei || "";
    const m = String(t).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (m) return `台北 ${Number(m[2])}/${Number(m[3])} ${m[4]}:${m[5]}`;
    return "";
  }
  function primaryQuote(s) {
    if (s.ahPrice != null) {
      const clock = shortTaipei(s);
      const time = clock
        ? `盤後 · ${clock}`
        : (s.ahSource === "massive-open-close" ? "盤後 · Massive（無鐘點）" : "盤後 · 僅給日期，無鐘點");
      return { price: s.ahPrice, change: s.ahChangePct, time, kind: "ah" };
    }
    return {
      price: s.regClose != null ? s.regClose : s.price,
      change: s.regChangePct,
      time: s.regLabel || "常規收盤",
      kind: "reg"
    };
  }
  function chgText(v) {
    if (v == null || !Number.isFinite(Number(v))) return { t: "—", k: "" };
    const n = Number(v);
    const t = (n > 0 ? "+" : "") + n.toFixed(2) + "%";
    return { t, k: n > 0 ? "up" : n < 0 ? "down" : "" };
  }
  function callBadges(s) {
    return (s.call || []).map(b => `<span class="badge ${b.k}">${b.t}</span>`).join("");
  }
  function peFace(s) {
    const q = s.quotePE || {};
    const t = q.trailing || { label: "N/A", kind: "na" };
    const f = q.forward || { label: "N/A", kind: "na" };
    return { t, f };
  }
  function prevCallText(s) {
    const p = s.prevCall;
    if (!p) return "";
    if (Array.isArray(p)) {
      return p.map(b => (b && b.t) ? b.t : String(b)).filter(Boolean).join("／");
    }
    if (typeof p === "object" && p.t) return p.t;
    return String(p);
  }

  function maPressHTML(s) {
    const mp = s.maPress || {};
    const a = mp.sma20 || { status: "insufficient" };
    const b = mp.sma60 || { status: "insufficient" };
    const insuf20 = a.status === "insufficient";
    const insuf60 = b.status === "insufficient";
    const below20 = a.status === "below";
    const below60 = b.status === "below";
    const item = (item, name) => {
      if (!item || item.status === "insufficient") {
        return `<div class="ma-item insuff"><span class="k">${name}資料不足</span></div>`;
      }
      if (item.status === "below") {
        const pct = (item.pct > 0 ? "+" : "") + Number(item.pct).toFixed(2) + "%";
        return `<div class="ma-item below"><span class="k">${name}壓力</span><span class="v">${money(item.value, 2)}</span><span class="d">距收盤 ${pct}</span></div>`;
      }
      return `<div class="ma-item above"><span class="k">站上${name}</span><span class="v">${money(item.value, 2)}</span></div>`;
    };
    if (insuf20 && insuf60) {
      return `<div class="card-ma-press insuff"><div class="lbl">月線／季線壓力（技術參考）</div><div class="ma-line muted">資料不足</div></div>`;
    }
    if (!below20 && !below60 && !insuf20 && !insuf60) {
      return `<div class="card-ma-press above"><div class="lbl">月線／季線壓力（技術參考）</div><div class="ma-line ok">站上月線/季線</div></div>`;
    }
    const parts = [];
    if (below20) parts.push(item(a, "月線"));
    else if (insuf20) parts.push(item(a, "月線"));
    if (below60) parts.push(item(b, "季線"));
    else if (insuf60) parts.push(item(b, "季線"));
    // If only one MA is resistance, do not also print 站上 for the other — keep the face compact.
    return `<div class="card-ma-press"><div class="lbl">月線／季線壓力（技術參考）</div><div class="ma-items">${parts.join("")}</div></div>`;
  }
  function maPressDetail(s) {
    const mp = s.maPress || {};
    const a = mp.sma20 || { status: "insufficient" };
    const b = mp.sma60 || { status: "insufficient" };
    const fmt = (item, name) => {
      if (!item || item.status === "insufficient") return `${name}資料不足`;
      if (item.status === "below") {
        const pct = (item.pct > 0 ? "+" : "") + Number(item.pct).toFixed(2) + "%";
        return `${name}壓力 ${money(item.value, 2)}（距收盤 ${pct}）`;
      }
      return `站上${name} ${money(item.value, 2)}`;
    };
    if (a.status === "insufficient" && b.status === "insufficient") {
      return "月線／季線壓力（技術參考）：資料不足";
    }
    if (a.status === "above" && b.status === "above") {
      return "月線／季線壓力（技術參考）：站上月線/季線";
    }
    return "月線／季線壓力（技術參考）：" + fmt(a, "月線") + "；" + fmt(b, "季線");
  }
  function cardHTML(s) {
    const p = pctText(s.smaPct, s.smaPos);
    const badges = callBadges(s);
    const q = primaryQuote(s);
    const chg = chgText(q.change);
    const pe = peFace(s);
    const press = (s.pressure || []).map(x => `${x.label} ${money(x.price, 2)}（${x.date}）`).join("；");
    const pressLine = press
      ? `壓力價（技術參考）：${press}`
      : (s.pressNote || "現價上方暫無獨立壓力價（可能已接近或高於近 52 週／上市以來高點）。");
    const regLine = (q.kind === "ah" && s.regClose != null)
      ? `<div class="card-reg">${s.regLabel || "常規收盤"} ${money(s.regClose, 2)} <span class="${s.regChangePct==null?"":(s.regChangePct>=0?"up":"down")}">${s.regChangePct==null?"—":((s.regChangePct>0?"+":"")+Number(s.regChangePct).toFixed(2)+"%")}</span></div>`
      : "";
    return `<article class="card" id="${s.ticker}">
      <div class="card-head">
        <div>
          <h3 class="ticker">${s.ticker}</h3>
          <p class="cname">${s.name}</p>
          ${s.subgroup ? `<p class="subgroup">${esc(s.subgroup)}</p>` : ""}
          ${s.changed ? `<div class="change-flag">${esc(s.changeLabel || "較11/21變動")}</div>` : ""}
        </div>
        <div class="badges">${badges}</div>
      </div>
      <div class="card-price">
        <span class="px">${q.price != null ? money(q.price, 2) : "—"}</span>
        <span class="chg ${chg.k}">${chg.t}</span>
        <span class="meta">${q.time}</span>
        ${regLine}
      </div>
      <div class="card-pe">
        <div class="pe-item">
          <div class="lbl">本益比</div>
          <div class="val ${pe.t.kind || ""}">${pe.t.label}</div>
        </div>
        <div class="pe-item">
          <div class="lbl">未來本益比</div>
          <div class="val ${pe.f.kind || ""}">${pe.f.label}</div>
        </div>
      </div>
      ${cardHighlight(s)}
      ${maPressHTML(s)}
      <div class="chart-legend">
        <span><i class="sma20"></i>月線 SMA20</span>
        <span><i class="sma60"></i>季線 SMA60</span>
        <span><i class="press"></i>壓力價</span>
        <span>K 線＋成交量</span>
      </div>
      <div class="chart-wrap" data-chart="${s.ticker}"></div>
      ${s.seriesNote ? `<div class="src series-note">${s.seriesNote}</div>` : ""}
      <details class="more">
        <summary>詳細</summary>
        <div class="more-body">
          ${s.callNote ? `<div class="src call-note">${s.callNote}</div>` : ""}
          ${s.changed ? `<div class="row change-reason"><dt>${esc(s.changeLabel || "較11/21變動")}</dt><dd>${esc((prevCallText(s) ? ("原判斷：" + prevCallText(s) + "。") : "") + (s.changeReason || "判斷已更新。"))}</dd></div>` : ""}
          <div class="metrics metrics-4">
            <div class="metric metric-ah">
              <div class="lbl">最新盤後價（美元）</div>
              <div class="val">${s.ahPrice != null ? money(s.ahPrice, 2) : "—"}</div>
              <div class="hint">${s.ahHint || "資料暫缺"}</div>
            </div>
            <div class="metric">
              <div class="lbl">${s.regLabel || "常規收盤"}</div>
              <div class="val ${s.regChangePct==null?"":(s.regChangePct>=0?"up":"down")}">${s.regClose != null ? money(s.regClose, 2) : "—"}</div>
              <div class="hint">${s.regHint || ""}</div>
            </div>
            <div class="metric">
              <div class="lbl">相對月線（SMA20）</div>
              <div class="val ${s.smaPct==null?"":pctClass(s.smaPos)}">${s.smaPct==null?"—":p.n}</div>
              <div class="hint">${s.smaPct==null?"月線資料不足":p.tag + "　月線 " + money(s.sma20, 2)}</div>
            </div>
            <div class="metric">
              <div class="lbl">${s.peLabel || "預估本益比"}</div>
              <div class="val" style="font-size:18px">${s.pe || "—"}</div>
              <div class="hint">${s.lendingMetrics ? (s.lendingMetrics.metric || "") : (s.peHint || "")}</div>
            </div>
          </div>
          ${marginBox(s)}
          ${valueBox(s)}
          ${lendingBox(s)}
          ${securityBox(s)}
          ${s.seriesNote ? `<div class="src series-note">${s.seriesNote}</div>` : ""}
          <div class="rows">
            ${s.earnDetail ? `<div class="row"><dt>下次財報</dt><dd>${esc(s.earnDetail)}</dd></div>` : ""}
            ${s.fullReport ? `<div class="row"><dt>完整報告</dt><dd><a class="full-report" href="${esc(s.fullReport)}">${esc(s.fullReportLabel || "開啟已審研究報告")}</a></dd></div>` : ""}
            ${s.insiderDetail ? `<div class="row"><dt>內部人買入</dt><dd>${esc(s.insiderDetail)}</dd></div>` : ""}
            <div class="row"><dt>升級條件</dt><dd>${esc(s.up || "—")}</dd></div>
            <div class="row"><dt>降級條件</dt><dd>${esc(s.down || "—")}</dd></div>
            ${s.risks ? `<div class="row"><dt>主要風險</dt><dd>${esc(s.risks)}</dd></div>` : ""}
            ${s.gaps ? `<div class="row"><dt>資料缺口</dt><dd>${esc(s.gaps)}</dd></div>` : ""}
          </div>
          <div class="press-list ma-press-detail">${maPressDetail(s)}</div>
          <div class="press-list">${pressLine}</div>
          ${s.note ? `<div class="note">${esc(s.note)}</div>` : ""}
          <div class="src">資料來源：${esc(s.src || "")}</div>
        </div>
      </details>
    </article>`;
  }
  function summaryTable(list) {
    if (!list.length) return "";
    const rows = list.map(s => {
      const q = primaryQuote(s);
      const chg = chgText(q.change);
      const pe = peFace(s);
      return `<tr data-jump="${s.ticker}" tabindex="0">
        <td class="tkr">${s.ticker}</td>
        <td class="num">${q.price != null ? money(q.price, 2) : "—"}</td>
        <td class="num ${chg.k}">${chg.t}</td>
        <td class="pe ${pe.t.kind || ""}">${pe.t.label}</td>
        <td class="pe ${pe.f.kind || ""}">${pe.f.label}</td>
        <td class="calls">${callBadges(s)}</td>
      </tr>`;
    }).join("");
    return `<div class="sum-wrap"><table class="sum-table">
      <thead><tr><th>代號</th><th>最新價</th><th>漲跌</th><th>本益比</th><th>未來本益比</th><th>判斷</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
  }
  function bindJumps(root) {
    if (!root) return;
    root.querySelectorAll("[data-jump]").forEach(row => {
      const go = () => {
        const id = row.getAttribute("data-jump");
        const el = document.getElementById(id);
        if (!el) return;
        history.replaceState(null, "", "#" + encodeURIComponent(id));
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        el.classList.remove("flash");
        void el.offsetWidth;
        el.classList.add("flash");
      };
      row.addEventListener("click", go);
      row.addEventListener("keydown", ev => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); go(); }
      });
    });
  }

  function pressBox() {
    return `<aside class="press-def"><strong>壓力價怎麼選（技術參考，不是預測）</strong>${PRESS_DEF}</aside>`;
  }

  function missingBox(item) {
    if (item && item.ok === false) {
      return `<div class="missing">資料暫缺：${item.reason || "來源讀取失敗"}</div>`;
    }
    return "";
  }


  function fearAndGreedValueToText(e) {
    if (typeof e !== "number" || !Number.isFinite(e)) return "";
    if (e <= 25) return "Extreme Fear";
    if (e > 25 && e < 45) return "Fear";
    if (e >= 45 && e <= 55) return "Neutral";
    if (e > 55 && e < 75) return "Greed";
    if (e >= 75) return "Extreme Greed";
    return "";
  }
  function getDialRangeAngle(score) {
    let r = score;
    if (typeof r !== "number" || !Number.isFinite(r)) return 0;
    if (r < 0) r = 0;
    if (r > 100) r = 100;
    const a = r <= 25
      ? { rangeStart: -91.1, rangeEnd: -48.5, valueStart: 0, valueEnd: 25 }
      : r < 45
      ? { rangeStart: -45.6, rangeEnd: -12.4, valueStart: 26, valueEnd: 44 }
      : r <= 55
      ? { rangeStart: -9.5, rangeEnd: 10.1, valueStart: 45, valueEnd: 55 }
      : r < 75
      ? { rangeStart: 13, rangeEnd: 45.7, valueStart: 56, valueEnd: 74 }
      : { rangeStart: 48.6, rangeEnd: 90.9, valueStart: 75, valueEnd: 100 };
    const t = (r - a.valueStart) / (a.valueEnd - a.valueStart);
    const span = Math.max(a.rangeStart, a.rangeEnd) - Math.min(a.rangeStart, a.rangeEnd);
    return a.rangeStart + span * t;
  }
  function tplHtml(id) {
    const el = document.getElementById(id);
    return el ? el.innerHTML : "";
  }
  function histItem(cls, label, raw) {
    if (raw == null || !Number.isFinite(Number(raw))) {
      return `<div class="market-fng-gauge__historical-item ${cls}">
        <div class="market-fng-gauge__historical-item-label">${label}</div>
        <div class="market-fng-gauge__historical-item-index">
          <div class="market-fng-gauge__historical-item-index-label"></div>
          <div class="market-fng-gauge__historical-item-index-value">—</div>
        </div>
      </div>`;
    }
    const v = parseInt(raw, 10);
    const tag = fearAndGreedValueToText(v).toLowerCase();
    return `<div class="market-fng-gauge__historical-item ${cls}" data-index-label="${tag}">
      <div class="market-fng-gauge__historical-item-label">${label}</div>
      <div class="market-fng-gauge__historical-item-index">
        <div class="market-fng-gauge__historical-item-index-label"></div>
        <div class="market-fng-gauge__historical-item-index-value">${v}</div>
      </div>
    </div>`;
  }
  function cnnFngCard(cnn) {
    if (!cnn || !cnn.ok) {
      return `<article class="macro-card cnn-fng-card" id="cnn-fng">
        <h3 class="cnn-fng-title">Fear &amp; Greed Index</h3>
        <p class="cnn-fng-sub">What emotion is driving the market now?</p>
        <div class="missing">${(cnn && cnn.reason) || "資料暫缺"}</div>
      </article>`;
    }
    const score = Math.round(Number(cnn.score));
    const label = fearAndGreedValueToText(score).toLowerCase();
    const ang = getDialRangeAngle(score);
    const dial = tplHtml("tpl-cnn-dial");
    let needle = tplHtml("tpl-cnn-needle");
    if (/style="/.test(needle)) needle = needle.replace(/style="[^"]*"/, `style="transform: rotate(${ang}deg)"`);
    else needle = needle.replace(/<svg\b/, `<svg style="transform: rotate(${ang}deg)"`);
    const updated = cnn.last_updated_et
      ? `Last updated ${cnn.last_updated_et}`
      : (cnn.time_et ? `Last updated ${cnn.time_et} ET` : "");
    const tpe = cnn.time_taipei ? `（台北 ${cnn.time_taipei}）` : "";
    return `<article class="macro-card cnn-fng-card" id="cnn-fng">
      <h3 class="cnn-fng-title">Fear &amp; Greed Index</h3>
      <p class="cnn-fng-sub">What emotion is driving the market now?</p>
      <div class="market-fng-gauge" data-showHistorical="true">
        <div class="market-fng-gauge__overview">
          <div class="market-fng-gauge__meter-container">
            <div class="market-fng-gauge__meter" data-index-label="${label}">
              <div class="market-fng-gauge__dial">${dial}</div>
              <div class="market-fng-gauge__hand">${needle}</div>
              <div class="market-fng-gauge__hand-base"></div>
              <div class="market-fng-gauge__dial-number">
                <span class="market-fng-gauge__dial-number-value">${score}</span>
              </div>
            </div>
          </div>
          <div class="market-fng-gauge__historical">
            ${histItem("market-fng-gauge__historical-item--prevClose", "Previous close", cnn.previous_close)}
            ${histItem("market-fng-gauge__historical-item--weekClose", "1 week ago", cnn.previous_1_week)}
            ${histItem("market-fng-gauge__historical-item--monthClose", "1 month ago", cnn.previous_1_month)}
            ${histItem("market-fng-gauge__historical-item--yearClose", "1 year ago", cnn.previous_1_year)}
          </div>
        </div>
        <div class="market-fng-gauge__timestamp">${updated}${tpe}</div>
      </div>
      ${foldNote(cnn.source || "", "資料來源")}
    </article>`;
  }

  function foldNote(html, title) {
    if (!html || !String(html).trim()) return "";
    return `<details class="notes-more"><summary>${title || "說明"}</summary><div class="notes-body">${html}</div></details>`;
  }


  function fmtSpread(v) {
    if (v == null || !Number.isFinite(Number(v))) return "—";
    const n = Number(v);
    const sign = n > 0 ? "＋" : n < 0 ? "−" : "";
    return sign + Math.abs(n).toFixed(1) + " 個百分點";
  }
  function fmtSignedPct(v, digits) {
    if (v == null || !Number.isFinite(Number(v))) return "—";
    const n = Number(v);
    const sign = n > 0 ? "＋" : n < 0 ? "−" : "";
    return sign + Math.abs(n).toFixed(digits) + "%";
  }
  function aaiiBars(a) {
    if (!a || !a.ok) return "";
    const segs = [
      {k:"bull", lab:"看多", v:a.bull, avg:a.avg_bull},
      {k:"neut", lab:"中立", v:a.neutral, avg:a.avg_neutral},
      {k:"bear", lab:"看空", v:a.bear, avg:a.avg_bear}
    ];
    return `<div class="aaii-bars">${segs.map(s => `
      <div class="aaii-row">
        <div class="aaii-lab">${s.lab} ${s.v.toFixed(1)}%</div>
        <div class="aaii-track"><div class="aaii-fill ${s.k}" style="width:${Math.max(0, Math.min(100, s.v))}%"></div>
          ${s.avg!=null ? `<i class="aaii-avg" style="left:${Math.max(0, Math.min(100, s.avg))}%" title="歷史均值 ${s.avg.toFixed(1)}%"></i>` : ""}
        </div>
        <div class="aaii-avg-lab">均值 ${s.avg!=null ? s.avg.toFixed(1)+"%" : "—"}</div>
      </div>`).join("")}</div>`;
  }
  function retailCard(r) {
    if (!r || !r.ok) {
      return `<article class="macro-card retail-card" id="retail">
        <div class="macro-head"><div><h3>散戶資金</h3></div></div>
        <div class="missing">${(r && r.reason) || "散戶資金指標資料暫缺。"}</div>
        ${foldNote((r && (r.blurb || r.source)) || "", "資料說明")}
      </article>`;
    }
    const a = r.aaii || {};
    const f = r.finra || {};
    const i = r.ici || {};
    const c = r.cboe || {};
    const rm = r.rmfsl || {};
    const aaiiBlock = a.ok ? `
      <div class="retail-item">
        <div class="lbl">AAII 散戶情緒</div>
        <div class="val ${a.spread<0?"down":(a.spread>0?"up":"")}">多空差 ${fmtSpread(a.spread)}</div>
        <div class="hint">週截至 ${a.week_ending || "—"}　來源：${a.sourceShort || "AAII"}</div>
        ${aaiiBars(a)}
      </div>` : `<div class="retail-item"><div class="lbl">AAII 散戶情緒</div><div class="missing">${a.reason || "暫缺"}</div></div>`;
    const finraBlock = f.ok ? `
      <div class="retail-item">
        <div class="lbl">FINRA 融資餘額</div>
        <div class="val">${money(f.debit_trillion, 3)} 兆美元</div>
        <div class="hint">${f.month || "—"}　年增 ${fmtSignedPct(f.yoy,1)}　月變 ${fmtSignedPct(f.mom,1)}</div>
        <div class="hint">來源：${f.sourceShort || "FINRA"}　單位：百萬美元 ${Number(f.debit).toLocaleString("en-US")}</div>
      </div>` : `<div class="retail-item"><div class="lbl">FINRA 融資餘額</div><div class="missing">${f.reason || "暫缺"}</div></div>`;
    const iciBlock = i.ok ? `
      <div class="retail-item">
        <div class="lbl">ICI 貨幣基金</div>
        <div class="val">${money(i.total/1000, 3)} 兆美元</div>
        <div class="hint">週截至 ${i.week_ending || "—"}　週變 ${i.total_change==null?"—":((i.total_change>0?"＋":"−")+money(Math.abs(i.total_change),2)+" 十億美元")}</div>
        <div class="hint">零售 ${money(i.retail/1000, 3)} 兆（週變 ${i.retail_change==null?"—":((i.retail_change>0?"＋":"−")+money(Math.abs(i.retail_change),2)+" 十億")}）　來源：${i.sourceShort || "ICI"}</div>
      </div>` : `<div class="retail-item"><div class="lbl">ICI 貨幣基金</div><div class="missing">${i.reason || "暫缺"}</div></div>`;
    const cboeBlock = c.ok ? `
      <div class="retail-item">
        <div class="lbl">Cboe 權益賣權／買權比</div>
        <div class="val">${money(c.equity, 2)}</div>
        <div class="hint">日資料 ${c.date || "—"}　全部選擇權 ${c.total==null?"—":money(c.total,2)}　來源：${c.sourceShort || "Cboe"}</div>
        <div class="hint">${c.equity<1?"買權成交多於賣權（比值低於 1）":(c.equity>1?"賣權成交多於買權（比值高於 1）":"賣權與買權大致相當")}</div>
      </div>` : `<div class="retail-item"><div class="lbl">Cboe 權益賣權／買權比</div><div class="missing">${c.reason || "暫缺"}</div></div>`;
    const details = `
      <p>${r.blurb || ""}目前綜合讀法是「${r.read || "—"}」，只描述相對歷史均值的位置，不是交易指令。</p>
      ${a.ok ? `<p>AAII：看多 ${a.bull.toFixed(1)}%、中立 ${a.neutral.toFixed(1)}%、看空 ${a.bear.toFixed(1)}%；歷史均值為看多 ${a.avg_bull.toFixed(1)}%、中立 ${a.avg_neutral.toFixed(1)}%、看空 ${a.avg_bear.toFixed(1)}%。調查問的是未來六個月股市方向，結果通常於週四公布。來源：${a.source}</p>` : ""}
      ${f.ok ? `<p>FINRA：${f.month} 客戶證券保證金帳戶借方餘額 ${Number(f.debit).toLocaleString("en-US")} 百萬美元（約 ${money(f.debit_trillion,3)} 兆美元）。相對前一月 ${f.prev_month} 為 ${fmtSignedPct(f.mom,2)}，相對前年同月 ${f.yoy_month}（${Number(f.yoy_debit).toLocaleString("en-US")} 百萬美元）為 ${fmtSignedPct(f.yoy,2)}。現金帳戶可用餘額 ${Number(f.free_credit_cash).toLocaleString("en-US")}、保證金帳戶可用餘額 ${Number(f.free_credit_margin).toLocaleString("en-US")} 百萬美元。FINRA 通常於參考月次月第三週更新。來源：${f.source}</p>` : ""}
      ${i.ok ? `<p>ICI：週截至 ${i.week_ending}、於 ${i.released} 發布。貨幣基金總資產 ${money(i.total,2)} 十億美元，較前一週 ${money(i.total_prev,2)} 十億美元變動 ${i.total_change} 十億美元；零售 ${money(i.retail,2)} 十億美元（週變 ${i.retail_change}），法人 ${money(i.institutional,2)} 十億美元（週變 ${i.institutional_change}）。ICI 註明成分相加可能因四捨五入與總額不完全相等；資產變動主要由資金流驅動，可作淨申贖的近似。來源：${i.source}</p>` : ""}
      ${rm.ok ? `<p>對照（口徑不同）：FRED RMFSL 零售貨幣基金 ${rm.date} 為 ${money(rm.value,1)} 十億美元，年增 ${fmtSignedPct(rm.yoy,1)}（對 ${rm.yoy_date} 的 ${money(rm.yoy_value,1)} 十億美元）。${rm.note || ""}來源：${rm.source}</p>` : ""}
      ${c.ok ? `<p>Cboe：${c.date} 權益選擇權賣權／買權比 ${money(c.equity,2)}，全部選擇權 ${c.total==null?"—":money(c.total,2)}，指數選擇權 ${c.index==null?"—":money(c.index,2)}。這是選擇權成交量比，不是散戶下單本身。來源：${c.source}</p>` : ""}
      ${(r.missing && r.missing.length) ? `<p>未能列入：${r.missing.join("；")}。</p>` : "<p>Nasdaq 等散戶淨流入公開數列本輪未取得，故未列入。</p>"}
    `;
    return `<article class="macro-card retail-card" id="retail">
      <div class="macro-head">
        <div>
          <h3>散戶資金</h3>
          <p class="retail-read">${r.headline || r.read || ""}</p>
        </div>
      </div>
      <div class="retail-grid">
        ${aaiiBlock}${finraBlock}${iciBlock}${cboeBlock}
      </div>
      ${foldNote(details, "詳細")}
    </article>`;
  }


  function dollarCard(d) {
    if (!d || d.ok === false) {
      return `<article class="macro-card" id="dollar">
        <div class="macro-head"><div><h3>聯準會廣義美元指數</h3></div></div>
        <div class="missing">資料暫缺：${(d && d.reason) || "來源讀取失敗"}</div>
      </article>`;
    }
    const s20 = d.sma20Latest == null ? "—" : money(d.sma20Latest, 2);
    const s60 = d.sma60Latest == null ? "—" : money(d.sma60Latest, 2);
    const stat = `${money(d.latest, 2)}<div class="hint">美東 ${d.latestDate}　月線 ${s20}　季線 ${s60}　來源：${d.sourceShort}</div>`;
    return `<article class="macro-card" id="dollar">
      <div class="macro-head">
        <div>
          <h3>聯準會廣義美元指數（DTWEXBGS）</h3>
          <p class="macro-sub">這不是 ICE 美元指數 DXY</p>
        </div>
        <div class="macro-stat">${stat}</div>
      </div>
      <div class="chart-legend">
        <span><i class="sma20"></i>廣義美元指數</span>
        <span><i class="sma60"></i>月線 SMA20</span>
        <span><i class="press"></i>季線 SMA60</span>
      </div>
      <div class="chart-wrap" data-line="dollar"></div>
      ${foldNote(((d.blurb || "") + " " + (d.source || "")).trim(), "資料來源")}
    </article>`;
  }
  function dollarNasdaqCard(c) {
    if (!c || c.ok === false) {
      return `<article class="macro-card" id="dollar-nasdaq">
        <div class="macro-head"><div><h3>廣義美元指數 vs 那斯達克綜合指數</h3></div></div>
        <div class="missing">資料暫缺：${(c && c.reason) || "來源讀取失敗"}</div>
      </article>`;
    }
    const corr = c.corrDaily == null ? "—" : Number(c.corrDaily).toFixed(2);
    const corr60 = c.corr60Last == null ? "—" : Number(c.corr60Last).toFixed(2);
    const hi = c.nasdaqRebasedHigh && c.dollarRebasedHigh
      ? `　美元最高 ${money(c.dollarRebasedHigh.v,1)}（${c.dollarRebasedHigh.d}）／那斯達克最高 ${money(c.nasdaqRebasedHigh.v,1)}（${c.nasdaqRebasedHigh.d}）`
      : "";
    const stat = `日報酬相關 ${corr}<div class="hint">60 日滾動相關 ${corr60}（${c.corr60LastDate || "—"}）　起點 ${c.startDate}＝100　截至 ${c.endDate}${hi}　來源：${c.sourceShort}</div>`;
    return `<article class="macro-card" id="dollar-nasdaq">
      <div class="macro-head">
        <div>
          <h3>廣義美元指數 vs 那斯達克綜合指數</h3>
          <p class="macro-sub">自 2022-01-03 收盤＝100；不是 ICE DXY，也不是那斯達克 100</p>
        </div>
        <div class="macro-stat" style="font-size:24px">${stat}</div>
      </div>
      <div class="chart-legend">
        <span><i class="sma20"></i>廣義美元指數（DTWEXBGS）</span>
        <span><i class="sma60"></i>那斯達克綜合指數（NASDAQCOM）</span>
        <span><i class="press"></i>60 日滾動相關（右軸）</span>
      </div>
      <div class="chart-wrap" data-line="dollar-nasdaq"></div>
      ${foldNote(((c.blurb || "") + " " + (c.source || "")).trim(), "資料來源")}
    </article>`;
  }
  function macroHTML() {

    const m = MACRO;
    const vix = m.vix || {};
    const oil = m.oil || {};
    const fed = m.fed || {};
    const auc = m.auctions || {};
    const vixStat = vix.ok ? `${money(vix.latest, 2)}<div class="hint">美東 ${vix.latestDate}　來源：${vix.sourceShort}</div>` : "";
    const oilStat = oil.ok ? `WTI ${money(oil.wtiLatest, 2)}　Brent ${money(oil.brentLatest, 2)}<div class="hint">截至 ${oil.latestDate}（美元／桶）　來源：${oil.sourceShort}</div>` : "";
    const target = fed.ok ? `${fed.targetRange}<div class="hint">${fed.targetAsOf}</div>` : "";
    const table = (auc.ok && auc.latest && auc.latest.length)
      ? `<table class="auctions"><thead><tr><th>期限</th><th>標售日</th><th>得標利率</th><th>口徑</th><th>投標倍數</th></tr></thead><tbody>${
          auc.latest.map(r => `<tr><td>${r.tenor}</td><td>${r.auctionDate}</td><td>${r.rate==null?"—":money(r.rate,3)}%</td><td>${r.rateLabel}</td><td>${r.btc==null?"—":money(r.btc,2)}</td></tr>`).join("")
        }</tbody></table>`
      : "";
    const cnn = m.cnn || {};
    const fw = m.fedwatch || {};
    const gg = m.gauges || {};
    const cnnCmp = cnn.ok ? `<div class="cmp-row">
        ${cmpLine("前收", cnn.previous_close, null, "")}
        ${cmpLine("一週前", cnn.previous_1_week, null, "")}
        ${cmpLine("一月前", cnn.previous_1_month, null, "")}
        ${cmpLine("一年前", cnn.previous_1_year, null, "")}
      </div>` : "";
    const fwBlock = fw.ok ? `<p class="fw-range">現行目標區間 ${fw.targetRange}（截至 ${fw.targetAsOf}）</p>
      <div class="fw-grid">${(fw.meetings || []).map(mt => `
        <div class="fw-meet">
          <h4>${mt.name}</h4>
          <div class="fw-pills">
            <span class="pill hold">維持 ${money(mt.hold,1)}%</span>
            <span class="pill cut">降息 ${money(mt.cut,1)}%</span>
            <span class="pill hike">升息 ${money(mt.hike,1)}%</span>
          </div>
          <ul class="fw-dist">${(mt.dist||[]).map(d => `<li>${d.targetRange}　${d.tag}　${money(d.prob,1)}%</li>`).join("")}</ul>
          ${foldNote((mt.method || "") + "隱含目標中位 " + money(mt.impliedMid,3) + "%。", "口徑")}
        </div>`).join("")}</div>
      ${foldNote((fw.blurb || "") + " " + (fw.source || ""), "資料來源與方法")}` : `<div class="missing">${fw.reason || "升息押注機率資料暫缺。"} ${foldNote(fw.source || "", "資料來源")}</div>`;
    const vixG = gg.vix || {};
    const vixGauge = vixG.ok ? semiGauge({
      title: "VIX",
      score: vixG.latest,
      scoreFmt: money(vixG.latest, 2),
      min: 0, max: vixG.zoneMax || 80,
      zones: vixG.zones,
      caption: (vixG.latest >= 30 ? "恐慌" : vixG.latest >= 20 ? "警戒" : vixG.latest >= 15 ? "偏高" : "平靜") + "　美東 " + (vixG.latestDate || "")
    }) + rangeGauge(Object.assign({unit: ""}, vixG)) : "";
    return `
      <section class="macro-grid">
        ${cnnFngCard(cnn)}
        ${retailCard(m.retail || {})}
        <article class="macro-card" id="fedwatch">
          <div class="macro-head">
            <div>
              <h3>升降息押注機率</h3>
            </div>
          </div>
          ${fwBlock}
        </article>
        <article class="macro-card" id="vix">
          <div class="macro-head">
            <div>
              <h3>恐慌指數 VIX</h3>
            </div>
            <div class="macro-stat">${vix.ok ? vixStat : ""}</div>
          </div>
          ${missingBox(vix)}
          ${vixGauge}
          <div class="chart-wrap" data-line="vix"></div>
          ${foldNote(((vix.blurb || "") + " " + (vix.source || "") + " " + (vixG.source || "")).trim(), "資料來源")}
        </article>
        <article class="macro-card" id="dots">
          <div class="macro-head">
            <div>
              <h3>利率點陣圖</h3>
            </div>
            <div class="macro-stat">${fed.ok ? target : ""}</div>
          </div>
          ${missingBox(fed)}
          <div class="chart-wrap" data-dots="1"></div>
          ${foldNote(((fed.blurb || "") + " " + (fed.source || "")).trim(), "資料來源")}
        </article>
        <article class="macro-card" id="oil">
          <div class="macro-head">
            <div>
              <h3>油價（WTI、Brent）</h3>
            </div>
            <div class="macro-stat" style="font-size:24px">${oil.ok ? oilStat : ""}</div>
          </div>
          ${missingBox(oil)}
          <div class="dual-gauge">
            <div><h4>WTI</h4>${rangeGauge(Object.assign({unit: ""}, gg.wti || {}))}</div>
            <div><h4>Brent</h4>${rangeGauge(Object.assign({unit: ""}, gg.brent || {}))}</div>
          </div>
          <div class="chart-legend"><span><i class="sma20"></i>WTI</span><span><i class="sma60"></i>Brent</span></div>
          <div class="chart-wrap" data-line="oil"></div>
          ${foldNote(((oil.blurb || "") + " " + (oil.source || "") + " " + ((gg.wti||{}).source || "") + " " + ((gg.brent||{}).source || "")).trim(), "資料來源")}
        </article>
        ${dollarCard(m.dollar || {})}
        ${dollarNasdaqCard(m.dollarNasdaq || {})}
        <article class="macro-card" id="rates-gauge">
          <div class="macro-head"><div><h3>利率位置</h3></div></div>
          <div class="dual-gauge">
            <div><h4>10 年期公債（DGS10）</h4>${rangeGauge(Object.assign({unit: "%"}, gg.dgs10 || {}))}</div>
            <div><h4>有效聯邦基金利率（DFF）</h4>${rangeGauge(Object.assign({unit: "%"}, gg.dff || {}))}</div>
          </div>
          ${foldNote("以近 52 週高低衡量目前 10 年期公債殖利率與有效聯邦基金利率的位置。" + " " + ((gg.dgs10||{}).source || "") + " " + ((gg.dff||{}).source || ""), "資料來源")}
        </article>
        <article class="macro-card" id="auctions">
          <div class="macro-head">
            <div>
              <h3>美國國債拍賣利率</h3>
            </div>
          </div>
          ${missingBox(auc)}
          ${table}
          <div class="chart-legend" style="margin-top:12px">
            <span><i class="sma20"></i>13 週（投資利率）</span>
            <span><i class="sma60"></i>2 年</span>
            <span><i class="press"></i>10 年</span>
            <span>30 年（虛線）</span>
          </div>
          <div class="chart-wrap" data-line="auctions"></div>
          ${foldNote(((auc.blurb || "") + " " + (auc.source || "")).trim(), "資料來源")}
        </article>
      </section>`;
  }

  function mountCharts() {
    charts.length = 0;
    document.querySelectorAll("[data-chart]").forEach(el => {
      const tk = el.getAttribute("data-chart");
      const s = STOCKS.find(x => x.ticker === tk);
      if (!s || !s.bars || !s.bars.length) {
        el.innerHTML = `<div class="missing">線圖資料暫缺${s && s.chartReason ? "：" + s.chartReason : ""}</div>`;
        return;
      }
      charts.push(drawCandles(el, s));
    });
    const vixEl = document.querySelector('[data-line="vix"]');
    if (vixEl && MACRO.vix && MACRO.vix.ok) charts.push(drawLines(vixEl, [{name:"VIX", color:null, points:MACRO.vix.points}], {yLabel:"VIX"}));
    const oilEl = document.querySelector('[data-line="oil"]');
    if (oilEl && MACRO.oil && MACRO.oil.ok) {
      charts.push(drawLines(oilEl, [
        {name:"WTI", color:null, points:MACRO.oil.wti},
        {name:"Brent", color:"var60", points:MACRO.oil.brent}
      ], {yLabel:"美元／桶"}));
    }
    const dollarEl = document.querySelector('[data-line="dollar"]');
    if (dollarEl && MACRO.dollar && MACRO.dollar.ok) {
      charts.push(drawLines(dollarEl, [
        {name:"廣義美元指數", color:null, points:MACRO.dollar.points},
        {name:"月線 SMA20", color:"var60", points:MACRO.dollar.sma20, dashed:true},
        {name:"季線 SMA60", color:"press", points:MACRO.dollar.sma60, dashed:true}
      ], {yLabel:"指數"}));
    }
    const dnEl = document.querySelector('[data-line="dollar-nasdaq"]');
    if (dnEl && MACRO.dollarNasdaq && MACRO.dollarNasdaq.ok) {
      charts.push(drawLines(dnEl, [
        {name:"廣義美元指數", color:null, points:MACRO.dollarNasdaq.dollarRebased},
        {name:"那斯達克綜合指數", color:"var60", points:MACRO.dollarNasdaq.nasdaqRebased},
        {name:"60日滾動相關", color:"press", points:MACRO.dollarNasdaq.corr60, dashed:true, axis:"right"}
      ], {yLabel:"起始日＝100", yLabelRight:"相關係數", dualRight:true, rightMin:-1, rightMax:1}));
    }
    const aucEl = document.querySelector('[data-line="auctions"]');
    if (aucEl && MACRO.auctions && MACRO.auctions.ok) {
      charts.push(drawLines(aucEl, MACRO.auctions.series, {yLabel:"%", isPct:true}));
    }
    const dotEl = document.querySelector("[data-dots]");
    if (dotEl && MACRO.fed && MACRO.fed.ok) drawDotPlot(dotEl, MACRO.fed);
  }

  function svgEl(name, attrs) {
    const n = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [k,v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  }

  function drawCandles(el, series) {
    el.innerHTML = "";
    const svg = svgEl("svg", {class:"chart-svg", viewBox:"0 0 800 260", preserveAspectRatio:"none"});
    const tip = document.createElement("div");
    tip.className = "chart-tip";
    el.append(svg, tip);
    const bars = series.bars;
    const press = series.pressure || [];
    const state = { svg, tip, bars, press, el };
    const ro = new ResizeObserver(() => paintCandles(state));
    ro.observe(el);
    paintCandles(state);
    return { destroy() { ro.disconnect(); } };
  }

  function paintCandles(state) {
    const { svg, tip, bars, press, el } = state;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const W = 800, H = 260;
    const pad = {l: 56, r: 68, t: 12, mid: 168, b: 24};
    const pH = pad.mid - pad.t;
    const vH = H - pad.mid - pad.b - 8;
    const n = bars.length;
    const xs = i => pad.l + (i + 0.5) * (W - pad.l - pad.r) / n;
    const slot = (W - pad.l - pad.r) / n;
    const lastBar = bars[bars.length - 1] || {};
    const maLvls = [];
    if (lastBar.s20 != null && lastBar.c != null && lastBar.c < lastBar.s20) maLvls.push(lastBar.s20);
    if (lastBar.s60 != null && lastBar.c != null && lastBar.c < lastBar.s60) maLvls.push(lastBar.s60);
    const hi = Math.max(...bars.map(b => b.h), ...press.map(p => p.price), ...maLvls);
    const lo = Math.min(...bars.map(b => b.l));
    const padY = (hi - lo) * 0.06 || 1;
    const yMin = lo - padY, yMax = hi + padY;
    const yP = v => pad.t + (yMax - v) / (yMax - yMin) * pH;
    const vmax = Math.max(...bars.map(b => b.v), 1);
    const yV = v => pad.mid + 8 + (1 - v / vmax) * vH;
    const upC = cssVar("--up", "#0b6a4a");
    const downC = cssVar("--down", "#9b1c2c");
    const gridC = cssVar("--line", "#ccc");
    const faint = cssVar("--faint", "#888");
    const accent = cssVar("--accent", "#0f6e68");
    const sma60C = cssVar("--mid", "#8a5a00");
    const pressC = getComputedStyle(document.documentElement).getPropertyValue("--text").includes("e9") ? "#ff9b6b" : "#c45c26";
    const textC = cssVar("--text", "#111");

    // grid
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const val = yMax - (yMax - yMin) * i / ticks;
      const y = yP(val);
      svg.appendChild(svgEl("line", {x1:pad.l, x2:W-pad.r, y1:y, y2:y, stroke:gridC, "stroke-width":1}));
      const lab = svgEl("text", {x:4, y:y+3, fill:faint, "font-size":"12", "font-family":"ui-sans-serif,system-ui,sans-serif"});
      lab.textContent = money(val, val >= 100 ? 0 : 2);
      svg.appendChild(lab);
    }
    // volume
    bars.forEach((b,i) => {
      const x = xs(i);
      const bw = Math.max(0.6, slot * 0.7);
      const y = yV(b.v);
      const rect = svgEl("rect", {x:x-bw/2, y, width:bw, height:Math.max(0.5, (pad.mid+8+vH)-y), fill: b.c>=b.o ? upC : downC, opacity:"0.35"});
      svg.appendChild(rect);
    });
    // candles
    bars.forEach((b,i) => {
      const x = xs(i);
      const color = b.c >= b.o ? upC : downC;
      const bw = Math.max(0.7, slot * 0.62);
      svg.appendChild(svgEl("line", {x1:x, x2:x, y1:yP(b.h), y2:yP(b.l), stroke:color, "stroke-width":1}));
      const y1 = yP(Math.max(b.o,b.c)), y2 = yP(Math.min(b.o,b.c));
      svg.appendChild(svgEl("rect", {x:x-bw/2, y:y1, width:bw, height:Math.max(1, y2-y1), fill:color}));
    });
    function poly(key, color) {
      const pts = [];
      bars.forEach((b,i) => { if (b[key] != null) pts.push(`${xs(i).toFixed(2)},${yP(b[key]).toFixed(2)}`); });
      if (pts.length >= 2) svg.appendChild(svgEl("polyline", {points:pts.join(" "), fill:"none", stroke:color, "stroke-width":1.6, "stroke-linejoin":"round"}));
    }
    poly("s20", accent);
    poly("s60", sma60C);
    // Right-edge labels for 月線／季線壓力 when the close is below that average.
    const maLabs = [];
    if (lastBar.s20 != null && lastBar.c != null && lastBar.c < lastBar.s20) {
      maLabs.push({ y: yP(lastBar.s20), text: "月 " + money(lastBar.s20, 2), fill: accent });
    }
    if (lastBar.s60 != null && lastBar.c != null && lastBar.c < lastBar.s60) {
      maLabs.push({ y: yP(lastBar.s60), text: "季 " + money(lastBar.s60, 2), fill: sma60C });
    }
    if (maLabs.length === 2 && Math.abs(maLabs[0].y - maLabs[1].y) < 12) {
      if (maLabs[0].y <= maLabs[1].y) maLabs[1].y = maLabs[0].y + 12;
      else maLabs[0].y = maLabs[1].y + 12;
    }
    maLabs.forEach(lab => {
      const el = svgEl("text", {x:W-pad.r+4, y:lab.y+3, fill:lab.fill, "font-size":"11", "font-family":"ui-sans-serif,system-ui,sans-serif"});
      el.textContent = lab.text;
      svg.appendChild(el);
    });
    press.forEach(p => {
      const y = yP(p.price);
      svg.appendChild(svgEl("line", {x1:pad.l, x2:W-pad.r, y1:y, y2:y, stroke:pressC, "stroke-width":1.2, "stroke-dasharray":"4 3"}));
      const lab = svgEl("text", {x:W-pad.r+4, y:y+3, fill:pressC, "font-size":"11", "font-family":"ui-sans-serif,system-ui,sans-serif"});
      lab.textContent = money(p.price, 2);
      svg.appendChild(lab);
    });
    // x labels
    [0, Math.floor((n-1)/2), n-1].forEach(i => {
      const lab = svgEl("text", {x:xs(i), y:H-4, fill:faint, "font-size":"12", "text-anchor":"middle", "font-family":"ui-sans-serif,system-ui,sans-serif"});
      lab.textContent = (bars[i].d || "").slice(2);
      svg.appendChild(lab);
    });
    // hover layer
    const cov = svgEl("rect", {x:pad.l, y:pad.t, width:W-pad.l-pad.r, height:H-pad.t-pad.b, fill:"transparent"});
    svg.appendChild(cov);
    const cursor = svgEl("line", {x1:0,x2:0,y1:pad.t,y2:pad.mid+8+vH, stroke:textC, "stroke-opacity":"0.25", "stroke-width":1, visibility:"hidden"});
    svg.appendChild(cursor);
    function at(ev) {
      const rec = svg.getBoundingClientRect();
      const px = (ev.clientX - rec.left) / rec.width * W;
      let i = Math.round((px - pad.l) / ((W-pad.l-pad.r)/n) - 0.5);
      i = Math.max(0, Math.min(n-1, i));
      return i;
    }
    function show(i, ev) {
      const b = bars[i];
      cursor.setAttribute("x1", xs(i)); cursor.setAttribute("x2", xs(i)); cursor.setAttribute("visibility","visible");
      tip.classList.add("show");
      tip.innerHTML = `<strong>${b.d}</strong><br>開 ${money(b.o,2)}　高 ${money(b.h,2)}<br>低 ${money(b.l,2)}　收 ${money(b.c,2)}<br>量 ${fmtVol(b.v)}<br>月線 ${b.s20==null?"—":money(b.s20,2)}　季線 ${b.s60==null?"—":money(b.s60,2)}`;
      const rec = el.getBoundingClientRect();
      const left = ev.clientX - rec.left + 12;
      const top = ev.clientY - rec.top + 12;
      tip.style.left = Math.min(left, rec.width - tip.offsetWidth - 8) + "px";
      tip.style.top = Math.min(top, rec.height - tip.offsetHeight - 8) + "px";
    }
    cov.addEventListener("mousemove", ev => show(at(ev), ev));
    cov.addEventListener("mouseleave", () => { tip.classList.remove("show"); cursor.setAttribute("visibility","hidden"); });
  }

  function drawLines(el, seriesList, opts) {
    el.innerHTML = "";
    const svg = svgEl("svg", {class:"line-svg", viewBox:"0 0 800 240", preserveAspectRatio:"none"});
    const tip = document.createElement("div");
    tip.className = "chart-tip";
    el.append(svg, tip);
    const state = { svg, tip, el, seriesList, opts: opts || {} };
    const ro = new ResizeObserver(() => paintLines(state));
    ro.observe(el);
    paintLines(state);
    return { destroy() { ro.disconnect(); } };
  }

  function paintLines(state) {
    const { svg, tip, el, seriesList, opts } = state;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const dual = !!(opts && opts.dualRight);
    const W=800, H=240, pad={l:58,r: dual ? 44 : 16,t:12,b:28};
    const leftSeries = seriesList.filter(s => s.axis !== "right");
    const rightSeries = seriesList.filter(s => s.axis === "right");
    const all = [];
    seriesList.forEach(s => (s.points||[]).forEach(p => { if (p.v != null) all.push(p); }));
    if (!all.length) return;
    const dates = [...new Set(all.map(p => p.d))].sort();
    const xmap = new Map(dates.map((d,i) => [d, i]));
    const xs = d => pad.l + xmap.get(d) * (W-pad.l-pad.r) / Math.max(1, dates.length-1);
    const leftVals = [];
    leftSeries.forEach(s => (s.points||[]).forEach(p => { if (p.v != null) leftVals.push(p.v); }));
    const scaleVals = leftVals.length ? leftVals : all.map(p => p.v);
    const lo = Math.min(...scaleVals), hi = Math.max(...scaleVals);
    const padY = (hi-lo)*0.08 || 1;
    const yMin=lo-padY, yMax=hi+padY;
    const yv = v => pad.t + (yMax-v)/(yMax-yMin)*(H-pad.t-pad.b);
    const rMin = (opts && opts.rightMin != null) ? opts.rightMin : -1;
    const rMax = (opts && opts.rightMax != null) ? opts.rightMax : 1;
    const yvr = v => pad.t + (rMax-v)/(rMax-rMin)*(H-pad.t-pad.b);
    const gridC = cssVar("--line","#ccc");
    const faint = cssVar("--faint","#888");
    const accent = cssVar("--accent","#0f6e68");
    const c60 = cssVar("--mid","#8a5a00");
    const pressC = getComputedStyle(document.documentElement).getPropertyValue("--text").includes("e9") ? "#ff9b6b" : "#c45c26";
    const colors = [accent, c60, pressC, faint];
    for (let i=0;i<=4;i++){
      const val = yMax - (yMax-yMin)*i/4;
      const y=yv(val);
      svg.appendChild(svgEl("line",{x1:pad.l,x2:W-pad.r,y1:y,y2:y,stroke:gridC,"stroke-width":1}));
      const lab=svgEl("text",{x:4,y:y+3,fill:faint,"font-size":"12","font-family":"ui-sans-serif,system-ui,sans-serif"});
      lab.textContent = opts.isPct ? val.toFixed(2) : money(val, val>=100?0:2);
      svg.appendChild(lab);
      if (dual) {
        const rv = rMax - (rMax-rMin)*i/4;
        const rlab=svgEl("text",{x:W-pad.r+6,y:y+3,fill:faint,"font-size":"11","font-family":"ui-sans-serif,system-ui,sans-serif"});
        rlab.textContent = rv.toFixed(1);
        svg.appendChild(rlab);
      }
    }
    if (dual) {
      const z = yvr(0);
      svg.appendChild(svgEl("line",{x1:pad.l,x2:W-pad.r,y1:z,y2:z,stroke:pressC,"stroke-width":1,"stroke-dasharray":"2 3","stroke-opacity":"0.5"}));
    }
    seriesList.forEach((s, si) => {
      const color = s.color === "var60" ? c60 : s.color === "press" ? pressC : (s.color || colors[si % colors.length]);
      const yfn = (s.axis === "right") ? yvr : yv;
      const pts = (s.points||[]).filter(p => p.v!=null).map(p => `${xs(p.d).toFixed(2)},${yfn(p.v).toFixed(2)}`);
      if (pts.length>=2) {
        const attrs = {points:pts.join(" "), fill:"none", stroke:color, "stroke-width":1.7, "stroke-linejoin":"round"};
        if (s.dashed) attrs["stroke-dasharray"] = "5 3";
        svg.appendChild(svgEl("polyline", attrs));
      }
    });
    (function dateTicks(dates) {
      if (dates.length < 3) return dates.map((_, i) => i);
      const y0 = Number(dates[0].slice(0, 4));
      const y1 = Number(dates[dates.length - 1].slice(0, 4));
      if (y1 - y0 < 2 || dates.length < 200) {
        return [0, Math.floor((dates.length - 1) / 2), dates.length - 1];
      }
      const idxs = [0];
      for (let year = y0 + 1; year <= y1; year++) {
        const target = year + "-01-01";
        const i = dates.findIndex(d => d >= target);
        if (i < 0) break;
        if (i !== idxs[idxs.length - 1] && (dates.length - 1 - i) / Math.max(1, dates.length - 1) >= 0.06) idxs.push(i);
      }
      if (idxs[idxs.length - 1] !== dates.length - 1) idxs.push(dates.length - 1);
      return idxs;
    })(dates).forEach(i => {
      const lab=svgEl("text",{x:xs(dates[i]),y:H-4,fill:faint,"font-size":"12","text-anchor":"middle","font-family":"ui-sans-serif,system-ui,sans-serif"});
      lab.textContent = dates[i].slice(2);
      svg.appendChild(lab);
    });
    const cov=svgEl("rect",{x:pad.l,y:pad.t,width:W-pad.l-pad.r,height:H-pad.t-pad.b,fill:"transparent"});
    svg.appendChild(cov);
    cov.addEventListener("mousemove", ev => {
      const rec=svg.getBoundingClientRect();
      const px=(ev.clientX-rec.left)/rec.width*W;
      let i=Math.round((px-pad.l)/((W-pad.l-pad.r)/Math.max(1,dates.length-1)));
      i=Math.max(0,Math.min(dates.length-1,i));
      const d=dates[i];
      const rows=seriesList.map(s => {
        const pt=(s.points||[]).find(p=>p.d===d);
        return `${s.name}：${pt&&pt.v!=null?(opts.isPct?pt.v.toFixed(3)+"%":money(pt.v,2)):"—"}`;
      });
      tip.classList.add("show");
      tip.innerHTML = `<strong>${d}</strong><br>${rows.join("<br>")}`;
      const box=el.getBoundingClientRect();
      tip.style.left = Math.min(ev.clientX-box.left+12, box.width-tip.offsetWidth-8)+"px";
      tip.style.top = Math.min(ev.clientY-box.top+12, box.height-tip.offsetHeight-8)+"px";
    });
    cov.addEventListener("mouseleave", () => tip.classList.remove("show"));
  }

  function drawDotPlot(el, fed) {
    el.innerHTML = "";
    const svg = svgEl("svg", {class:"dot-svg", viewBox:"0 0 800 360"});
    el.appendChild(svg);
    const W=800,H=360,pad={l:58,r:20,t:32,b:40};
    const years = fed.years || ["2026","2027","2028","2029","Longer run"];
    const counts = fed.counts || {};
    const levels = Object.keys(counts).map(Number).sort((a,b)=>b-a);
    const yMin=2.6, yMax=4.6;
    const yv = v => pad.t + (yMax-v)/(yMax-yMin)*(H-pad.t-pad.b);
    const cx = i => pad.l + (i+0.5)*(W-pad.l-pad.r)/years.length;
    const gridC=cssVar("--line","#ccc"), faint=cssVar("--faint","#888");
    const accent=cssVar("--accent","#0f6e68"), textC=cssVar("--text","#111");
    const mid=cssVar("--mid","#8a5a00");
    // current target band
    if (fed.targetLow != null && fed.targetHigh != null) {
      const y1=yv(fed.targetHigh), y2=yv(fed.targetLow);
      svg.appendChild(svgEl("rect",{x:pad.l,y:y1,width:W-pad.l-pad.r,height:Math.max(1,y2-y1),fill:accent,opacity:"0.12"}));
    }
    for (let v=2.75; v<=4.5+1e-9; v+=0.25) {
      const y=yv(v);
      svg.appendChild(svgEl("line",{x1:pad.l,x2:W-pad.r,y1:y,y2:y,stroke:gridC,"stroke-width":1}));
      const lab=svgEl("text",{x:8,y:y+3,fill:faint,"font-size":"12","font-family":"ui-sans-serif,system-ui,sans-serif"});
      lab.textContent=v.toFixed(2);
      svg.appendChild(lab);
    }
    years.forEach((yr, yi) => {
      const lab=svgEl("text",{x:cx(yi),y:H-10,fill:textC,"font-size":"13","text-anchor":"middle","font-weight":"650","font-family":"ui-sans-serif,system-ui,sans-serif"});
      lab.textContent = yr === "Longer run" ? "較長期" : yr;
      svg.appendChild(lab);
    });
    years.forEach((yr, yi) => {
      levels.forEach(lv => {
        const key = lv.toFixed(3);
        const n = (counts[key] || [])[yi] || 0;
        const gap=9;
        const start = cx(yi) - (n-1)*gap/2;
        for (let k=0;k<n;k++){
          svg.appendChild(svgEl("circle",{cx:start+k*gap, cy:yv(lv), r:5, fill:accent, stroke:textC, "stroke-width":0.4}));
        }
      });
      if (fed.medians && fed.medians[yr] != null) {
        const y=yv(fed.medians[yr]);
        svg.appendChild(svgEl("rect",{x:cx(yi)-7,y:y-7,width:14,height:14,fill:mid,transform:`rotate(45 ${cx(yi)} ${y})`}));
      }
    });
    const lg=svgEl("text",{x:pad.l,y:16,fill:faint,"font-size":"13","font-family":"ui-sans-serif,system-ui,sans-serif"});
    lg.textContent="圓點＝個別委員預估（四捨五入至 1/8 個百分點）；菱形＝表 1 中位數；色帶＝現行目標區間";
    svg.appendChild(lg);
  }

  function render() {
    const cat = CATS.find(c => c.id === current);
    titleEl.textContent = cat.name;
    subEl.textContent = cat.blurb;
    const stampEl = document.getElementById("dataStamp");
    if (stampEl) stampEl.textContent = (META && META.priceStamp) || "";
    if (current === "macro") {
      extraEl.innerHTML = "";
      gridEl.className = "";
      gridEl.innerHTML = macroHTML();
    } else {
      const list = current === "all" ? STOCKS : STOCKS.filter(s => s.cat === current);
      extraEl.innerHTML = summaryTable(list);
      bindJumps(extraEl);
      gridEl.className = "grid";
      gridEl.innerHTML = list.length ? list.map(cardHTML).join("") : `<p class="empty">此分類目前沒有股票。</p>`;
    }
    renderNav();
    mountCharts();
  }

  const sidebarEl = document.getElementById("sidebar");
  const menuBtn = document.getElementById("menuToggle");
  function setNavOpen(open) {
    if (!sidebarEl || !menuBtn) return;
    sidebarEl.classList.toggle("nav-open", open);
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (menuBtn) {
    menuBtn.addEventListener("click", () => {
      setNavOpen(!(sidebarEl && sidebarEl.classList.contains("nav-open")));
    });
  }
  function googleAskUrl(q) {
    const t = (q || "").trim();
    return t
      ? "https://www.google.com/search?udm=50&q=" + encodeURIComponent(t)
      : "https://www.google.com/search?udm=50";
  }
  function openInNewTab(url) {
    const win = window.open(url, "_blank", "noopener");
    if (win) return;
    const a = document.createElement("a");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  const ASK_HIST_KEY = "watchlist-ask-history";
  const ASK_HIST_MAX = 50;
  function taipeiStamp() {
    try {
      const parts = new Intl.DateTimeFormat("sv-SE", {
        timeZone: "Asia/Taipei",
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        hour12: false
      }).formatToParts(new Date());
      const g = typ => (parts.find(p => p.type === typ) || {}).value;
      return g("year") + "-" + g("month") + "-" + g("day") + "T" + g("hour") + ":" + g("minute") + ":" + g("second") + "+08:00";
    } catch (e) {
      return new Date().toISOString();
    }
  }
  function formatTaipei(ts) {
    const m = String(ts || "").match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    if (m) return Number(m[2]) + "/" + Number(m[3]) + " " + m[4] + ":" + m[5];
    return ts || "";
  }
  function loadAskHistory() {
    try {
      const raw = localStorage.getItem(ASK_HIST_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.filter(x => x && typeof x.q === "string") : [];
    } catch (e) { return []; }
  }
  function saveAskHistory(arr) {
    try { localStorage.setItem(ASK_HIST_KEY, JSON.stringify(arr.slice(0, ASK_HIST_MAX))); } catch (e) {}
  }
  function addAskHistory(q) {
    const text = (q || "").trim();
    if (!text) return;
    const items = loadAskHistory();
    items.unshift({ q: text, t: taipeiStamp() });
    saveAskHistory(items);
  }
  function renderAskHistory() {
    const items = loadAskHistory();
    const list = document.getElementById("askHistoryList");
    const empty = document.getElementById("askHistoryEmpty");
    const clearBtn = document.getElementById("askHistClear");
    if (!list) return;
    list.innerHTML = items.map((it, i) =>
      "<li>" +
        "<button type=\"button\" class=\"ask-hist-q\" data-i=\"" + i + "\">" +
          "<span class=\"q\">" + esc(it.q) + "</span>" +
          "<span class=\"t\">" + esc(formatTaipei(it.t)) + "</span>" +
        "</button>" +
        "<button type=\"button\" class=\"ask-hist-del\" data-i=\"" + i + "\" aria-label=\"刪除這筆紀錄\">×</button>" +
      "</li>"
    ).join("");
    if (empty) empty.hidden = items.length > 0;
    if (clearBtn) clearBtn.hidden = items.length === 0;
  }
  document.querySelectorAll("form.ask-form").forEach(form => {
    form.addEventListener("submit", ev => {
      ev.preventDefault();
      const input = form.querySelector(".ask-input");
      const q = ((input && input.value) || "").trim();
      if (q) {
        addAskHistory(q);
        renderAskHistory();
      }
      openInNewTab(googleAskUrl(q));
    });
  });
  const histPanel = document.getElementById("askHistory");
  const histToggle = document.getElementById("askHistToggle");
  if (histToggle && histPanel) {
    histToggle.addEventListener("click", () => {
      const open = histPanel.hasAttribute("hidden");
      if (open) histPanel.removeAttribute("hidden");
      else histPanel.setAttribute("hidden", "");
      histToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  const histList = document.getElementById("askHistoryList");
  if (histList) {
    histList.addEventListener("click", ev => {
      const del = ev.target.closest(".ask-hist-del");
      if (del) {
        ev.preventDefault();
        const items = loadAskHistory();
        const i = Number(del.getAttribute("data-i"));
        if (i >= 0 && i < items.length) {
          items.splice(i, 1);
          saveAskHistory(items);
          renderAskHistory();
        }
        return;
      }
      const qbtn = ev.target.closest(".ask-hist-q");
      if (qbtn) {
        const items = loadAskHistory();
        const it = items[Number(qbtn.getAttribute("data-i"))];
        if (it && it.q) openInNewTab(googleAskUrl(it.q));
      }
    });
  }
  const histClear = document.getElementById("askHistClear");
  if (histClear) {
    histClear.addEventListener("click", () => {
      if (!loadAskHistory().length) return;
      if (!confirm("確定清除全部搜尋紀錄？")) return;
      saveAskHistory([]);
      renderAskHistory();
    });
  }
  renderAskHistory();
  navEl.addEventListener("click", e => {
    const btn = e.target.closest("[data-id]");
    if (!btn) return;
    current = btn.dataset.id;
    setNavOpen(false);
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  const root = document.documentElement;
  const themeBtn = document.getElementById("themeBtn");
  function applyTheme(t) {
    root.dataset.theme = t;
    try { localStorage.setItem("watchlist-theme", t); } catch (e) {}
    themeBtn.textContent = t === "dark" ? "切換淺色" : "切換深色";
    mountCharts();
  }
  const params = new URLSearchParams(location.search);
  const qTheme = params.get("theme") === "dark" || params.get("theme") === "light" ? params.get("theme") : null;
  const saved = (() => { try { return localStorage.getItem("watchlist-theme"); } catch (e) { return null; } })();
  const preferDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(qTheme || saved || (preferDark ? "dark" : "light"));
  themeBtn.addEventListener("click", () => applyTheme(root.dataset.theme === "dark" ? "light" : "dark"));
  if (params.get("cat") && CATS.some(c => c.id === params.get("cat"))) current = params.get("cat");
  const hashTk = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (hashTk && STOCKS.some(s => s.ticker === hashTk)) {
    const found = STOCKS.find(s => s.ticker === hashTk);
    if (found && (!params.get("cat") || params.get("cat") === "all")) current = params.get("cat") || found.cat;
  }

  render();
  if (hashTk) {
    const el = document.getElementById(hashTk);
    if (el) setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }
})();
