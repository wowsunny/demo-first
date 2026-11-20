#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一份要发出去的草稿，已知的内容先填好，剩下的 {{…}} 由你来填。

分工确认（发给用户，写完 CHARTER.md 和 BOARD.md 之后运行）：
  python3 new_brief.py kickoff                      生成 coord/KICKOFF.md

派工单（发给新会话，生成到 coord/briefs/<编号>.md）。顺序：探索者 → 建设者 → 监管者：
  python3 new_brief.py explorer E1 "发言节奏"       探索者必须写细分
  python3 new_brief.py builder B1                   建设者只有一个，细分可以不写
  python3 new_brief.py supervisor S1

每份派工单生成后，脚本会给出三样，开任务时照着指定：
  会话名      项目短名 - 角色 - 细分
  思考强度    默认探索者、建设者超高，监管者极致；要改用 --effort
  要附什么    后开的会话要引用先开的，所以每开一个就把任务链接记进 BOARD.md，再生成下一份
同名文件已存在时不覆盖，除非加 --force。超过会话上限时不生成，除非加 --over-cap。

退出码：0 成功；2 参数有问题、没找到台账、前置文件没写完、同名文件已存在，或超过会话上限。
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

ALIASES = {
    "kickoff": "kickoff", "分工确认": "kickoff", "开工确认": "kickoff",
    "explorer": "explorer", "探索者": "explorer",
    "builder": "builder", "建设者": "builder",
    "lead-builder": "builder", "lead": "builder", "总建设者": "builder",
    "supervisor": "supervisor", "监管者": "supervisor",
}
RETIRED = ("landing-builder", "landing", "落地建设者")

# 这两个角色要拿初始设定当基准，所以把全文嵌进派工单。
NEEDS_CHARTER = ("builder", "supervisor")

# 思考强度分四档，各平台叫法不同，生成派工单时一并说出来，免得再去翻适配文件。
# 一律写明、不用平台的默认档：有的平台默认继承开它的会话（太重），有的默认最低档（太轻）。
EFFORT_NAMES = {
    "标准": "标准", "standard": "标准", "medium": "标准",
    "高": "高", "high": "高",
    "超高": "超高", "xhigh": "超高", "extra": "超高",
    "极致": "极致", "最高": "极致", "max": "极致", "ultra": "极致",
}
EFFORT_ON_PLATFORM = {
    "标准": "Manus 是标准模式 standard；Claude Code 是 medium",
    "高": "Manus 是 Max 的高档 max-high；Claude Code 是 high",
    "超高": "Manus 是 Max 的超高档 max-extra；Claude Code 是 xhigh",
    "极致": "Manus 是 Max 的极致档 max-ultra；Claude Code 是 max",
}
# 探索者和建设者要把用户的要求吃透、再组织子代理去做，用超高。
# 监管者用极致：它的用处就是找出别的会话和子代理想得不够深留下的问题。
DEFAULT_EFFORT = {"explorer": "超高", "builder": "超高", "supervisor": "极致"}

CHECKER = Path(__file__).resolve().parent / "check_brief.py"


def python_name():
    """现在用的解释器叫什么（python3 或 python）。写进派工单和提示里，对方照抄就能跑。"""
    return Path(sys.executable).stem if sys.executable else "python3"


def cap_problems(role, task_id, ledger):
    """这份派工单会不会超过会话上限。返回每一条超限的说明。"""
    caps = ledger.get("caps", {})
    problems = []
    open_ids = [(k, v.get("role", "")) for k, v in ledger.get("briefs", {}).items()
                if v.get("status") != "done" and k != task_id]
    if role == "explorer" and caps.get("explorers"):
        running = [k for k, r in open_ids if r == "explorer"]
        if len(running) >= caps["explorers"]:
            problems.append("探索者到了会话上限（%d 个）：%s 还没结束。把这一个留在 BOARD.md 的“待探索”里，"
                            "等前面的有了结论、运行过 clock.py --done <编号>，再来生成。"
                            % (caps["explorers"], "、".join(running)))
    if role == "builder":
        running = [k for k, r in open_ids if r.endswith("builder")]
        if running:
            problems.append("已经有建设者 %s 了。正式项目只归一个会话：要并行的活，由它在内部分给子代理。"
                            % running[0])
    if role == "supervisor":
        running = [k for k, r in open_ids if r == "supervisor"]
        if running:
            problems.append("已经有监管者 %s 了。要换一个冷启动的监管者，先把旧的记成结束：clock.py --done %s。"
                            % (running[0], running[0]))
    return problems


def session_lines(base, ledger, only=None, skip=None):
    """从分工表里列出会话，一行一个：编号｜会话名｜要做的事｜任务链接。

    返回 (行, 没记链接的编号)。分工表认不出来时返回 (None, [])。
    """
    tasks = c.board_tasks(base)
    if tasks is None:
        return None, []
    lines, no_link = [], []
    for task in tasks:
        key = c.role_key(task["role"])
        if task["id"] == skip or (only and key != only):
            continue
        name = c.session_name(ledger, key or task["role"], task["title"])
        link = task["link"]
        if not link:
            no_link.append(task["id"])
            link = "（链接还没记）"
        lines.append("- %s｜%s｜%s｜%s" % (task["id"], name, task["what"], link))
    return lines, no_link


def finish(rel, text, notes):
    for note in notes:
        print("注意：" + note)
    todo = c.placeholders(text)
    if todo:
        print("还要你填的 %d 处：" % len(todo))
        for item in todo:
            print("  - " + item)
    checker = str(CHECKER)
    if " " in checker:
        checker = '"%s"' % checker
    print("填完运行：%s %s %s" % (python_name(), checker, rel))


def make_kickoff(base, ledger, force):
    target = base / c.LEDGER_DIR / "KICKOFF.md"
    rel = "%s/KICKOFF.md" % c.LEDGER_DIR
    if target.exists() and not force:
        c.die("%s 已经存在。接着改它就行；初始设定或分工变了要重新生成，加 --force。" % rel)

    charter, missing = c.charter_text(base)
    if charter is None:
        c.die("没找到 coord/CHARTER.md。先运行 init_ledger.py。")
    if missing:
        c.die("coord/CHARTER.md 还没写完，里面还有 %d 处 {{…}}，例如 %s。写完再生成分工确认。"
              % (len(missing), missing[0]))

    tasks = c.board_tasks(base)
    if tasks is None:
        c.die("coord/BOARD.md 的分工表认不出来了（表头要有“编号”“角色”“细分”“要回答的问题 / 要交付的”这几列）。照模板改回来。")
    if not tasks:
        c.die("coord/BOARD.md 里还没有会话。先把分工写进表里，一个会话一行，再生成分工确认。")
    lines, notes = [], []
    roles = []
    for task in tasks:
        key = c.role_key(task["role"])
        roles.append(key)
        if key is None:
            notes.append("分工表里 %s 的角色“%s”不认识。只能是：探索者、建设者、监管者。" % (task["id"], task["role"]))
        if key == "explorer" and not task["title"]:
            notes.append("分工表里 %s 没写细分。探索者的会话名要有第三段，说明它试的是什么。" % task["id"])
        lines.append("- %s（%s）｜%s" % (c.session_name(ledger, key or task["role"], task["title"]), task["id"], task["what"]))
    lines += ["- 待探索，现在不开：%s" % item for item in c.board_list(base, "待探索")]
    if roles.count("builder") != 1:
        notes.append("分工表里要有、也只能有一个建设者。改好 BOARD.md，再加 --force 重新生成。")
    if "supervisor" not in roles:
        notes.append("分工表里没有监管者。在 BOARD.md 里补一行，再加 --force 重新生成。")
    cap = ledger.get("caps", {}).get("explorers")
    if cap and roles.count("explorer") > cap:
        notes.append("分工表里有 %d 个探索者，超过了同时 %d 个的上限。把后开的挪进“待探索”，再加 --force 重新生成。"
                     % (roles.count("explorer"), cap))

    values, _ = c.base_values(ledger)
    values["初始设定全文"] = charter
    values["分工"] = "\n".join(lines)
    text = c.fill(c.read_text(c.TEMPLATE_DIR / "coord" / "KICKOFF.md"), values)
    c.write_text(target, text)
    c.refresh_progress(base)  # 分工表写好了，全景里就看得到要开哪些会话

    print("已生成 %s（初始设定和 %d 个会话已经填进去）" % (rel, len(tasks)))
    finish(rel, text, notes)


def make_brief(base, ledger, role, task_id, title, force, over_cap, effort=None):
    if effort and effort.lower() not in EFFORT_NAMES:
        c.die("--effort 只能是：标准、高、超高、极致（也可以写 standard、high、xhigh、max）。")
    effort = EFFORT_NAMES[effort.lower()] if effort else DEFAULT_EFFORT[role]
    if not task_id:
        c.die("派工单要有编号，例如：new_brief.py %s %s1" % (role, role[0].upper()))
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", task_id):
        c.die("编号“%s”不合规矩。写成 E1、E2、B1、S1。" % task_id)
    if role == "explorer" and not title:
        c.die("探索者要写细分，它是会话名的第三段，例如：new_brief.py explorer %s \"发言节奏\"" % task_id)

    target = base / c.LEDGER_DIR / "briefs" / (task_id + ".md")
    rel = "%s/briefs/%s.md" % (c.LEDGER_DIR, task_id)
    if target.exists() and not force:
        c.die("%s 已经存在。接着改它就行；确实要重新生成，加 --force。" % rel)
    template = c.TEMPLATE_DIR / ("brief-%s.md" % role)
    rules = c.TEMPLATE_DIR / "rules-subagent.md"
    for needed in (template, rules):
        if not needed.exists():
            c.die("没找到模板 %s。技能目录不完整，重新安装本技能。" % needed)

    over = cap_problems(role, task_id, ledger)
    if over and not over_cap:
        c.die("现在不该开这个会话，派工单没有生成。\n  " + "\n  ".join(over)
              + "\n  想清楚了确实要多开，加 --over-cap。")

    values, tz = c.base_values(ledger)
    now = c.now_in(tz)
    notes = []

    name = c.session_name(ledger, role, title)
    values.update({
        "任务名": name, "编号": task_id, "python": python_name(),
        "子代理规矩": c.embed_text(c.read_text(rules)),
    })
    if role in NEEDS_CHARTER:
        charter, missing = c.charter_text(base)
        if charter and not missing:
            values["初始设定全文"] = charter
        else:
            notes.append("coord/CHARTER.md 还没写完，初始设定没能自动填进来。先写完它，再加 --force 重新生成。")

    # 建设者要知道有哪些探索在跑，监管者要知道全部会话：从分工表里取，不用再抄一遍。
    attach = ""
    if role in ("builder", "supervisor"):
        key = "探索清单" if role == "builder" else "会话清单"
        lines, no_link = session_lines(base, ledger, only="explorer" if role == "builder" else None, skip=task_id)
        if lines is None:
            notes.append("coord/BOARD.md 的分工表认不出来，“%s”要你手工填。" % key)
        else:
            lines += ["- 待探索，还没开：%s" % item for item in c.board_list(base, "待探索")]
            values[key] = "\n".join(lines) if lines else "（现在没有）"
            if no_link:
                notes.append("分工表里 %s 的任务链接还没记。先开它们、把链接记进 BOARD.md，再加 --force 重新生成；"
                             "它们确实还没开，就在派工单里把那一行改成“还没开”。" % "、".join(no_link))
        if role == "builder":
            attach = "把探索者的任务都作为任务引用附上：它落地时要去读移交说明和 demo。"
        else:
            attach = "把其他所有会话的任务、连同你自己这个任务，都作为任务引用附上：它要读得到全部。"

    text = c.fill(c.read_text(template), values)
    c.write_text(target, text)
    ledger.setdefault("briefs", {})[task_id] = {
        "role": role,
        "title": title,
        "name": name,
        "created": now.isoformat(),
        "effort": effort,
        "status": "open",
    }
    c.save_ledger(base, ledger)
    c.refresh_progress(base)

    print("已生成 %s（%s）" % (rel, c.ROLE_NAMES[role]))
    print("开任务时照这三样指定，不用平台默认的：")
    print("  会话名：%s" % name)
    print("  思考强度：%s（%s）" % (effort, EFFORT_ON_PLATFORM[effort]))
    print("  要附的：%s" % (attach or "没有。"))
    finish(rel, text, notes + ["超过了会话上限，按你的要求照样生成了。"] * bool(over))


def main():
    c.setup_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", metavar="种类", help="kickoff / explorer / builder / supervisor")
    parser.add_argument("task_id", metavar="编号", nargs="?", help="派工单的编号，例如 E1、B1、S1")
    parser.add_argument("title", metavar="细分", nargs="?", help="会话名的第三段：这个会话具体管什么。探索者必须写")
    parser.add_argument("--dir", default=".", help="台账所在的目录（里面有 coord/ 的那一层），默认当前目录")
    parser.add_argument("--force", action="store_true", help="同名文件已存在时覆盖它")
    parser.add_argument("--over-cap", action="store_true", help="超过会话上限也照样生成")
    parser.add_argument("--effort", metavar="强度", help="这个会话的思考强度：标准、高、超高、极致。不写就按角色的默认")
    args = parser.parse_args()

    raw = args.kind.strip().lower()
    if raw in RETIRED:
        c.die("不再单开落地建设者：落地由建设者会话自己做，要并行就由它分给子代理。"
              "探索定稿后，请用户去建设者的会话说一句“<编号> 定稿了”。")
    kind = ALIASES.get(raw)
    if not kind:
        c.die("不认识“%s”。可用的：kickoff、explorer、builder、supervisor。" % args.kind)
    ledger = c.load_ledger(args.dir)
    base = Path(args.dir).resolve()

    if kind == "kickoff":
        make_kickoff(base, ledger, args.force)
    else:
        make_brief(base, ledger, kind, (args.task_id or "").strip(), (args.title or "").strip(),
                   args.force, args.over_cap, (args.effort or "").strip() or None)


if __name__ == "__main__":
    main()
