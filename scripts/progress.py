#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""记进展，并重新生成全景。各会话共用一个文件夹时才用得上。

用法（在工作区根目录运行；init_ledger.py 会把本文件复制到 coord/ 里）：
  python3 coord/progress.py E1.1 进行中 "松手后的反馈动画" E1.2 进行中 "录音格式兼容"
  python3 coord/progress.py E1.1 完成 "松手即转圈" E1.2 卡住 "一种手机不认这个格式"
  python3 coord/progress.py                不记，只重新生成全景

怎么记：
  编号   接在你的会话编号后面：E1.1、E1.2。一个编号是一块活：一个子代理的任务，
         或者你自己的一个阶段。整件事的状态记在会话编号（E1）上。
         一般记到这一层就够。一块活自己又分成几块同时做，才再往下分（E1.1.1）；
         同一块活改了几版、试了几次，不用一版一版记。
         只记你自己编号下的。别的会话的活，哪怕你知道结果，也不要替它记。
  子代理 这块活交给了子代理：第一次记它时，在编号后面加“子代理”三个字，之后不用再加。
         python3 coord/progress.py E1.3 子代理 进行中 "松手后的反馈动画"
  状态   只用这七个词：待做、进行中、等用户、完成、不成、卡住、放弃。
  文字   第一次写这块活是什么，之后写一句结果。20 个字以内，可以不写。
  时机   拆活的时候，把拆出来的几块一次记上；一块活开始、交回、结束时改状态；
         要用户来看、来定的时候记“等用户”，全景页会把它顶到最上面。
         只有“等用户”不能省：用户靠它知道该去哪个会话。别的漏记了，全景只是粗一点。
  先后   先推进，再记：先把下一批活开出去、先回复用户，然后才运行这条命令。
  钟点   每次运行都会打印项目钟点。回报、巡检和记录里写钟点都照它，不用机器自己的时间。

监管者另外用它记清单：每条提醒、延后清单里的每一项，各记成一条（S1.1、S1.2……）。
  没处理的记“待做”，要用户定的记“等用户”，处理掉了改“完成”，不做了改“放弃”；
  文字写“是什么（建议去哪个会话处理）”。全景页会把没处理的单列出来。
  每次巡检结束，在自己的编号上记一句：S1 进行中 "巡检 #2：1 条提醒"。

它写四样东西，都不要手改：
  coord/progress/<会话编号>.md   每个会话一个文件，只往后加行，所以几个会话同时记也不会撞
  coord/PROGRESS.md              全景，Markdown
  coord/progress.html            全景，用浏览器打开，开着就行，它自己会更新
  coord/progress.data.js         开着的全景页每几秒读一次的数据

退出码：0 成功；2 参数有问题。
"""

import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATUSES = ["待做", "进行中", "等用户", "完成", "不成", "卡住", "放弃"]
ID = re.compile(r"^[A-Za-z][A-Za-z0-9]*(\.[0-9]+)*$")
LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2} \d{2}:\d{2})｜([^｜]+)｜([^｜]+)｜([^｜]*)(?:｜(.*))?$")
AGENT = "子代理"  # 写在编号后面：这块活交给了子代理
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


# “小样”“待探索”两节里，agent 常写一行“无。……”或“（已开出：……）”。它们不是一项：
# 不滤掉的话，全景页会把它画成一个排队的会话。“无障碍适配”“没有网络时的提示”这种是真的一项，不能误伤。
NOT_AN_ITEM = re.compile(r"^(?:(?:无|暂无|没有)(?:[。．.，,；;：:！!（(\s]|$)|[（(]已)")


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
            if not NOT_AN_ITEM.match(text[2:].strip()):
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
                found.append((m.group(1), path.name, number, m.group(2).strip(), m.group(3).strip(), m.group(4).strip(),
                              (m.group(5) or "").strip() == AGENT))
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
            nodes[node_id] = {"id": node_id, "title": "", "note": "", "status": "", "at": "", "children": [], "agent": False}
            if "." in node_id:
                node(node_id.rsplit(".", 1)[0])["children"].append(node_id)
        return nodes[node_id]

    for at, _, _, node_id, status, text, agent in events(coord):
        item = node(node_id)
        item["agent"] = item["agent"] or (agent and "." in node_id)  # 标过一次就一直算
        if "." not in node_id:
            # 会话这一层有自己的名字，记的文字都算“最新情况”。
            item["note"] = text or item["note"]
        elif text and not item["title"]:
            item["title"] = text  # 第一次写的是这块活是什么
        elif text and text != item["title"]:
            item["note"] = text  # 和标题一字不差的不算结果：同一条命令跑了两遍，全景上别显示两遍
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
            "id": session_id, "role": role, "name": name, "title": title, "what": row.get("what", ""),
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
    """把 “2026-03-14 15:02” 或 ISO 时间缩成钟点。"""
    return at.replace("T", " ")[11:16] if len(at) >= 16 else at


# ---------- 写成 Markdown ----------

def render_md(tree):
    lines = ["# 全景：%s" % tree["project"], "",
             "> 由 progress.py 生成，不要手改。生成于 %s。浏览器里看：coord/progress.html（开着就行，它自己会更新）。"
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
        lines.append("%s- %s %s %s%s%s" % ("  " * depth, item["status"] or "（没记）", item["id"],
                                         "（子代理）" if item["agent"] else "", item["title"], note))
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

# 网页只是一个壳：数据嵌在里面一份，另存一份到 progress.data.js。
# 开着的页面每几秒读一次那个文件，有变化就原地重画，不整页刷新，展开收起和滚动位置都留着。
PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
/* 版式：顶上是项目和整体进度（一格是一块活），紧跟着是等你处理的事。
   下面是一棵树：项目 → 会话 → 会话里的活和子代理 → 再往下。窗口够宽时画成向右分叉的图，窄了就是缩进的大纲。 */
:root {
  --bg:#f5f4f0; --surface:#fffefb; --sunken:#eceae3; --ink:#1d1c19; --ink2:#4b4943; --dim:#7d7a72; --faint:#a5a299;
  --line:#e3e0d7; --line2:#cfcbc0; --on:#fff; --idle:#b4b0a5;
  --run:#2563d9; --run-solid:#3b78ea; --run-bg:#e7effd;
  --wait:#8f5300; --wait-solid:#ee9d16; --wait-bg:#fff3d4; --wait-line:#efcf85;
  --done:#1d7a4d; --done-solid:#2f9e68; --done-bg:#e2f3e9;
  --bad:#c0362d; --bad-solid:#dc4a40; --bad-bg:#fdeae7; --fail:#b98880;
  --sans:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"PingFang SC","HarmonyOS Sans SC","Microsoft YaHei UI","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
  --mono:"Cascadia Mono","SF Mono",ui-monospace,Menlo,Consolas,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#131412; --surface:#1b1c19; --sunken:#242521; --ink:#eceae4; --ink2:#c3c0b8; --dim:#908d85; --faint:#6a6861;
  --line:#2a2b27; --line2:#3a3b36; --on:#141512; --idle:#5d5c56;
  --run:#86adff; --run-solid:#6f9cf5; --run-bg:#19284a;
  --wait:#f3bb5e; --wait-solid:#eca62c; --wait-bg:#2c2210; --wait-line:#5f4a1a;
  --done:#68cf98; --done-solid:#4db57f; --done-bg:#13301f;
  --bad:#ff8a7f; --bad-solid:#ef6a5f; --bad-bg:#3a1a17; --fail:#8f6660; color-scheme:dark; } }
:root[data-theme="dark"] {
  --bg:#131412; --surface:#1b1c19; --sunken:#242521; --ink:#eceae4; --ink2:#c3c0b8; --dim:#908d85; --faint:#6a6861;
  --line:#2a2b27; --line2:#3a3b36; --on:#141512; --idle:#5d5c56;
  --run:#86adff; --run-solid:#6f9cf5; --run-bg:#19284a;
  --wait:#f3bb5e; --wait-solid:#eca62c; --wait-bg:#2c2210; --wait-line:#5f4a1a;
  --done:#68cf98; --done-solid:#4db57f; --done-bg:#13301f;
  --bad:#ff8a7f; --bad-solid:#ef6a5f; --bad-bg:#3a1a17; --fail:#8f6660; color-scheme:dark; }

* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.6 var(--sans); -webkit-font-smoothing:antialiased; }
[hidden] { display:none !important; }
button { font:inherit; color:inherit; background:none; border:0; padding:0; margin:0; cursor:pointer; text-align:inherit; }
a { color:inherit; }
:focus-visible { outline:2px solid var(--run-solid); outline-offset:2px; border-radius:6px; }
svg { display:block; flex:none; }
.wrap { max-width:1120px; margin:0 auto; padding-block:32px 56px;
  padding-left:max(24px, env(safe-area-inset-left, 0px)); padding-right:max(24px, env(safe-area-inset-right, 0px)); }
.wrap.wide { max-width:1280px; }

/* 顶部 */
.top { display:flex; flex-wrap:wrap; gap:12px 32px; align-items:flex-end; justify-content:space-between; }
.eyebrow { margin:0 0 4px; font-size:12px; letter-spacing:.3em; color:var(--dim); }
h1 { margin:0; font-size:28px; line-height:1.25; font-weight:650; letter-spacing:.02em; text-wrap:balance; }
.goal { margin:4px 0 0; color:var(--ink2); max-width:62ch; }
.pace { margin:2px 0 0; color:var(--dim); font-size:12.5px; font-variant-numeric:tabular-nums; }
.tools { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
.live { display:inline-flex; align-items:center; gap:7px; margin-right:8px; color:var(--dim); font-size:12.5px; font-variant-numeric:tabular-nums; }
.live i { width:7px; height:7px; border-radius:50%; background:var(--done-solid); animation:ping 2.4s ease-out infinite; }
.live.off { color:var(--bad); }
.live.off i { background:var(--bad-solid); animation:none; }
.btn { display:inline-flex; align-items:center; gap:6px; height:28px; padding:0 11px; border:1px solid var(--line2); border-radius:8px;
  background:var(--surface); font-size:12.5px; color:var(--ink2); white-space:nowrap; }
.btn:hover { border-color:var(--faint); color:var(--ink); }
.btn[aria-pressed="true"] { background:var(--ink); border-color:var(--ink); color:var(--bg); }

/* 整体进度：一格是一块最底下的活，按会话分组 */
.overall { margin-top:22px; }
.ov-nums { display:flex; flex-wrap:wrap; align-items:center; gap:6px 16px; color:var(--dim); font-size:13px; }
.ov-nums b { font-size:26px; line-height:1; font-weight:650; color:var(--ink); font-variant-numeric:tabular-nums; }
.ov-nums b small { font-size:15px; font-weight:500; color:var(--dim); }
.ov-chip { display:inline-flex; align-items:center; gap:6px; color:var(--ink2); }
.ov-chip.zero { color:var(--faint); }
.ov-chip.k-wait:not(.zero) { color:var(--wait); font-weight:650; }
.ov-chip.k-stuck:not(.zero) { color:var(--bad); font-weight:650; }
.ov-bar { display:flex; gap:10px; margin-top:12px; }
.ov-g { min-width:0; }
.ov-g > button { display:block; max-width:100%; margin-top:6px; font-size:12px; color:var(--dim); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ov-g > button:hover { color:var(--ink); }
.ov-g em { font:500 11.5px var(--mono); margin-right:6px; color:var(--faint); }
.segs { display:flex; gap:3px; }
.segs i { flex:1; min-width:3px; height:10px; border-radius:3px; background:var(--line2); }
.segs i.s-run { background:var(--run-solid); }
.segs i.s-wait { background:var(--wait-solid); }
.segs i.s-done { background:var(--done-solid); }
.segs i.s-stuck { background:var(--bad-solid); }
.segs i.s-fail { background:var(--fail); }
.segs i.s-drop { background:transparent; box-shadow:inset 0 0 0 1.5px var(--line2); }
.ov-bar .segs i { cursor:pointer; }

/* 等你处理、监管者的提醒 */
.needs { margin-top:22px; padding:12px 16px 8px; border:1px solid var(--wait-line); border-radius:12px; background:var(--wait-bg); }
.needs.calm { padding:10px 16px; border-color:var(--line); background:transparent; color:var(--dim); font-size:13px; }
.needs h2 { display:flex; align-items:center; gap:8px; margin:0 0 4px; font-size:14px; font-weight:650; color:var(--wait); }
.needs ul { list-style:none; margin:0; padding:0; }
.needs li { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 10px; padding:6px 0; border-top:1px solid var(--wait-line); }
.needs li:first-child { border-top:0; }
.needs li b { font-weight:650; white-space:nowrap; }
.go { flex:1; min-width:min(14em, 100%); overflow-wrap:anywhere; }
.go:hover { text-decoration:underline; text-decoration-color:var(--wait-line); text-underline-offset:3px; }
.id { font:500 11.5px var(--mono); color:var(--faint); white-space:nowrap; }
.needs time { color:var(--dim); font-size:12px; white-space:nowrap; font-variant-numeric:tabular-nums; }
.lnk { font-size:12.5px; color:var(--dim); text-decoration:underline; text-decoration-color:var(--line2); text-underline-offset:3px; white-space:nowrap; }
.lnk:hover { color:var(--ink); }
.needs .lnk { color:var(--wait); text-decoration-color:var(--wait-line); }
.notes { margin-top:10px; padding:10px 16px 6px; border:1px solid var(--line); border-radius:12px; background:var(--surface); }
.notes h2 { margin:0 0 2px; font-size:13px; font-weight:650; color:var(--ink2); }
.notes h2 small { margin-left:8px; font-weight:400; color:var(--dim); }
.notes ul { list-style:none; margin:0; padding:0; }
.notes li { display:flex; align-items:baseline; gap:8px; padding:4px 0; font-size:13.5px; }
.notes li .ico { align-self:center; }

/* 树：共用的零件 */
.ico { display:grid; place-items:center; width:18px; height:16px; flex:none; }
.spin { display:block; width:14px; height:14px; border-radius:50%; border:2px solid var(--run-bg); border-top-color:var(--run-solid);
  border-right-color:var(--run-solid); animation:spin 1.2s linear infinite; }
.meter { display:inline-flex; align-items:center; gap:8px; white-space:nowrap; }
.meter .segs i { flex:none; width:12px; height:6px; min-width:0; }
.meter.many .segs i { width:6px; }
.meter b { font-size:12px; font-weight:600; color:var(--dim); font-variant-numeric:tabular-nums; }
.tag { display:inline-block; margin-right:6px; padding:0 5px; border:1px solid var(--line2); border-radius:5px; font-size:11px; line-height:16px;
  color:var(--dim); white-space:nowrap; vertical-align:1px; }
.st { font-size:12px; font-weight:650; white-space:nowrap; }
.st.k-wait { color:var(--wait); } .st.k-stuck { color:var(--bad); }
.st.k-fail, .st.k-todo, .st.k-drop, .st.k-open { color:var(--dim); }
.in { font-size:12px; font-weight:650; color:var(--wait); white-space:nowrap; }
.in.bad { color:var(--bad); }
time.ago { color:var(--faint); font-size:12px; font-variant-numeric:tabular-nums; white-space:nowrap; }
time.ago.fresh { color:var(--ink2); }
time.ago.stale { color:var(--wait); }

.panel { position:relative; margin-top:22px; padding:8px 14px 10px; background:var(--surface); border:1px solid var(--line); border-radius:14px; }
.panel > svg { position:absolute; left:0; top:0; pointer-events:none; overflow:visible; }
.nd { position:relative; --mid:17px; }
.nd.lv1 { --mid:22px; }
.row { position:relative; display:grid; grid-template-columns:18px 18px minmax(0, 1fr) auto; column-gap:8px; align-items:start;
  min-height:34px; padding:6px 10px 6px 6px; border-radius:9px; cursor:pointer; }
.leaf > .row { cursor:default; }
.row:hover { background:var(--sunken); }
.chev { display:grid; place-items:center; width:18px; height:22px; color:var(--faint); border-radius:5px; }
.chev svg { transition:transform .15s; transform:rotate(90deg); }
.chev b { display:none; }
.nd.closed > .row .chev svg { transform:none; }
.leaf > .row .chev { visibility:hidden; }
.row > .ico { margin-top:3px; }
.main { min-width:0; line-height:22px; overflow-wrap:anywhere; }
.ttl { font-size:13.5px; }
.ttl .id { margin-right:7px; }
.note { color:var(--dim); font-size:13px; }
.note::before { content:"— "; margin-left:7px; color:var(--faint); }
.what { margin:1px 0 0; color:var(--dim); font-size:12.5px; line-height:1.55; }
.what .lnk { margin-left:10px; }
.list .nd.closed > .row .what { display:none; }
.side { display:flex; align-items:center; gap:12px; min-height:22px; padding-left:10px; }
.side time { min-width:5.2em; text-align:right; }
.side .acts { display:none; }
.nd:not(.closed) > .row .in { display:none; }
.lv0 > .row, .lv1 > .row { min-height:44px; padding-block:10px; }
.lv0 > .row .ttl, .lv1 > .row .ttl { font-size:15px; font-weight:650; }
.lv1 > .row .ttl .id { font-size:12px; padding:2px 6px; border-radius:6px; background:var(--sunken); color:var(--ink2); vertical-align:1px; }
.lv0 > .row .note::before, .lv1 > .row .note::before { content:""; margin:0; }
.lv0 > .row .note, .lv1 > .row .note { margin-left:10px; }
.lv1 > .row .note { font-size:13.5px; color:var(--ink2); }
/* 颜色：做完的退后，等你和卡住的整行着色 */
.k-done > .row .ttl { color:var(--ink2); }
.k-todo > .row .ttl { color:var(--dim); }
.k-drop > .row .ttl { color:var(--faint); text-decoration:line-through; }
.k-wait > .row { background:var(--wait-bg); box-shadow:inset 0 0 0 1px var(--wait-line); }
.k-stuck > .row { background:var(--bad-bg); }
.ghost > .row .ttl { font-weight:500; color:var(--dim); }
.more > .row { min-height:28px; color:var(--faint); font-size:12px; cursor:default; }
.more > .row:hover { background:none; }

/* 大纲：缩进，引导线从父行的图标下面拐过来 */
.list .kids { margin-left:16px; }
.list .kids > .nd { padding-left:20px; }
.list .kids > .nd::before { content:""; position:absolute; left:0; top:0; bottom:0; border-left:1.5px solid var(--line2); }
.list .kids > .nd:last-child::before { bottom:auto; height:calc(var(--mid) - 8px); }
.list .kids > .nd::after { content:""; position:absolute; left:0; top:calc(var(--mid) - 9px); width:14px; height:9px;
  border-left:1.5px solid var(--line2); border-bottom:1.5px solid var(--line2); border-bottom-left-radius:8px; }
.list .lv1 { padding-block:4px; }
.list .lv1 + .lv1 > .row::before { content:""; position:absolute; left:0; right:0; top:-5px; border-top:1px solid var(--line); }

/* 分叉图：项目在顶上，会话顺着一根主干往下排，每个会话再一层层向右分叉。
   一个节点是一张小牌，连线跟着孩子的状态上色（连线由脚本画在 svg 里） */
.graph { padding:24px 22px; overflow-x:auto; }
.graph .nd { display:flex; align-items:center; gap:42px; }
.graph .kids { display:flex; flex-direction:column; gap:6px; }
.graph .lv0 { flex-direction:column; align-items:flex-start; gap:16px; }
.graph .lv0 > .kids { gap:16px; margin-left:44px; }
.graph .row { z-index:1; flex:none; width:290px; grid-template-columns:18px minmax(0, 1fr); min-height:0; padding:7px 11px 7px 9px;
  border:1px solid var(--line2); border-radius:10px; background:var(--surface); }
.graph .row:hover { background:var(--surface); filter:brightness(.985); }
.graph .lv1 > .row { width:300px; padding:10px 12px 10px 10px; border-radius:12px; }
.graph .lv0 > .row { width:auto; max-width:100%; padding:9px 16px; grid-template-columns:minmax(0, 1fr); background:var(--ink); border-color:var(--ink); color:var(--bg); }
.graph .lv0 > .row .ico, .graph .lv0 > .row .side { display:none; }
.graph .lv0 > .row .note { display:inline; margin-left:10px !important; font-size:12.5px; color:inherit; opacity:.7; }
.graph .main { line-height:20px; }
.graph .note { display:block; margin:0 !important; font-size:12px; line-height:1.5; }
.graph .note::before { content:none !important; }
.graph .lv1 > .row .note { margin-top:1px !important; font-size:13px; }
.graph .what { display:none; }
.graph .side .acts { display:inline-flex; gap:10px; margin-left:auto; }
.graph .side { grid-column:2; flex-wrap:wrap; justify-content:flex-start; gap:2px 10px; min-height:0; margin-top:4px; padding:0; }
.graph .side time { min-width:0; text-align:left; }
/* 小牌上只留要紧的：会话、收着的、等你的、卡住的才有第三行 */
.graph .nd:not(.lv1):not(.closed):not(.k-wait):not(.k-stuck) > .row .side { display:none; }
.graph .nd:not(.lv1):not(.closed) > .row .meter { display:none; }
.graph .k-done:not(.lv1) > .row time, .graph .k-fail > .row time, .graph .k-drop > .row time { display:none; }
.graph span.chev { display:none; }
.graph .chev { position:absolute; right:-11px; top:50%; z-index:2; transform:translateY(-50%); width:auto; min-width:20px; height:20px; padding:0 6px;
  border:1px solid var(--line2); border-radius:10px; background:var(--surface); color:var(--dim); font-size:11px; font-weight:650; line-height:1; }
.graph .chev:hover { border-color:var(--faint); color:var(--ink); }
.graph .chev svg { display:none; }
.graph .chev b { display:block; font-weight:650; }
.graph .nd.closed > .row .chev { background:var(--ink2); border-color:var(--ink2); color:var(--bg); }
.graph .k-run > .row { border-color:var(--run-solid); background:var(--run-bg); }
.graph .k-wait > .row { border-color:var(--wait-solid); background:var(--wait-bg); box-shadow:0 0 0 3px var(--wait-bg); }
.graph .k-done > .row { border-color:transparent; background:var(--done-bg); }
.graph .k-stuck > .row { border-color:var(--bad-solid); background:var(--bad-bg); }
.graph .k-todo > .row { border-style:dashed; background:transparent; }
.graph .k-fail > .row, .graph .k-drop > .row { border-color:transparent; background:var(--sunken); }
.graph .more > .row { border-style:dashed; background:transparent; grid-template-columns:minmax(0, 1fr); }
.graph .more > .row span:empty { display:none; }

/* 页脚、提示条 */
.foot { display:flex; flex-wrap:wrap; gap:8px 22px; align-items:center; margin-top:30px; padding-top:14px; border-top:1px solid var(--line);
  color:var(--dim); font-size:12px; }
.legend { display:flex; flex-wrap:wrap; gap:6px 14px; }
.legend span { display:inline-flex; align-items:center; gap:5px; }
.toast { position:fixed; left:50%; bottom:26px; z-index:9; max-width:min(90vw, 560px); padding:8px 14px; border-radius:10px;
  background:var(--ink); color:var(--bg); font-size:13px; opacity:0; pointer-events:none;
  transform:translate(-50%, 16px); transition:opacity .2s, transform .2s; }
.toast.on { opacity:1; transform:translate(-50%, 0); }

/* 刚变过的地方亮一下 */
.row.flash { animation:flash 2.8s ease-out; }
.needs li.flash { animation:flashw 2.8s ease-out; }
@keyframes flash { 0%, 30% { box-shadow:0 0 0 4px var(--run-bg), inset 0 0 0 1.5px var(--run-solid); } }
@keyframes flashw { 0%, 30% { background-color:var(--wait-line); } }
@keyframes spin { to { transform:rotate(360deg); } }
@keyframes ping { 0% { box-shadow:0 0 0 0 rgba(47, 158, 104, .45); } 80%, 100% { box-shadow:0 0 0 7px rgba(47, 158, 104, 0); } }

@media (max-width:640px) {
  .wrap { padding-block:20px 40px; padding-left:max(14px, env(safe-area-inset-left, 0px)); padding-right:max(14px, env(safe-area-inset-right, 0px)); }
  h1 { font-size:23px; }
  .panel { padding-inline:6px; }
  .side time, .meter .segs { display:none; }
  .side { gap:8px; padding-left:4px; }
  .list .kids { margin-left:8px; } .list .kids > .nd { padding-left:13px; } .list .kids > .nd::after { width:9px; }
  .ov-g > button { display:none; }
}
@media (prefers-reduced-motion:reduce) { *, *::before, *::after { animation:none !important; transition:none !important; } }
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<noscript><p style="padding:24px">这一页要开着 JavaScript 才能看。也可以直接读同一个文件夹里的 PROGRESS.md。</p></noscript>
<script>window.__DF_BOOT__ = __DATA__;</script>
<script>
(() => {
"use strict";
let D = window.__DF_BOOT__;
const KEY = "demo-first:" + D.project;
const POLL_MS = 5000;   // 多久读一次数据文件
const QUIET_MIN = 30;   // 进行中的会话这么久没记进展，就在时间上说一句。只陈述，不催。
const FRESH_MIN = 5;    // 这么多分钟之内变过的，时间写得深一点
const SETTLED = ["完成", "结束", "不成", "放弃"];
const app = document.getElementById("app"), toastEl = document.getElementById("toast");
const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

// 每个人自己的看法：展开到哪、哪几处自己点开或收起过、收不收做完的、提示音、外观。只存在这个浏览器里。
const ui = {mode: "auto", open: {}, view: "graph", hideDone: false, sound: false, theme: ""};
try {
  const saved = JSON.parse(localStorage.getItem(KEY + ":tree") || "{}");
  for (const k in ui) if (saved && typeof saved[k] === typeof ui[k] && saved[k] !== null) ui[k] = saved[k];
} catch (e) {}
const save = () => { try { localStorage.setItem(KEY + ":tree", JSON.stringify(ui)); } catch (e) {} };
const forced = /[?&]theme=(dark|light)/.exec(location.search);
function applyTheme() {
  const t = forced ? forced[1] : ui.theme;
  if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
}
applyTheme();

// 窗口够宽才排成分叉图，窄了自动是大纲
const wideMQ = window.matchMedia ? matchMedia("(min-width: 1100px)") : {matches: false};
const forcedView = /[?&]view=(graph|list)/.exec(location.search);
const asGraph = () => wideMQ.matches && (forcedView ? forcedView[1] : ui.view) !== "list";
let M = {}, TOP = [], sig = {}, waitKeys = null, lastOk = Date.now(), lastIcon = -1;

const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g,
  c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const pad = n => String(n).padStart(2, "0");
const KIND = {"进行中": "run", "等用户": "wait", "完成": "done", "结束": "done", "不成": "fail", "卡住": "stuck",
  "待做": "todo", "待开": "todo", "放弃": "drop", "已开": "open"};
const kind = s => KIND[s] || "todo";
const label = s => s === "等用户" ? "等你" : s || "没记";
const svg = body => '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">' + body + "</svg>";
const ICON = {
  run: '<span class="spin"></span>',
  wait: svg('<circle cx="8" cy="8" r="7.2" fill="var(--wait-solid)"/><circle cx="8" cy="6" r="2.1" fill="var(--on)"/><path d="M4.3 12.1c.5-2 1.9-3.1 3.7-3.1s3.2 1.1 3.7 3.1" fill="none" stroke="var(--on)" stroke-width="1.7" stroke-linecap="round"/>'),
  done: svg('<circle cx="8" cy="8" r="7.2" fill="var(--done-solid)"/><path d="M4.7 8.3l2.2 2.2 4.4-4.7" fill="none" stroke="var(--on)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'),
  fail: svg('<circle cx="8" cy="8" r="6.4" fill="none" stroke="var(--fail)" stroke-width="1.5"/><path d="M5.7 5.7l4.6 4.6M10.3 5.7l-4.6 4.6" fill="none" stroke="var(--fail)" stroke-width="1.5" stroke-linecap="round"/>'),
  stuck: svg('<path d="M8 1.2l7 12.3H1z" fill="var(--bad-solid)" stroke="var(--bad-solid)" stroke-width="1.2" stroke-linejoin="round"/><path d="M8 6v3.4" fill="none" stroke="var(--on)" stroke-width="1.7" stroke-linecap="round"/><circle cx="8" cy="11.6" r="1" fill="var(--on)"/>'),
  todo: svg('<circle cx="8" cy="8" r="6.2" fill="none" stroke="var(--idle)" stroke-width="1.6"/>'),
  open: svg('<circle cx="8" cy="8" r="6.2" fill="none" stroke="var(--idle)" stroke-width="1.6"/><circle cx="8" cy="8" r="2.2" fill="var(--idle)"/>'),
  drop: svg('<circle cx="8" cy="8" r="6.2" fill="none" stroke="var(--idle)" stroke-width="1.6" stroke-dasharray="2.4 2.4"/><path d="M5.6 8h4.8" fill="none" stroke="var(--idle)" stroke-width="1.6" stroke-linecap="round"/>'),
  queue: svg('<circle cx="8" cy="8" r="6.2" fill="none" stroke="var(--idle)" stroke-width="1.6" stroke-dasharray="2.4 2.4"/>'),
};
const CHEV = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const BELL = '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M8 2.2a3.6 3.6 0 0 0-3.6 3.6c0 2.9-1.2 3.9-1.2 3.9h9.6s-1.2-1-1.2-3.9A3.6 3.6 0 0 0 8 2.2zM6.6 12.2a1.5 1.5 0 0 0 2.8 0" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function hm(d) {  // 按项目的时区显示钟点
  const m = /([+-])(\d\d):(\d\d)$/.exec(D.tz || "");
  if (!m) return pad(d.getHours()) + ":" + pad(d.getMinutes());
  const off = (m[1] === "+" ? 1 : -1) * (m[2] * 60 + +m[3]);
  const t = new Date(d.getTime() + off * 60000);
  return pad(t.getUTCHours()) + ":" + pad(t.getUTCMinutes());
}
const span = ms => { const m = Math.max(0, Math.round(ms / 60000)); return Math.floor(m / 60) + ":" + pad(m % 60); };
const ago = m => m < 1 ? "刚刚" : m < 60 ? m + " 分钟前" : Math.floor(m / 60) + " 小时" + (m % 60 ? " " + (m % 60) + " 分" : "") + "前";
const when = (at, quiet) => at ? '<time class="ago" data-at="' + esc(at) + '"' + (quiet ? ' data-quiet="1"' : "")
  + ' title="' + hm(new Date(at)) + '"></time>' : "";
const sessActs = s => '<button class="lnk" data-act="copy" data-text="' + esc(s.name) + '" title="复制会话的全名，好在任务列表里找到它">复制会话名</button>'
  + (/^https?:/.test(s.link || "") ? '<a class="lnk" href="' + esc(s.link) + '" target="_blank" rel="noopener">打开会话</a>' : "");

// ---------- 把数据理成一棵树 ----------
// 第一层是会话（取自分工表和台账，不用谁来记），往下是各会话自己记的活。
// 每个节点顺手算好：下面最底下的活有哪些（leaves），里面有几处等你、几处卡住，是不是整枝都结束了。

function model() {
  M = {}; TOP = [];
  const add = (id, parent, lv, s) => {
    const n = D.nodes[id] || {};
    const v = M[id] = {id, parent, lv, s: s || null, agent: !!n.agent, kids: [], sup: s ? s.role === "监管者" : M[parent].sup,
      title: s ? (s.role || "") + (s.role && s.title ? " · " : "") + (s.title || "") || s.name || id : n.title || id,
      short: s ? (s.role === "探索者" && s.title) || s.role || s.name || id : n.title || id,
      note: (s ? s.note : n.note) || "", status: (s ? s.status : n.status) || "", at: (s ? s.at : n.at) || ""};
    for (const c of (s ? s.children : n.children) || []) if (D.nodes[c]) v.kids.push(add(c, id, lv + 1).id);
    const below = v.kids.map(k => M[k]);
    v.leaves = below.length ? below.flatMap(k => k.leaves) : [v];
    v.below = below.reduce((n, k) => n + 1 + k.below, 0);
    v.waitIn = below.reduce((n, k) => n + k.waitIn + (k.status === "等用户"), 0);
    v.stuckIn = below.reduce((n, k) => n + k.stuckIn + (k.status === "卡住"), 0);
    v.runIn = below.some(k => k.runIn || k.status === "进行中");
    // 会话开了、自己还没记过状态，但下面的活在动：按进行中显示
    if (s && v.status === "已开" && v.runIn) v.status = "进行中";
    v.settled = SETTLED.includes(v.status) && below.every(k => k.settled);
    v.k = kind(v.status);
    return v;
  };
  for (const s of D.sessions) TOP.push(add(s.id, "", 1, s).id);
  // 调度者没记过小样，就用分工表“小样”一节里写的
  const d = M.D;
  if (d && !d.kids.length) (D.samples || []).forEach((text, i) => {
    const id = "D.小样" + (i + 1);
    M[id] = {id, parent: "D", lv: 2, s: null, agent: false, kids: [], title: text, short: text, note: "", status: "完成", at: "",
      waitIn: 0, stuckIn: 0, runIn: false, settled: true, k: "done", sup: false, label: "小样", below: 0};
    M[id].leaves = [M[id]];
    d.kids.push(id);
    d.below++;
  });
  if (d && d.kids.length && d.leaves[0] === d) d.leaves = d.kids.map(k => M[k]);
}
const isOpen = v => v.kids.length > 0 && (v.id in ui.open ? ui.open[v.id] : ui.mode === "all" ? true : ui.mode === "sessions" ? false : !v.settled);
const path = id => { const out = []; for (let v = M[id]; v; v = M[v.parent]) out.push(v.id); return out; };
function allNodes() { const out = []; const walk = id => { out.push(M[id]); M[id].kids.forEach(walk); }; TOP.forEach(walk); return out; }

// ---------- 画 ----------

function meter(v) {
  if (!v.kids.length) return "";
  const done = v.leaves.filter(n => n.status === "完成").length, what = v.sup ? "条提醒，处理掉 " : "块活，做完 ";
  return '<span class="meter' + (v.leaves.length > 10 ? " many" : "") + '" title="' + v.leaves.length + " " + what + done + '"><span class="segs">'
    + v.leaves.map(n => '<i class="s-' + n.k + '"></i>').join("") + "</span><b>" + done + "/" + v.leaves.length + "</b></span>";
}
function node(id) {
  const v = M[id], s = v.s, open = isOpen(v);
  sig[id] = [v.status, v.title, v.note, v.at].join("|");
  const word = ["wait", "stuck", "fail", "drop"].includes(v.k) ? '<span class="st k-' + v.k + '">' + esc(label(v.status)) + "</span>"
    : s && s.status === "待开" ? '<span class="st k-todo">还没开</span>' : "";
  let kids = "";
  if (open) {
    let hidden = 0;
    for (const c of v.kids) { if (ui.hideDone && M[c].settled) hidden++; else kids += node(c); }
    if (hidden) kids += '<div class="nd more lv' + (v.lv + 1) + '"><div class="row"><span></span><span></span><span>结束的 ' + hidden + " 块收起了</span></div></div>";
  }
  return '<div class="nd lv' + v.lv + " k-" + v.k + (v.kids.length ? open ? "" : " closed" : " leaf") + (s && s.status === "待开" ? " ghost" : "")
    + '" data-key="' + esc(id) + '" data-k="' + v.k + '"><div class="row" data-id="' + esc(id) + '"' + (s && s.what ? ' title="' + esc(s.what) + '"' : "") + ">"
    + (v.kids.length ? '<button class="chev" data-act="toggle" data-id="' + esc(id) + '" aria-expanded="' + open + '" aria-label="' + (open ? "收起" : "展开")
      + '" title="' + (open ? "收起" : "展开下面的 " + v.below + " 块") + '">' + CHEV + "<b>" + (open ? "−" : "+" + v.below) + "</b></button>" : '<span class="chev"></span>')
    + '<span class="ico" title="' + esc(label(v.status)) + '">' + ICON[v.k] + "</span>"
    + '<div class="main"><span class="ttl"><span class="id">' + esc(v.label || id) + "</span>" + (v.agent ? '<span class="tag">子代理</span>' : "") + esc(v.title) + "</span>"
    + (v.note ? '<span class="note">' + esc(v.note) + "</span>" : "")
    + (s ? '<p class="what"><span class="what-t">' + esc(s.what || "") + (s.effort ? (s.what ? " · " : "") + "思考强度 " + esc(s.effort) : "") + "</span>" + sessActs(s) + "</p>" : "") + "</div>"
    + '<span class="side">' + (v.waitIn ? '<span class="in">里面 ' + v.waitIn + " 处等你</span>" : "") + (v.stuckIn ? '<span class="in bad">' + v.stuckIn + " 处卡住</span>" : "")
    + meter(v) + word + when(v.at, s && v.status === "进行中") + (s ? '<span class="acts">' + sessActs(s) + "</span>" : "") + "</span></div>"
    + (kids ? '<div class="kids">' + kids + "</div>" : "") + "</div>";
}
function tree() {
  const queue = D.queue || [];
  const body = TOP.filter(id => !(ui.hideDone && M[id].settled)).map(node).join("")
    + queue.map(text => '<div class="nd lv1 leaf ghost k-todo" data-k="todo"><div class="row"><span class="chev"></span><span class="ico" title="排队">' + ICON.queue + "</span>"
      + '<div class="main"><span class="ttl"><span class="id">排队</span>' + esc(text) + '</span></div><span class="side"><span class="st k-todo">还没开</span></span></div></div>').join("");
  const gone = TOP.filter(id => ui.hideDone && M[id].settled).length;
  return '<section class="panel ' + (asGraph() ? "graph" : "list") + '" id="tree"><svg id="links" aria-hidden="true"></svg><div class="nd lv0"><div class="row" style="cursor:default"><span class="chev"></span><span class="ico">' + ICON.open + "</span>"
    + '<div class="main"><span class="ttl">' + esc(D.project) + '</span><span class="note">' + (TOP.length ? "拆成 " + TOP.length + " 个会话" : "分工定下来之后，各个会话会出现在这里")
    + (queue.length ? "，" + queue.length + " 个排队" : "") + (gone ? "，结束的 " + gone + " 个收起了" : "") + '</span></div><span class="side"></span></div>'
    + (body ? '<div class="kids">' + body + "</div>" : "") + "</div></section>";
}

// 分叉图的连线：从父节点的右边中点，画到每个孩子的左边中点，颜色跟着孩子的状态
const LINK = {run: "var(--run-solid)", wait: "var(--wait-solid)", done: "var(--done-solid)", stuck: "var(--bad-solid)", fail: "var(--fail)"};
function links() {
  const box = document.getElementById("tree"), pic = document.getElementById("links");
  if (!box || !pic) return;
  if (!box.classList.contains("graph")) { pic.innerHTML = ""; return; }
  const o = box.getBoundingClientRect(), dx = box.scrollLeft - o.left - box.clientLeft, dy = box.scrollTop - o.top - box.clientTop, out = [];
  const line = (d, k) => '<path d="' + d + '" fill="none" stroke-linecap="round" stroke="' + (LINK[k] || "var(--line2)") + '" stroke-width="'
    + (k === "run" || k === "wait" || k === "stuck" ? 2 : 1.5) + '"' + (k === "todo" || k === "drop" ? ' stroke-dasharray="4 4"' : "") + "/>";
  for (const kids of box.querySelectorAll(".kids")) {
    const p = kids.previousElementSibling.getBoundingClientRect(), x1 = p.right + dx, y1 = p.top + p.height / 2 + dy;
    if (kids.parentNode.classList.contains("lv0")) {
      // 第一层：一根主干从项目往下，每个会话一个拐弯
      const tx = p.left + dx + 20, R = 10;
      let end = p.bottom + dy;
      for (const c of kids.children) {
        const r = c.firstElementChild.getBoundingClientRect(), y = r.top + Math.min(r.height / 2, 28) + dy, x2 = r.left + dx;
        out.push(line("M" + tx + " " + (y - R).toFixed(1) + "Q" + tx + " " + y.toFixed(1) + " " + (tx + R) + " " + y.toFixed(1) + "H" + x2.toFixed(1), c.dataset.k));
        end = y - R;
      }
      out.unshift(line("M" + tx + " " + (p.bottom + dy).toFixed(1) + "V" + end.toFixed(1), "trunk"));
      continue;
    }
    for (const c of kids.children) {
      const r = c.firstElementChild.getBoundingClientRect(), x2 = r.left + dx, y2 = r.top + r.height / 2 + dy, mx = (x1 + x2) / 2, k = c.dataset.k;
      out.push(line("M" + x1.toFixed(1) + " " + y1.toFixed(1) + "C" + mx.toFixed(1) + " " + y1.toFixed(1) + " " + mx.toFixed(1) + " " + y2.toFixed(1) + " " + x2.toFixed(1) + " " + y2.toFixed(1), k));
    }
  }
  pic.setAttribute("width", box.scrollWidth); pic.setAttribute("height", box.scrollHeight);
  pic.innerHTML = out.join("");
}

function overall(wait) {
  const groups = TOP.map(id => M[id]).filter(v => !v.sup);
  const work = groups.flatMap(v => v.leaves), all = allNodes();
  const count = k => work.filter(n => n.k === k).length, stuck = all.filter(n => n.status === "卡住").length;
  const chip = (k, n, text) => '<span class="ov-chip k-' + k + (n ? "" : " zero") + '">' + ICON[k] + n + " " + text + "</span>";
  if (!work.length) return "";
  return '<section class="overall"><div class="ov-nums"><span><b>' + count("done") + "<small>/" + work.length + "</small></b> 块活做完</span>"
    + chip("run", count("run"), "进行中") + chip("wait", wait.length, "处等你") + chip("stuck", stuck, "卡住") + chip("todo", count("todo") + count("open"), "待做") + "</div>"
    + '<div class="ov-bar">' + groups.map(v => '<div class="ov-g" style="flex:' + v.leaves.length + '"><div class="segs">'
      + v.leaves.map(n => '<i class="s-' + n.k + '" data-act="goto" data-go="' + esc(n.id) + '" title="' + esc(n.id + " " + n.title + "：" + label(n.status)) + '"></i>').join("")
      + '</div><button data-act="goto" data-go="' + esc(v.id) + '"><em>' + esc(v.id) + "</em>" + esc(v.short) + "</button></div>").join("") + "</div></section>";
}

function needs(wait) {
  // 监管者记的提醒里，还没处理、也不是在等你的：单列出来，这是它给你的简报
  const notes = allNodes().filter(v => v.sup && v.lv === 2 && ["待做", "进行中", "卡住"].includes(v.status));
  const says = v => v.s ? v.note || "在等你" : v.title + (v.note ? " — " + v.note : "");
  let out = "";
  if (wait.length) {
    out += '<section class="needs"><h2>' + ICON.wait + wait.length + " 处等你</h2><ul>" + wait.map(v => {
      const s = M[path(v.id).pop()], key = "need:" + v.id;
      sig[key] = [v.note, v.at].join("|");
      return '<li data-key="' + esc(key) + '"><b>去 ' + esc(s.title) + '</b><span class="id">' + esc(v.id) + "</span>"
        + '<button class="go" data-act="goto" data-go="' + esc(v.id) + '" title="在树上找到它">' + esc(says(v)) + "</button>" + when(v.at) + sessActs(s.s) + "</li>";
    }).join("") + "</ul></section>";
  } else if (TOP.length) {
    out += '<section class="needs calm">现在没有等你处理的事。</section>';
  }
  if (notes.length) out += '<section class="notes"><h2>监管者的提醒<small>' + notes.length + " 条没处理</small></h2><ul>" + notes.map(v =>
    '<li><span class="ico">' + ICON[v.k] + '</span><span class="id">' + esc(v.id) + '</span><button class="go" data-act="goto" data-go="' + esc(v.id) + '" title="在树上找到它">'
    + esc(says(v)) + "</button>" + when(v.at) + "</li>").join("") + "</ul></section>";
  return out;
}

function render(animate) {
  const old = sig, top = scrollY;
  sig = {};
  model();
  const wait = allNodes().filter(v => v.status === "等用户").sort((a, b) => (b.at || "").localeCompare(a.at || ""));
  for (const v of allNodes()) sig[v.id] = [v.status, v.title, v.note, v.at].join("|");
  const legend = [["run", "进行中"], ["wait", "等你"], ["done", "完成"], ["stuck", "卡住"], ["fail", "不成"], ["todo", "待做"], ["drop", "放弃"]];
  const modeName = {auto: "自动", all: "全部", sessions: "只到会话"}[ui.mode], themeName = {"": "自动", light: "浅色", dark: "深色"}[ui.theme] || "自动";
  app.innerHTML = '<header class="top"><div><p class="eyebrow">全景</p><h1>' + esc(D.project) + "</h1>"
    + (D.goal ? '<p class="goal">' + esc(D.goal) + "</p>" : "") + '<p class="pace" id="pace"></p></div>'
    + '<div class="tools"><span class="live" id="live"><i></i><span></span></span>'
    + '<button class="btn" data-act="sound" aria-pressed="' + ui.sound + '" title="有新的事等你处理时响一声">' + BELL + "提示音</button>"
    + '<button class="btn" data-act="hide" aria-pressed="' + ui.hideDone + '" title="把整枝都结束了的收起来">只看没结束的</button>'
    + '<button class="btn" data-act="mode" title="自动：没结束的展开，结束的收起。点一下换成全部展开，再点一下只展开到会话">展开：' + modeName + "</button>"
    + (wideMQ.matches && !forcedView ? '<button class="btn" data-act="view" title="分叉图：一层层向右分叉。大纲：一行一块，更省地方。窗口窄的时候总是大纲">排法：' + (asGraph() ? "分叉图" : "大纲") + "</button>" : "")
    + (forced ? "" : '<button class="btn" data-act="theme" title="换外观">外观：' + themeName + "</button>") + "</div></header>"
    + overall(wait) + needs(wait) + tree()
    + '<footer class="foot"><span class="legend">' + legend.map(([k, t]) => "<span>" + ICON[k] + t + "</span>").join("") + "</span>"
    + "<span>各会话自己报的进展，由 coord/progress.py 汇成这一页。要紧的地方以监管者的巡检为准。</span></footer>";
  app.classList.toggle("wide", asGraph());
  tick();
  links();
  if (animate) {
    // 变过的那一行亮一下；它被收在里面看不见，就亮它上面看得见的那一行
    for (const key in sig) {
      if (old[key] === sig[key]) continue;
      let el = null;
      if (key.startsWith("need:")) el = find(key);
      else for (const id of path(key)) if ((el = find(id))) { el = el.firstElementChild; break; }
      if (el) el.classList.add("flash");
    }
    if (Math.abs(scrollY - top) > 1) scrollTo(0, top);
  }
  const keys = wait.map(v => v.id);
  if (waitKeys && ui.sound && keys.some(k => !waitKeys.includes(k))) beep();
  waitKeys = keys;
  document.title = (keys.length ? "(" + keys.length + ") " : "") + D.project + " · 全景";
  favicon(keys.length);
}

function tick() {
  const now = new Date(), start = D.start ? new Date(D.start) : null, end = D.deadline ? new Date(D.deadline) : null;
  const pace = document.getElementById("pace");
  // 这一页不催任何人。期限是用户自己定的，定了才显示，只给用户看。
  if (pace) pace.textContent = [start && now >= start ? "已进行 " + span(now - start) : "", !end ? "没有设期限，节奏由你掌握"
    : now < end ? "你定的期限 " + hm(end) + "，还有 " + span(end - now) : "已经过了你定的期限 " + span(now - end)].filter(Boolean).join(" · ");
  for (const el of app.querySelectorAll("time[data-at]")) {
    const m = Math.max(0, Math.round((now - new Date(el.dataset.at)) / 60000));
    const quiet = !!el.dataset.quiet && m >= QUIET_MIN;
    el.textContent = quiet ? ago(m).replace(/前$/, "") + "没有新记录" : ago(m);
    el.classList.toggle("stale", quiet);
    el.classList.toggle("fresh", m < FRESH_MIN);
  }
  const live = document.getElementById("live");
  if (live) {
    const off = Date.now() - lastOk > 4 * POLL_MS;
    live.classList.toggle("off", off);
    live.lastChild.textContent = off ? "读不到更新" : "实时 · 更新于 " + hm(new Date(D.generated));
  }
}

// ---------- 动作 ----------

let toastTimer = 0;
function toast(text) {
  toastEl.textContent = text;
  toastEl.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("on"), 2600);
}
function copy(text) {
  const ok = () => toast("已复制：" + text);
  const byHand = () => {
    const box = document.createElement("textarea");
    box.value = text; box.style.position = "fixed"; box.style.opacity = "0";
    document.body.appendChild(box); box.select();
    let done = false;
    try { done = document.execCommand("copy"); } catch (e) {}
    box.remove();
    done ? ok() : toast("没复制成。会话名是：" + text);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, byHand); else byHand();
}
const find = key => app.querySelector('[data-key="' + String(key).replace(/["\\]/g, "") + '"]');
function goTo(id) {  // 在树上找到它：把它上面的都展开，滚过去，亮一下
  if (!M[id]) return;
  const up = path(id).slice(1);
  let changed = false;
  for (const a of up) if (!isOpen(M[a])) { ui.open[a] = true; changed = true; }
  if (ui.hideDone && path(id).some(a => M[a].settled)) { ui.hideDone = false; changed = true; }
  if (changed) { save(); render(false); }
  const el = find(id);
  if (!el) return;
  const row = el.firstElementChild;
  row.scrollIntoView({behavior: reduce ? "auto" : "smooth", block: "center"});
  row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash");
}
let audio = null;
function beep() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    if (audio.state === "suspended") audio.resume();
    const t = audio.currentTime;
    [880, 1175].forEach((hz, i) => {
      const osc = audio.createOscillator(), gain = audio.createGain(), at = t + i * 0.17;
      osc.type = "sine"; osc.frequency.value = hz;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.linearRampToValueAtTime(0.14, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.32);
      osc.connect(gain); gain.connect(audio.destination);
      osc.start(at); osc.stop(at + 0.34);
    });
  } catch (e) {}
}
function favicon(n) {
  if (n === lastIcon) return;
  lastIcon = n;
  try {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const x = c.getContext("2d");
    x.fillStyle = n ? "#ee9d16" : "#1d1c19";
    x.beginPath();
    if (x.roundRect) x.roundRect(0, 0, 64, 64, 16); else x.rect(0, 0, 64, 64);
    x.fill();
    x.fillStyle = "#fff"; x.textAlign = "center"; x.textBaseline = "middle";
    x.font = "700 40px 'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif";
    x.fillText(n ? String(Math.min(n, 9)) : "景", 32, 35);
    let link = document.querySelector("link[rel=icon]");
    if (!link) { link = document.createElement("link"); link.rel = "icon"; document.head.appendChild(link); }
    link.href = c.toDataURL("image/png");
  } catch (e) {}
}

app.addEventListener("click", e => {
  const a = e.target.closest("[data-act]");
  const row = !a && !e.target.closest("a, button") && e.target.closest(".row[data-id]");
  const act = a ? a.dataset.act : row ? "toggle" : "";
  const id = a ? a.dataset.id : row ? row.dataset.id : "";
  if (act === "toggle") {
    const v = M[id];
    if (!v || !v.kids.length) return;
    if (getSelection && String(getSelection())) return;  // 在选字，不是要收起
    ui.open[id] = !isOpen(v);
  } else if (act === "mode") {
    ui.mode = {auto: "all", all: "sessions", sessions: "auto"}[ui.mode] || "auto";
    ui.open = {};  // 换一种展开法，之前一处一处点的就不算了
  } else if (act === "view") {
    ui.view = asGraph() ? "list" : "graph";
  } else if (act === "hide") {
    ui.hideDone = !ui.hideDone;
  } else if (act === "sound") {
    ui.sound = !ui.sound;
    if (ui.sound) { beep(); toast("开了。有新的事等你处理时会响一声；刷新页面后要先在页面上点一下，浏览器才让它响。"); }
  } else if (act === "theme") {
    ui.theme = {"": "light", light: "dark", dark: ""}[ui.theme] || "";
    applyTheme();
  } else if (act === "copy") {
    copy(a.dataset.text || ""); return;
  } else if (act === "goto") {
    goTo(a.dataset.go || ""); return;
  } else {
    return;
  }
  save();
  render(false);
});
// 浏览器要等用户在页面上点过一下，才让页面出声。
document.addEventListener("pointerdown", () => { if (ui.sound && audio && audio.state === "suspended") audio.resume(); });

// ---------- 自己更新 ----------

// progress.data.js 里只有一句：把最新的数据交给下面这个函数。用 <script> 去读，直接双击打开的页面也读得了。
window.__demoFirstUpdate = data => {
  lastOk = Date.now();
  if (!data || data.v !== D.v) {  // 页面的样子换过了：整页重读一次，一分钟内不重复
    try {
      const k = KEY + ":reload";
      if (Date.now() - (+sessionStorage.getItem(k) || 0) > 60000) { sessionStorage.setItem(k, String(Date.now())); location.reload(); }
    } catch (e) {}
    return;
  }
  if (JSON.stringify(data) === JSON.stringify(D)) { tick(); return; }
  D = data;
  render(true);
};
function poll() {
  const tag = document.createElement("script");
  tag.src = "progress.data.js?t=" + Date.now();
  tag.onload = tag.onerror = () => tag.remove();
  document.head.appendChild(tag);
}

render(false);
// 窗口变宽变窄：过了那条线就换排法，没过也要把连线重画一遍
let wasGraph = asGraph(), linkTimer = 0;
addEventListener("resize", () => {
  if (asGraph() !== wasGraph) { wasGraph = asGraph(); render(false); return; }
  clearTimeout(linkTimer);
  linkTimer = setTimeout(links, 60);
});
setInterval(tick, 15000);
setInterval(poll, POLL_MS);
poll();
})();
</script>
</body>
</html>
"""

PAGE_VERSION = hashlib.md5(PAGE.encode("utf-8")).hexdigest()[:10]


def iso_at(at, tz_label):
    """进展记录里的 “2026-03-14 15:02” 配上时区，给网页算“几分钟前”。"""
    return at.replace(" ", "T") + ":00" + (tz_label or "") if at else ""


def page_data(tree):
    """网页要的数据：和 build() 给的是同一棵树，钟点都配上时区。"""
    tz = tree["tz"]
    return {
        "v": PAGE_VERSION, "project": tree["project"], "goal": tree["goal"], "tz": tz,
        "start": tree["start"], "deadline": tree["deadline"], "generated": tree["generated"],
        "sessions": [dict(session, at=iso_at(session["at"], tz)) for session in tree["sessions"]],
        "nodes": {key: dict(item, at=iso_at(item["at"], tz)) for key, item in tree["nodes"].items()},
        "samples": tree["samples"], "queue": tree["queue"],
    }


def render_html(tree):
    blob = json.dumps(page_data(tree), ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    return PAGE.replace("__TITLE__", html.escape("%s · 全景" % tree["project"])).replace("__DATA__", blob)


def render_data_js(tree):
    """开着的页面每几秒读一次这个文件。"""
    return "window.__demoFirstUpdate && window.__demoFirstUpdate(%s);\n" % json.dumps(page_data(tree), ensure_ascii=False)


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
    """重新生成 PROGRESS.md、progress.html 和 progress.data.js。返回这棵树。"""
    coord = Path(coord)
    tree = build(coord)
    write_atomic(coord / "PROGRESS.md", render_md(tree))
    write_atomic(coord / "progress.html", render_html(tree))
    write_atomic(coord / "progress.data.js", render_data_js(tree))
    return tree


# ---------- 记 ----------

def parse_triples(tokens):
    """把命令行上的一串词切成 [(编号, 状态, 文字, 是不是子代理)]。文字可以不写；“子代理”写在编号后面，可以不写。"""
    triples, at = [], 0
    while at < len(tokens):
        node_id = tokens[at]
        if not ID.match(node_id):
            die("“%s”不是编号。编号接在会话编号后面，例如 E1.1、E1.2、E1.1.1。" % node_id)
        agent = at + 1 < len(tokens) and tokens[at + 1] == AGENT
        if agent:
            at += 1
        if at + 1 >= len(tokens) or tokens[at + 1] not in STATUSES:
            die("编号 %s 后面要跟状态，只能是：%s。" % (node_id, "、".join(STATUSES)))
        status, text, at = tokens[at + 1], "", at + 2
        starts_next = at + 1 < len(tokens) and ID.match(tokens[at]) and tokens[at + 1] in STATUSES + [AGENT]
        if at < len(tokens) and not starts_next:
            text, at = tokens[at], at + 1
        triples.append((node_id, status, " ".join(text.replace("｜", "/").split()), agent and "." in node_id))
    return triples


def record(coord, triples, stamp):
    folder = coord / "progress"
    folder.mkdir(parents=True, exist_ok=True)
    by_file = {}
    for node_id, status, text, agent in triples:
        by_file.setdefault(node_id.split(".")[0], []).append(
            "- %s｜%s｜%s｜%s%s" % (stamp, node_id, status, text, "｜" + AGENT if agent else ""))
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
    zone = read_json(coord / "ledger.json").get("tz")
    tz = parse_tz(zone)
    now = now_in(tz)
    if triples:
        record(coord, triples, now.strftime("%Y-%m-%d %H:%M"))
    tree = rebuild(coord)
    for node_id, status, text, agent in triples:
        print("已记：%s %s %s%s" % (node_id, status, text, "（子代理）" if agent else ""))
        if len(text) > TEXT_HINT:
            print("  提醒：这句有 %d 个字。全景是给人扫一眼的，下次压到 20 个字以内。" % len(text))
    wait = waiting(tree)
    print("全景已更新：%s（%d 个会话%s）" % (coord / "progress.html", len(tree["sessions"]),
                                    "，%d 处等用户" % len(wait) if wait else ""))
    # 各会话自己看钟点时看到的是机器的时间，和这里记的对不上。所以每次都把项目钟点说出来。
    print("项目钟点：%s%s。回报、巡检和记录里写钟点都照它，不用机器自己的时间。"
          % (now.strftime("%H:%M"), "（%s）" % zone if tz else ""))


if __name__ == "__main__":
    main()
