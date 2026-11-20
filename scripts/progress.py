#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记进展，并重新生成全景。各会话共用一个文件夹时才用得上。

用法（在工作区根目录运行；init_ledger.py 会把本文件复制到 coord/ 里）：
  python3 coord/progress.py E1.1 进行中 "路线 A：浏览器自带识别"
  python3 coord/progress.py E1.1 不成 "部分手机拿不到结果" E1.2 完成 "松手后 2 秒出字"
  python3 coord/progress.py                不记，只重新生成全景

怎么记：
  编号   接在你的会话编号后面：E1.1、E1.2，再往下分是 E1.1.1。一个编号是一块活：
         一个子代理的任务，或者你自己的一个阶段。整件事的状态记在会话编号（E1）上。
  状态   只用这七个词：待做、进行中、等用户、完成、不成、卡住、放弃。
  文字   第一次写这块活是什么，之后写一句结果。20 个字以内，可以不写。
  时机   拆活的时候，把拆出来的几块一次记上；一块活开始、交回、结束时改状态；
         要用户来看、来定的时候记“等用户”，全景页会把它顶到最上面。
  先后   先推进，再记：先把下一批活开出去、先回复用户，然后才运行这条命令。

监管者另外用它记清单：每条提醒、延后清单里的每一项，各记成一条（S1.1、S1.2……）。
  没处理的记“待做”，要用户定的记“等用户”，处理掉了改“完成”，不做了改“放弃”；
  文字写“是什么（建议去哪个会话处理）”。全景页会把没处理的单列一栏。
  每次巡检结束，在自己的编号上记一句：S1 进行中 "巡检 #2：1 条提醒"。

它写三样东西，都不要手改：
  coord/progress/<会话编号>.md   每个会话一个文件，只往后加行，所以几个会话同时记也不会撞
  coord/PROGRESS.md              全景，Markdown
  coord/progress.html            全景，用浏览器打开，每 10 秒自动刷新

退出码：0 成功；2 参数有问题。
"""

import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATUSES = ["待做", "进行中", "等用户", "完成", "不成", "卡住", "放弃"]
ID = re.compile(r"^[A-Za-z][A-Za-z0-9]*(\.[0-9]+)*$")
LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2})｜([^｜]+)｜([^｜]+)｜(.*)$")
ROLE_CN = {"explorer": "探索者", "builder": "建设者", "supervisor": "监管者"}
TEXT_HINT = 30  # 文字超过这么多字就提醒一句：全景是给人扫一眼的


def die(message):
    print("错误：" + message, file=sys.stderr)
    sys.exit(2)


def setup_output():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ---------- 读 ----------

def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def parse_tz(text):
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", text or "")
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))


def now_in(tz):
    fake = os.environ.get("DEMO_FIRST_NOW")
    if fake:
        try:
            dt = datetime.fromisoformat(fake)
        except ValueError:
            die("环境变量 DEMO_FIRST_NOW 的值“%s”不是 ISO 时间。" % fake)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz or timezone.utc)
        return dt.astimezone(tz) if tz else dt
    return datetime.now(timezone.utc).astimezone(tz)


def board(coord):
    """从 BOARD.md 里读分工表和“小样”“待探索”两节。文件没有或认不出来就返回空的。"""
    rows, lists = [], {"小样": [], "待探索": []}
    path = coord / "BOARD.md"
    if not path.exists():
        return rows, lists
    header, section = None, None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if text.startswith("## "):
            section = next((key for key in lists if text[3:].strip().startswith(key)), None)
            continue
        if section and text.startswith("- ") and text[2:].strip():
            lists[section].append(text[2:].strip())
            continue
        if not text.startswith("|"):
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        if header is None:
            if "编号" in cells and "角色" in cells:
                header = cells
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue
        row = dict(zip(header, cells))
        if row.get("编号"):
            what = next((value for key, value in row.items() if key.startswith("要回答的问题")), "")
            rows.append({"id": row["编号"], "role": row.get("角色", ""), "title": row.get("细分", ""),
                         "what": what, "link": row.get("任务链接", "")})
    return rows, lists


def events(coord):
    """读所有会话的进展记录，按时间排好。同一分钟里的保持各自文件里的先后。"""
    found = []
    folder = coord / "progress"
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*.md")):
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines()):
            m = LINE.match(line.strip())
            if m and ID.match(m.group(2).strip()) and m.group(3).strip() in STATUSES:
                found.append((m.group(1), path.name, number, m.group(2).strip(), m.group(3).strip(), m.group(4).strip()))
    found.sort(key=lambda item: (item[0], item[1], item[2]))
    return found


# ---------- 组成一棵树 ----------

def order_key(node_id):
    return [int(part) if part.isdigit() else part for part in node_id.split(".")]


def build(coord):
    ledger = read_json(coord / "ledger.json")
    tz = parse_tz(ledger.get("tz"))
    rows, lists = board(coord)
    briefs = ledger.get("briefs", {})
    project = ledger.get("name") or ledger.get("goal", "")[:10] or "项目"

    nodes = {}

    def node(node_id):
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "title": "", "note": "", "status": "", "at": "", "children": []}
            if "." in node_id:
                node(node_id.rsplit(".", 1)[0])["children"].append(node_id)
        return nodes[node_id]

    for at, _, _, node_id, status, text in events(coord):
        item = node(node_id)
        if "." not in node_id:
            # 会话这一层有自己的名字，记的文字都算“最新情况”。
            item["note"] = text or item["note"]
        elif text and not item["title"]:
            item["title"] = text
        elif text:
            item["note"] = text
        item["status"], item["at"] = status, at
    for item in nodes.values():
        item["children"].sort(key=order_key)

    # 会话这一层：分工表里的、台账里登记过的、自己记过进展的，都算。
    order = []
    for source in ([row["id"] for row in rows], list(briefs), [k for k in nodes if "." not in k]):
        for session_id in source:
            if session_id not in order:
                order.append(session_id)
    by_row = {row["id"]: row for row in rows}
    sessions = []
    for session_id in order:
        row, brief = by_row.get(session_id, {}), briefs.get(session_id, {})
        role = row.get("role") or ROLE_CN.get(brief.get("role"), "")
        if session_id == "D":
            role = role or "调度者"
        title = brief.get("title") or row.get("title", "")
        name = brief.get("name") or " - ".join(part for part in (project, role, title) if part)
        mine = nodes.get(session_id)
        if mine and mine["status"]:
            status = mine["status"]
        elif brief.get("status") == "done":
            status = "结束"
        elif brief or session_id == "D":
            status = "已开"
        else:
            status = "待开"
        sessions.append({
            "id": session_id, "role": role, "name": name, "what": row.get("what", ""),
            "link": row.get("link", ""), "effort": brief.get("effort", ""), "status": status,
            "note": (mine or {}).get("note", ""),
            "at": (mine or {}).get("at", ""), "children": (mine or {}).get("children", []),
        })

    return {
        "project": project, "goal": ledger.get("goal", ""), "tz": ledger.get("tz", ""),
        "start": ledger.get("start") or "", "deadline": ledger.get("deadline") or "",
        "generated": now_in(tz).isoformat(timespec="seconds"),
        "sessions": sessions, "nodes": nodes, "samples": lists["小样"], "queue": lists["待探索"],
    }


def waiting(tree):
    """状态是“等用户”的节点，最新的在前。返回 [(会话, 节点)]。"""
    found = []
    for session in tree["sessions"]:
        stack = [session["id"]]
        while stack:
            node_id = stack.pop()
            item = tree["nodes"].get(node_id)
            if not item:
                continue
            if item["status"] == "等用户":
                found.append((session, item))
            stack.extend(item["children"])
    found.sort(key=lambda pair: pair[1]["at"], reverse=True)
    return found


OPEN = ("待做", "进行中", "等用户", "卡住")


def watch_list(tree):
    """监管者记的清单：它编号下面的每一条。返回 (没处理的 [(会话, 节点)], 已处理的条数)。"""
    todo, closed = [], 0
    for session in tree["sessions"]:
        if session["role"] != "监管者":
            continue
        for node_id in session["children"]:
            item = tree["nodes"][node_id]
            if item["status"] in OPEN:
                todo.append((session, item))
            else:
                closed += 1
    return todo, closed


def what_waits(item):
    """“等用户”的那一条该怎么念：会话这一层只有最新情况，下面的节点有标题和结果。"""
    if "." not in item["id"]:
        return item["note"] or "在等你"
    return "%s %s%s" % (item["id"], item["title"] or "", " — " + item["note"] if item["note"] else "")


def clock(at):
    """把 “2026-11-22 15:02” 或 ISO 时间缩成钟点。"""
    return at.replace("T", " ")[11:16] if len(at) >= 16 else at


# ---------- 写成 Markdown ----------

def render_md(tree):
    lines = ["# 全景：%s" % tree["project"], "",
             "> 由 progress.py 生成，不要手改。生成于 %s。浏览器里看：coord/progress.html（每 10 秒自动刷新）。"
             % clock(tree["generated"]), ""]
    wait = waiting(tree)
    if wait:
        lines.append("等用户处理的：")
        for session, item in wait:
            lines.append("- %s：%s（%s 起）" % (session["name"], what_waits(item), clock(item["at"])))
        lines.append("")
    todo, closed = watch_list(tree)
    if todo or closed:
        lines.append("监管者的清单（没处理的 %d 条，已处理 %d 条）：" % (len(todo), closed))
        for _, item in todo:
            lines.append("- %s %s %s%s" % (item["status"], item["id"], item["title"],
                                           " — " + item["note"] if item["note"] else ""))
        lines.append("")

    def walk(node_id, depth):
        item = tree["nodes"][node_id]
        note = " — " + item["note"] if item["note"] else ""
        lines.append("%s- %s %s %s%s" % ("  " * depth, item["status"] or "（没记）", item["id"], item["title"], note))
        for child in item["children"]:
            walk(child, depth + 1)

    for session in tree["sessions"]:
        lines.append("- %s %s %s%s%s" % (session["status"], session["id"], session["name"],
                                         "（%s）" % session["effort"] if session["effort"] else "",
                                         " — " + session["note"] if session["note"] else ""))
        if session["what"]:
            lines.append("  - 管什么：%s" % session["what"])
        if session["id"] == "D":
            lines.extend("  - 小样：%s" % sample for sample in tree["samples"])
        for child in session["children"]:
            walk(child, 1)
    lines.extend("- 待探索，还没开：%s" % item for item in tree["queue"])
    return "\n".join(lines) + "\n"


# ---------- 写成网页 ----------

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>全景 · __PROJECT__</title>
<style>
:root { --bg:#f6f5f1; --card:#fff; --ink:#1f2328; --dim:#6b7280; --line:#e3e1da; --blue:#2563eb; --green:#15803d;
  --amber:#b45309; --red:#b91c1c; --amber-bg:#fef3c7; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181c; --card:#1f2228; --ink:#e6e6e6; --dim:#9aa1ac;
  --line:#30343c; --blue:#7aa7ff; --green:#5fcf85; --amber:#f0b35a; --red:#ff8585; --amber-bg:#3d2f10; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
main { max-width:980px; margin:0 auto; padding:20px 16px 48px; }
h1 { font-size:20px; margin:0 0 2px; }
.goal { color:var(--dim); margin:0 0 14px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin-bottom:12px; }
.time { display:flex; flex-wrap:wrap; gap:6px 18px; align-items:baseline; }
.time b { font-size:18px; font-variant-numeric:tabular-nums; }
.attn { border-color:var(--amber); background:var(--amber-bg); }
.attn h2, .tree h2, .watch h2 { font-size:14px; margin:0 0 6px; }
.attn ul { margin:0; padding-left:18px; }
.watch h2 span { font-weight:400; color:var(--dim); margin-left:6px; }
.sess { border-top:1px solid var(--line); padding:10px 0 6px; }
.sess:first-of-type { border-top:0; padding-top:2px; }
.sess > summary, .node > summary { cursor:pointer; list-style:none; }
.sess > summary::-webkit-details-marker, .node > summary::-webkit-details-marker { display:none; }
details > summary::before { content:"▸"; display:inline-block; width:1em; color:var(--dim); }
details[open] > summary::before { content:"▾"; }
.name { font-weight:600; }
.meta { color:var(--dim); font-size:13px; }
.what { color:var(--dim); font-size:13px; margin:2px 0 4px 1em; }
.kids { margin:2px 0 0 10px; padding-left:12px; border-left:2px solid var(--line); }
.node, .leaf { padding:2px 0; }
.tag { display:inline-block; min-width:3.6em; text-align:center; font-size:12px; padding:0 6px; border-radius:9px;
  border:1px solid currentColor; margin-right:6px; }
.s-进行中, .s-已开 { color:var(--blue); } .s-完成, .s-结束 { color:var(--green); } .s-等用户 { color:var(--amber); font-weight:700; }
.s-不成, .s-卡住 { color:var(--red); } .s-待做, .s-待开, .s-放弃, .s-没记 { color:var(--dim); }
.id { color:var(--dim); font-size:12px; margin-right:4px; font-variant-numeric:tabular-nums; }
.note { color:var(--dim); }
.ago { color:var(--dim); font-size:12px; margin-left:6px; }
a { color:var(--blue); }
footer { color:var(--dim); font-size:12px; margin-top:14px; }
</style>
</head>
<body>
<main>
<h1>__PROJECT__ · 全景</h1>
<p class="goal">__GOAL__</p>
<div class="card time"><span>现在 <b id="now">--:--</b></span><span id="ran"></span><span id="limit" class="meta"></span></div>
<div class="card attn" id="attn" hidden><h2>要你去的地方</h2><ul id="attn-list">__WAITING__</ul></div>
__WATCH__
<div class="card tree"><h2>分工和进展</h2>
__TREE__
</div>
<footer>每 10 秒自动刷新。最后一次生成：__GENERATED__。这一页由 coord/progress.py 生成，各会话自己报的进展，要紧的地方请以监管者的巡检为准。</footer>
</main>
<script>
const D = __DATA__;
const pad = n => String(n).padStart(2, "0");
const span = ms => { const m = Math.max(0, Math.round(ms / 60000)); return Math.floor(m / 60) + ":" + pad(m % 60); };
const now = new Date();
const start = D.start ? new Date(D.start) : null, end = D.deadline ? new Date(D.deadline) : null;
function hm(d) {  // 按项目的时区显示钟点
  const m = /([+-])(\\d\\d):(\\d\\d)$/.exec(D.tz || "");
  if (!m) return pad(d.getHours()) + ":" + pad(d.getMinutes());
  const off = (m[1] === "+" ? 1 : -1) * (m[2] * 60 + +m[3]);
  const t = new Date(d.getTime() + off * 60000);
  return pad(t.getUTCHours()) + ":" + pad(t.getUTCMinutes());
}
document.getElementById("now").textContent = hm(now);
if (start && now >= start) document.getElementById("ran").textContent = "已进行 " + span(now - start);
// 这一页不催任何人。期限是用户自己定的，定了才显示，只给用户看。
document.getElementById("limit").textContent = !end ? "没有设期限，节奏由你掌握"
  : now < end ? "你定的期限 " + hm(end) + "，还有 " + span(end - now) : "已经过了你定的期限 " + span(now - end);
document.getElementById("attn").hidden = !document.getElementById("attn-list").children.length;
for (const el of document.querySelectorAll("[data-at]")) {
  const m = Math.round((now - new Date(el.dataset.at)) / 60000);
  el.textContent = m < 1 ? "刚刚" : m < 60 ? m + " 分钟前" : span(m * 60000) + " 前";
}
// 自动刷新后保持折叠状态和滚动位置
const KEY = "demo-first:" + D.project;
let closed = [];
try { closed = JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) {}
for (const d of document.querySelectorAll("details[data-id]")) {
  if (closed.includes(d.dataset.id)) d.open = false;
  d.addEventListener("toggle", () => {
    const all = [...document.querySelectorAll("details[data-id]")].filter(x => !x.open).map(x => x.dataset.id);
    try { localStorage.setItem(KEY, JSON.stringify(all)); } catch (e) {}
  });
}
try { window.scrollTo(0, +sessionStorage.getItem(KEY + ":y") || 0); } catch (e) {}
window.addEventListener("beforeunload", () => { try { sessionStorage.setItem(KEY + ":y", window.scrollY); } catch (e) {} });
</script>
</body>
</html>
"""


def iso_at(at, tz_label):
    """进展记录里的 “2026-11-22 15:02” 配上时区，给网页算“几分钟前”。"""
    return at.replace(" ", "T") + ":00" + (tz_label or "")


def render_html(tree):
    esc = html.escape

    def tag(status):
        status = status or "没记"
        return '<span class="tag s-%s">%s</span>' % (esc(status), esc(status))

    def walk(node_id):
        item = tree["nodes"][node_id]
        head = '%s<span class="id">%s</span>%s' % (tag(item["status"]), esc(item["id"]), esc(item["title"] or item["id"]))
        if item["note"]:
            head += ' <span class="note">— %s</span>' % esc(item["note"])
        if item["at"]:
            head += '<span class="ago" data-at="%s"></span>' % esc(iso_at(item["at"], tree["tz"]))
        if not item["children"]:
            return '<div class="leaf">%s</div>' % head
        kids = "".join(walk(child) for child in item["children"])
        return ('<details class="node" open data-id="%s"><summary>%s</summary><div class="kids">%s</div></details>'
                % (esc(item["id"]), head, kids))

    parts = []
    for session in tree["sessions"]:
        meta = [part for part in (session["role"], session["effort"]) if part]
        head = '%s<span class="name">%s</span> <span class="meta">%s</span>' % (
            tag(session["status"]), esc(session["name"]), esc("｜".join([session["id"]] + meta)))
        if session["at"]:
            head += '<span class="ago" data-at="%s"></span>' % esc(iso_at(session["at"], tree["tz"]))
        if session["link"].startswith("http"):
            head += ' <a href="%s" target="_blank" rel="noopener">打开会话</a>' % esc(session["link"], quote=True)
        if session["note"]:
            head += '<div class="what">最新：%s</div>' % esc(session["note"])
        body = ""
        if session["what"]:
            body += '<div class="what">管什么：%s</div>' % esc(session["what"])
        kids = "".join(walk(child) for child in session["children"])
        if session["id"] == "D":
            kids = "".join('<div class="leaf">%s%s</div>' % (tag("完成"), esc("小样：" + sample))
                           for sample in tree["samples"]) + kids
        if kids:
            body += '<div class="kids">%s</div>' % kids
        attrs = ' data-id="%s"' % esc(session["id"], quote=True)
        # 监管者的清单在上面单列了一栏，树里默认收起，免得同样的内容出现两遍。
        opened = "" if session["role"] == "监管者" and session["children"] else " open"
        parts.append('<details class="sess"%s%s><summary>%s</summary>%s</details>' % (opened, attrs, head, body))
    for item in tree["queue"]:
        parts.append('<div class="sess">%s<span class="name">待探索，还没开</span><div class="what">%s</div></div>'
                     % (tag("待开"), esc(item)))

    wait = "".join('<li><b>%s</b>：%s<span class="ago" data-at="%s"></span></li>'
                   % (esc(session["name"]), esc(what_waits(item)), esc(iso_at(item["at"], tree["tz"])))
                   for session, item in waiting(tree))
    todo, closed = watch_list(tree)
    watch = ""
    if todo or closed:
        rows = "".join('<div class="leaf">%s<span class="id">%s</span>%s%s<span class="ago" data-at="%s"></span></div>'
                       % (tag(item["status"]), esc(item["id"]), esc(item["title"] or item["id"]),
                          ' <span class="note">— %s</span>' % esc(item["note"]) if item["note"] else "",
                          esc(iso_at(item["at"], tree["tz"])))
                       for _, item in todo)
        watch = ('<div class="card watch"><h2>监管者的清单<span>没处理的 %d 条，已处理 %d 条</span></h2>%s</div>'
                 % (len(todo), closed, rows or '<div class="meta">都处理完了。</div>'))
    data = {key: tree[key] for key in ("project", "tz", "start", "deadline")}
    page = PAGE
    for key, value in (("__PROJECT__", esc(tree["project"])), ("__GOAL__", esc(tree["goal"])),
                       ("__WAITING__", wait), ("__WATCH__", watch), ("__TREE__", "\n".join(parts)),
                       ("__GENERATED__", esc(clock(tree["generated"]))),
                       ("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))):
        page = page.replace(key, value)
    return page


def write_atomic(path, text):
    """先写到临时文件再换上去：别的会话或浏览器不会读到写了一半的文件。"""
    tmp = path.with_name(path.name + ".%d.tmp" % os.getpid())
    tmp.write_text(text, encoding="utf-8", newline="\n")
    try:
        os.replace(tmp, path)
    except OSError:
        # 另一个会话正好也在换这个文件：让它的那一份留着，下一次记进展时会再生成。
        try:
            tmp.unlink()
        except OSError:
            pass


def rebuild(coord):
    """重新生成 PROGRESS.md 和 progress.html。返回这棵树。"""
    coord = Path(coord)
    tree = build(coord)
    write_atomic(coord / "PROGRESS.md", render_md(tree))
    write_atomic(coord / "progress.html", render_html(tree))
    return tree


# ---------- 记 ----------

def parse_triples(tokens):
    """把命令行上的一串词切成 [(编号, 状态, 文字)]。文字可以不写。"""
    triples, at = [], 0
    while at < len(tokens):
        node_id = tokens[at]
        if not ID.match(node_id):
            die("“%s”不是编号。编号接在会话编号后面，例如 E1.1、E1.2、E1.1.1。" % node_id)
        if at + 1 >= len(tokens) or tokens[at + 1] not in STATUSES:
            die("编号 %s 后面要跟状态，只能是：%s。" % (node_id, "、".join(STATUSES)))
        status, text, at = tokens[at + 1], "", at + 2
        starts_next = at + 1 < len(tokens) and ID.match(tokens[at]) and tokens[at + 1] in STATUSES
        if at < len(tokens) and not starts_next:
            text, at = tokens[at], at + 1
        triples.append((node_id, status, " ".join(text.replace("｜", "/").split())))
    return triples


def record(coord, triples, stamp):
    folder = coord / "progress"
    folder.mkdir(parents=True, exist_ok=True)
    by_file = {}
    for node_id, status, text in triples:
        by_file.setdefault(node_id.split(".")[0], []).append("- %s｜%s｜%s｜%s" % (stamp, node_id, status, text))
    for root, lines in by_file.items():
        path = folder / (root + ".md")
        head = "" if path.exists() else "# 进展记录 %s\n\n> 只由 progress.py 往后加行，不要手改。每行：时间｜编号｜状态｜文字。\n\n" % root
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(head + "\n".join(lines) + "\n")


def main():
    setup_output()
    args = sys.argv[1:]
    if any(arg in ("-h", "--help") for arg in args):
        # 例子里的解释器名换成现在用的这个（Windows 上多半没有 python3），照抄就能跑。
        python = Path(sys.executable).stem if sys.executable else "python3"
        print(__doc__.strip().replace("python3", python))
        return
    base = None
    if "--dir" in args:
        at = args.index("--dir")
        if at + 1 >= len(args):
            die("--dir 后面要跟目录（里面有 coord/ 的那一层）。")
        base = Path(args[at + 1])
        args = args[:at] + args[at + 2:]
    here = Path(__file__).resolve().parent
    if base is not None:
        coord = base / "coord"
    elif here.name == "coord":
        coord = here  # 被复制进台账之后，就认自己所在的这个台账
    else:
        coord = Path.cwd() / "coord"
    if not coord.is_dir():
        die("没找到 %s。在工作区根目录运行，或者用 --dir 指到里面有 coord/ 的那一层。" % coord)

    triples = parse_triples(args)
    if triples:
        tz = parse_tz(read_json(coord / "ledger.json").get("tz"))
        record(coord, triples, now_in(tz).strftime("%Y-%m-%d %H:%M"))
    tree = rebuild(coord)
    for node_id, status, text in triples:
        print("已记：%s %s %s" % (node_id, status, text))
        if len(text) > TEXT_HINT:
            print("  提醒：这句有 %d 个字。全景是给人扫一眼的，下次压到 20 个字以内。" % len(text))
    wait = waiting(tree)
    print("全景已更新：%s（%d 个会话%s）" % (coord / "progress.html", len(tree["sessions"]),
                                    "，%d 处等用户" % len(wait) if wait else ""))


if __name__ == "__main__":
    main()
