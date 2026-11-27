#!/usr/bin/env python3
"""Render reviewed research memos to styled static HTML. No raw index files."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCREEN = Path("/workspace/cross-sector-screen")
OUT = ROOT / "reports"

REPORTS = [
    {
        "id": "ai-disruption-20261123",
        "src": Path("/workspace/ai-disruption-20261123/report.md"),
        "tickers": Path("/workspace/ai-disruption-20261123/tickers.json"),
        "title": "AI 時代金流轉移：哪些產業被拿走蛋糕、誰會受益",
        "date": "2026-11-23",
        "nav": "AI 時代產業金流轉移",
        "blurb": "已審（2026-11-23）。14 個產業排序與受益者。條件式研究，不是交易指令。",
    },
    {
        "id": "agentic-commerce-20261123",
        "src": Path("/workspace/agentic-commerce-20261123/report.md"),
        "title": "Agent 作為主要消費端口：誰是最終受益者",
        "date": "2026-11-23",
        "nav": "Agent 消費端口的受益者",
        "blurb": "已審（2026-11-23）。獨家供給與履約網絡較可能留住價值。條件式研究，不是交易指令。",
    },
    {
        "id": "spacex-tsla-cashflow-20261117",
        "src": SCREEN / "spacex-tsla-cashflow-20261117.md",
        "title": "SpaceX × Tesla：營運現金流能否支應資料中心與 Terafab 資本支出",
        "date": "2026-11-17",
        "nav": "SpaceX／Tesla 現金流與 Terafab",
        "blurb": "已審（2026-11-17）。合併未成案；SPCX 觀望。TSLA 僅研究、未加入看板。",
    },
    {
        "id": "ai-apps-shop-20261117",
        "src": SCREEN / "ai-apps-shop-20261117.md",
        "title": "AI 應用組：SHOP＋應用層初選 12 檔",
        "date": "2026-11-17",
        "nav": "AI 應用：SHOP 與初選 12 檔",
        "blurb": "已審（2026-11-17）。SHOP 觀望；初選 12 檔未加入看板卡片。",
    },
    {
        "id": "hyperscalers-4-20261117",
        "src": SCREEN / "hyperscalers-4-20261117.md",
        "title": "四大雲加入看板：MSFT、AMZN、META、ORCL",
        "date": "2026-11-17",
        "nav": "四大雲：MSFT、AMZN、META、ORCL",
        "blurb": "已審（2026-11-17）。四檔皆觀望。",
    },
    {
        "id": "midterm-election-20261115",
        "src": SCREEN / "midterm-election-20261115.md",
        "title": "美國期中選舉後股市表現（1950–2022）與 2026 對照",
        "date": "2026-11-15",
        "nav": "期中選舉後一年報酬",
        "blurb": "已審（2026-11-15）。價格指數，不是總報酬。",
    },
    {
        "id": "midterm-entry-timing-20261116",
        "src": SCREEN / "midterm-entry-timing-20261116.md",
        "title": "期中選舉後「第幾個交易日進場」的歷史檢視（1950–2022）與 2026 對照",
        "date": "2026-11-16",
        "nav": "期中選後進場時點",
        "blurb": "已審（2026-11-16）。沒有固定最佳進場日。",
    },
]

DISCLAIMER = (
    "僅供陳煒川本人自用。研究用途，不是下單指令，不承諾報酬。"
    "文中價格與報酬若未另註，為拆股調整價格指數，不是官方收盤，也不是含息總報酬。"
    "若引用 Massive 日線，屬延遲／非官方報價，不是交易所官方收盤。"
    "本頁只公開已審報告正文，不含原始指數數列或內部計算檔。"
)


def _protect_code(text: str):
    bits = []
    def repl(m):
        bits.append(m.group(1))
        return f"\x00C{len(bits)-1}\x00"
    return re.sub(r"`([^`]+)`", repl, text), bits


def _extract_md_links(text: str):
    """Split markdown links, allowing parentheses inside the URL."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        j = text.find("[", i)
        if j < 0:
            out.append(("t", text[i:]))
            break
        out.append(("t", text[i:j]))
        k = text.find("]", j + 1)
        if k < 0 or k + 1 >= n or text[k + 1] != "(":
            out.append(("t", text[j:j + 1]))
            i = j + 1
            continue
        depth = 1
        p = k + 2
        while p < n and depth:
            if text[p] == "(":
                depth += 1
            elif text[p] == ")":
                depth -= 1
            p += 1
        if depth != 0:
            out.append(("t", text[j:j + 1]))
            i = j + 1
            continue
        out.append(("a", text[j + 1:k], text[k + 2:p - 1]))
        i = p
    return out


def _inline(text: str) -> str:
    text, codes = _protect_code(text)
    links = []
    rebuilt = []
    for part in _extract_md_links(text):
        if part[0] == "t":
            rebuilt.append(part[1])
        else:
            links.append((part[1], part[2]))
            rebuilt.append(f"\x00L{len(links)-1}\x00")
    text = "".join(rebuilt)
    # bold then italic
    def esc_keep(s):
        return html.escape(s, quote=False)
    parts = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text)
    out = []
    for p in parts:
        if p.startswith("**") and p.endswith("**") and len(p) >= 4:
            out.append("<strong>" + esc_keep(p[2:-2]) + "</strong>")
        elif p.startswith("*") and p.endswith("*") and len(p) >= 2 and not p.startswith("**"):
            out.append("<em>" + esc_keep(p[1:-1]) + "</em>")
        else:
            out.append(esc_keep(p))
    text = "".join(out)
    for i, (label, url) in enumerate(links):
        safe = html.escape(url, quote=True)
        # only http(s) links; never turn local paths into hrefs
        if url.startswith("http://") or url.startswith("https://"):
            repl = f'<a href="{safe}" rel="noopener noreferrer" target="_blank">{html.escape(label)}</a>'
        else:
            repl = html.escape(label)
        text = text.replace(f"\x00L{i}\x00", repl)
    for i, code in enumerate(codes):
        text = text.replace(f"\x00C{i}\x00", f"<code>{html.escape(code)}</code>")
    return text


def _heading_id(title: str, used: dict) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", title).strip("-").lower() or "section"
    n = used.get(base, 0)
    used[base] = n + 1
    return base if n == 0 else f"{base}-{n}"


def _list_level(indent: str) -> int:
    n = len(indent.replace("\t", "  "))
    if n <= 1:
        return 0
    if n <= 3:
        return 1
    return 2



def tickers_appendix_md(path: Path) -> str:
    """Compact ticker table from reviewed tickers.json. Not a raw-file dump."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("tickers") or []
    meta = data.get("meta") or {}
    # detect columns
    sample = rows[0] if rows else {}
    group_key = "group" if "group" in sample else ("layer" if "layer" in sample else None)
    cols = ["代碼"]
    if group_key:
        cols.append("角色／位置" if group_key == "group" else "價值鏈層")
    if "category" in sample:
        cols.append("類別")
    cols += ["看板", "判斷"]

    def cell(s: str) -> str:
        s = "" if s is None else str(s)
        return s.replace("|", "／").replace("\n", " ").strip()

    lines = [
        "",
        "## 附錄：代碼與判斷一覽",
        "",
        "下表由已審代碼表轉成，方便對照全文。升降級條件見正文各節，本表不重複長文。原始 json 不隨本頁公開。",
        "",
        "| " + " | ".join(cols) + " |",
        "|" + "|".join(["---"] * len(cols)) + "|",
    ]
    for r in rows:
        vals = [cell(r.get("ticker"))]
        if group_key:
            vals.append(cell(r.get(group_key)))
        if "category" in sample:
            vals.append(cell(r.get("category")))
        on = r.get("onDashboard")
        if on is True:
            vals.append("是")
        elif on is False:
            vals.append("否")
        else:
            vals.append(cell(on) if on else "—")
        vals.append(cell(r.get("call") or "—"))
        lines.append("| " + " | ".join(vals) + " |")
    note = meta.get("priceNote") or ""
    disc = meta.get("disclaimer") or ""
    if note or disc:
        lines += ["", " ".join(x for x in [note, disc] if x)]
    return "\n".join(lines) + "\n"


TAG_RE = re.compile(r"【(事|司|估|推|假|媒/未核|媒／未核|媒|暫定)[^】]*】")
TAG_CLASS = {
    "事": "tag-shi",
    "司": "tag-si",
    "估": "tag-gu",
    "推": "tag-tui",
    "假": "tag-jia",
    "媒/未核": "tag-mei",
    "媒／未核": "tag-mei",
    "媒": "tag-mei",
    "暫定": "tag-zan",
}


def mark_tags(html_text: str) -> str:
    def repl(m):
        raw = m.group(0)
        kind = m.group(1)
        cls = TAG_CLASS.get(kind, "tag-mei")
        return f'<span class="tag {cls}">{html.escape(raw)}</span>'
    return TAG_RE.sub(repl, html_text)


def md_to_html(src: str) -> str:
    lines = src.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    ids: dict[str, int] = {}
    n = len(lines)

    def flush_para(buf: list[str]):
        if buf:
            out.append("<p>" + _inline(" ".join(s.strip() for s in buf)) + "</p>")
            buf.clear()

    para: list[str] = []

    while i < n:
        line = lines[i]
        # table
        if re.match(r"^\s*\|", line) and i + 1 < n and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            flush_para(para)
            rows = []
            while i < n and re.match(r"^\s*\|", lines[i]):
                raw = lines[i].strip()
                if re.match(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?$", raw):
                    i += 1
                    continue
                cells = [c.strip() for c in raw.strip("|").split("|")]
                rows.append(cells)
                i += 1
            if rows:
                head, body = rows[0], rows[1:]
                th = "".join(f"<th>{_inline(c)}</th>" for c in head)
                trs = []
                for r in body:
                    # pad/truncate
                    r = (r + [""] * len(head))[:len(head)]
                    trs.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
                out.append(
                    '<div class="table-wrap" tabindex="0"><table>'
                    f"<thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
                )
            continue
        # heading
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            flush_para(para)
            level = len(m.group(1))
            title = m.group(2).strip()
            hid = _heading_id(re.sub(r"[#*`]", "", title), ids)
            out.append(f'<h{level} id="{html.escape(hid, True)}">{_inline(title)}</h{level}>')
            i += 1
            continue
        # hr
        if re.match(r"^\s*---+\s*$", line):
            flush_para(para)
            out.append("<hr>")
            i += 1
            continue
        # blockquote
        if line.startswith(">"):
            flush_para(para)
            bq = []
            while i < n and (lines[i].startswith(">") or (bq and lines[i].strip() == "")):
                bq.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            # drop trailing blanks
            while bq and bq[-1].strip() == "":
                bq.pop()
            inner = md_to_html("\n".join(bq)) if any(x.strip() for x in bq) else ""
            out.append(f"<blockquote>{inner}</blockquote>")
            continue
        # lists
        lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if lm:
            flush_para(para)
            # gather consecutive list lines (including blanks between items? no)
            items = []
            while i < n:
                cur = lines[i]
                m2 = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", cur)
                if m2:
                    items.append((_list_level(m2.group(1)), m2.group(2), m2.group(3)))
                    i += 1
                    continue
                break
            def emit(start: int, parent_level: int) -> tuple[str, int]:
                # determine type from first item at this level
                j = start
                while j < len(items) and items[j][0] != parent_level:
                    if items[j][0] < parent_level:
                        return "", start
                    j += 1
                if j >= len(items) or items[j][0] != parent_level:
                    return "", start
                ordered = items[j][1] not in "-*"
                tag = "ol" if ordered else "ul"
                chunks = [f"<{tag}>"]
                k = start
                while k < len(items):
                    lvl, marker, text = items[k]
                    if lvl < parent_level:
                        break
                    if lvl > parent_level:
                        # should have been consumed as child
                        child, k = emit(k, lvl)
                        if chunks[-1].endswith("</li>"):
                            chunks[-1] = chunks[-1][:-5] + child + "</li>"
                        else:
                            chunks.append(f"<li>{child}</li>")
                        continue
                    # item at this level; absorb following deeper items
                    k += 1
                    child_html = ""
                    if k < len(items) and items[k][0] > parent_level:
                        child_html, k = emit(k, items[k][0])
                    chunks.append(f"<li>{_inline(text)}{child_html}</li>")
                chunks.append(f"</{tag}>")
                return "".join(chunks), k
            block, _ = emit(0, items[0][0])
            out.append(block)
            continue
        # blank
        if not line.strip():
            flush_para(para)
            i += 1
            continue
        para.append(line)
        i += 1
    flush_para(para)
    return "\n".join(out)


CSS = r"""
:root {
  --bg: #f3f0e8;
  --bg-elev: #fffcf6;
  --sidebar: #faf7f0;
  --line: rgba(28, 36, 48, 0.12);
  --text: #152033;
  --muted: #5c6b80;
  --faint: #8a97a8;
  --accent: #0f6e68;
  --accent-soft: rgba(15, 110, 104, 0.12);
  --chip: #e8f4f2;
  --shadow: 0 10px 30px rgba(21, 32, 51, 0.08);
  --radius: 16px;
}
[data-theme="dark"] {
  --bg: #0c111b;
  --bg-elev: #151c29;
  --sidebar: #101826;
  --line: rgba(210, 222, 238, 0.1);
  --text: #e9eef6;
  --muted: #9aa8bb;
  --faint: #738196;
  --accent: #5ee0d0;
  --accent-soft: rgba(94, 224, 208, 0.12);
  --chip: #1b2738;
  --shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
}
html { font-size: 19px; -webkit-text-size-adjust: 100%; }
html, body { margin: 0; padding: 0; }
body {
  font-family: ui-sans-serif, system-ui, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.65;
  font-size: 19px;
}
a { color: var(--accent); text-underline-offset: 3px; }
a:hover { text-decoration-thickness: 2px; }
.top {
  position: sticky; top: 0; z-index: 20;
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--line);
  padding: 12px 20px;
}
.top-inner {
  max-width: 52rem; margin: 0 auto;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.brand-link {
  font-weight: 750; text-decoration: none; color: var(--text);
  font-size: 16px;
}
.brand-link:hover { color: var(--accent); }
.top .spacer { flex: 1; }
.ghost {
  border: 1px solid var(--line);
  background: var(--bg-elev);
  color: var(--text);
  border-radius: 999px;
  padding: 8px 13px;
  cursor: pointer;
  font: inherit;
  font-size: 15px;
}
.ghost:hover { border-color: color-mix(in srgb, var(--accent) 50%, var(--line)); }
.ghost:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.wrap { max-width: 52rem; margin: 0 auto; padding: 24px 20px 64px; }
.kicker { color: var(--faint); font-size: 14px; letter-spacing: 0.08em; text-transform: uppercase; margin: 0 0 6px; }
h1 { font-size: 31px; letter-spacing: -0.03em; line-height: 1.25; margin: 0 0 12px; }
h2 { font-size: 24px; letter-spacing: -0.02em; margin: 2em 0 0.6em; }
h3 { font-size: 20px; margin: 1.6em 0 0.5em; }
h4, h5, h6 { font-size: 18px; margin: 1.4em 0 0.4em; }
.disclaimer {
  background: var(--accent-soft);
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--line));
  border-radius: var(--radius);
  padding: 14px 16px;
  font-size: 16px;
  color: var(--text);
  margin: 0 0 28px;
}
.meta { color: var(--muted); font-size: 16px; margin: 0 0 16px; }
article p { margin: 0.7em 0; }
article ul, article ol { margin: 0.5em 0 0.8em; padding-left: 1.4em; }
article li { margin: 0.25em 0; }
article li > ul, article li > ol { margin: 0.2em 0 0.3em; }
hr { border: 0; border-top: 1px solid var(--line); margin: 2em 0; }
blockquote {
  margin: 1em 0;
  padding: 8px 16px;
  border-left: 4px solid var(--accent);
  background: var(--bg-elev);
  border-radius: 0 12px 12px 0;
  color: var(--text);
}
blockquote p { margin: 0.4em 0; }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.88em;
  background: var(--chip);
  padding: 0.1em 0.35em;
  border-radius: 6px;
  overflow-wrap: anywhere; word-break: normal;
}
.table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin: 1em 0 1.4em;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg-elev);
  max-width: 100%;
}
.table-wrap:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
table {
  border-collapse: collapse;
  min-width: 36em;
  width: 100%;
  font-size: 16px;
  line-height: 1.45;
}
th, td {
  border-bottom: 1px solid var(--line);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}
th {
  font-size: 14px;
  color: var(--muted);
  font-weight: 650;
  background: color-mix(in srgb, var(--bg) 55%, var(--bg-elev));
  white-space: nowrap;
}
tbody tr:last-child td { border-bottom: 0; }
.other {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
}
.other h2 { margin-top: 0; font-size: 20px; }
.other ul { padding-left: 1.2em; }
.foot {
  margin-top: 36px;
  color: var(--faint);
  font-size: 15px;
}
@media (max-width: 720px) {
  html, body { font-size: 17px; }
  h1 { font-size: 26px; }
  h2 { font-size: 21px; }
  .wrap { padding: 18px 16px 48px; }
  .top { padding: 10px 16px; }
  table { font-size: 15px; min-width: 40em; }
  th, td { padding: 8px 9px; }
}
@media print {
  .top { position: static; }
  .ghost { display: none; }
  body { background: #fff; color: #111; }
}
.tag {
  font-size: 0.86em;
  font-weight: 700;
  padding: 0.05em 0.32em;
  border-radius: 5px;
  white-space: nowrap;
}
.tag-shi { color: var(--accent); background: var(--accent-soft); }
.tag-si { color: var(--muted); background: var(--chip); }
.tag-gu { color: var(--muted); background: var(--chip); }
.tag-tui { color: var(--text); background: color-mix(in srgb, var(--accent) 10%, var(--bg-elev)); }
.tag-jia { color: var(--muted); background: var(--chip); }
.tag-mei { color: var(--muted); background: color-mix(in srgb, var(--faint) 18%, var(--bg-elev)); }
.tag-zan { color: var(--muted); background: var(--chip); }
"""

THEME_JS = r"""
(function(){
  var root = document.documentElement;
  var btn = document.getElementById("themeBtn");
  function label(t){ if(btn) btn.textContent = t === "dark" ? "切換淺色" : "切換深色"; }
  function apply(t){
    root.setAttribute("data-theme", t);
    try { localStorage.setItem("watchlist-theme", t); } catch(e) {}
    label(t);
  }
  var saved = null;
  try { saved = localStorage.getItem("watchlist-theme"); } catch(e) {}
  var prefer = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  apply((saved === "dark" || saved === "light") ? saved : (prefer ? "dark" : "light"));
  if (btn) btn.addEventListener("click", function(){
    apply(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });
})();
"""


def page(rep: dict, body: str, others: list[dict]) -> str:
    links = []
    for o in others:
        if o["id"] == rep["id"]:
            continue
        links.append(f'<li><a href="{html.escape(o["id"])}.html">{html.escape(o["nav"])}</a>　<span class="meta" style="display:inline">{html.escape(o["date"])}</span></li>')
    other_html = (
        f'<nav class="other"><h2>其他研究報告</h2><ul>{"".join(links)}</ul></nav>'
        if links else ""
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>{html.escape(rep["title"])}　關注持股看板</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="top">
    <div class="top-inner">
      <a class="brand-link" href="../index.html">← 關注持股看板</a>
      <div class="spacer"></div>
      <button class="ghost" id="themeBtn" type="button" aria-label="切換主題">切換深淺色</button>
    </div>
  </header>
  <main class="wrap">
    <p class="kicker">研究報告　{html.escape(rep["date"])}　台北時間</p>
    <p class="disclaimer">{html.escape(DISCLAIMER)}</p>
    <article>
      {body}
    </article>
    {other_html}
    <p class="foot">來源檔只作內部研究底稿。本頁為已審正文的網頁版，不是交易授權。</p>
  </main>
  <script>{THEME_JS}</script>
</body>
</html>
"""


def build_reports(dest: Path | None = None) -> list[Path]:
    dest = Path(dest) if dest else OUT
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    rendered = []
    for rep in REPORTS:
        md = rep["src"].read_text(encoding="utf-8")
        tickers_path = rep.get("tickers")
        if tickers_path and Path(tickers_path).exists() and "附錄：代碼與判斷一覽" not in md:
            md = md.rstrip() + "\n\n" + tickers_appendix_md(Path(tickers_path))
        # If the first line is an H1 matching the title, keep it as the page h1.
        body = mark_tags(md_to_html(md))
        rendered.append(page(rep, body, REPORTS))
    for rep, html_text in zip(REPORTS, rendered):
        path = dest / f"{rep['id']}.html"
        path.write_text(html_text, encoding="utf-8")
        written.append(path)
        print("wrote report", path, "bytes", path.stat().st_size)
    return written


if __name__ == "__main__":
    build_reports()
