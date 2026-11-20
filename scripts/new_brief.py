#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一份要发出去的草稿，已知的内容先填好，剩下的 {{…}} 由你来填。

开工确认（发给用户，写完 CHARTER.md 和 BOARD.md 之后运行）：
  python3 new_brief.py kickoff                      生成 coord/KICKOFF.md

派工单（发给新任务，生成到 coord/briefs/<编号>.md）：
  python3 new_brief.py explorer E1 "语音转文字走哪条路"
  python3 new_brief.py lead-builder B1 "边界、架构和骨架"
  python3 new_brief.py landing-builder B2 "把语音输入写进正式项目" --handoff E1
  python3 new_brief.py supervisor S1 "全局巡检"

落地建设者加 --handoff <探索者编号>：把 coord/handoffs/<编号>.md 的全文填进派工单，不用你再抄一遍。
时间盒从生成那一刻起算，默认按角色定，要改用 --box 分钟数。所以派工单现生成现发，不要提前囤。
同名文件已存在时不覆盖，除非加 --force。超过并行上限时不生成，除非加 --over-cap。

退出码：0 成功；2 参数有问题、没找到台账、前置文件没写完、同名文件已存在，或超过并行上限。
"""

import argparse
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

ALIASES = {
    "kickoff": "kickoff", "开工确认": "kickoff",
    "explorer": "explorer", "探索者": "explorer",
    "lead-builder": "lead-builder", "lead": "lead-builder", "总建设者": "lead-builder",
    "landing-builder": "landing-builder", "landing": "landing-builder", "落地建设者": "landing-builder",
    "supervisor": "supervisor", "监管者": "supervisor",
}

# 这两个角色要拿初始设定当基准，所以把全文嵌进派工单。
NEEDS_CHARTER = ("lead-builder", "supervisor")

# 落地建设者默认的时间盒，见 default_box_end 里的说明。
LANDING_WINDOW = 0.20
LANDING_BUFFER = 0.05

CHECKER = Path(__file__).resolve().parent / "check_brief.py"


def default_box_end(role, now, ledger):
    """各角色默认的时间盒截止时间。"""
    gates = {k: c.from_iso(v) for k, v in ledger["gates"].items()}
    if role == "explorer":
        # 不超过单个探索的上限，也不越过探索截止。
        limit = now + timedelta(minutes=ledger["caps"]["explorer_box_minutes"])
        return min(limit, gates["explore_end"]) if now < gates["explore_end"] else limit
    if role == "lead-builder":
        # 落地从探索截止开始，骨架和接入位要在那之前就位。
        return gates["explore_end"] if now < gates["explore_end"] else gates["freeze"]
    if role == "landing-builder":
        # 落地的窗口是探索截止到功能冻结，正好是总时长的两成，所以一块落地最多给这么久。
        # 还要在功能冻结前留出总时长的 5%，给总建设者同步、检查、发布。
        total = c.from_iso(ledger["deadline"]) - c.from_iso(ledger["start"])
        end = min(now + total * LANDING_WINDOW, gates["freeze"] - total * LANDING_BUFFER)
        if end <= now:  # 已经贴近或过了功能冻结：只剩修补，最晚到开始交付
            end = min(now + total * LANDING_WINDOW, gates["deliver"])
        return end.replace(second=0, microsecond=0)
    return c.from_iso(ledger["deadline"])  # 监管者一直工作到交付


def cap_problems(role, task_id, ledger):
    """这份派工单会不会超过并行上限。返回每一条超限的说明。"""
    caps = ledger.get("caps", {})
    problems = []
    open_ids = [(k, v.get("role", "")) for k, v in ledger.get("briefs", {}).items()
                if v.get("status") != "done" and k != task_id]
    if role == "explorer" and caps.get("explorers"):
        running = [k for k, r in open_ids if r == "explorer"]
        if len(running) >= caps["explorers"]:
            problems.append("探索者到了并行上限（%d 个）：%s 还没结束。把这一个记进 BOARD.md 的“排队”，"
                            "等前面的有了结论、运行过 clock.py --done <编号>，再来生成。"
                            % (caps["explorers"], "、".join(running)))
    if role.endswith("builder") and caps.get("builders"):
        running = [k for k, r in open_ids if r.endswith("builder")]
        if len(running) >= caps["builders"]:
            problems.append("建设者到了并行上限（%d 个）：%s 还没结束。这一块不开新任务，"
                            "把移交说明全文发给总建设者，由它来落地。" % (caps["builders"], "、".join(running)))
    if role == "supervisor":
        running = [k for k, r in open_ids if r == "supervisor"]
        if running:
            problems.append("已经有监管者 %s 了。要换一个冷启动的监管者，先把旧的记成结束：clock.py --done %s。"
                            % (running[0], running[0]))
    if caps.get("levels") and task_id.count(".") >= caps["levels"]:
        problems.append("编号 %s 是第 %d 层，超过了任务树的层数上限（%d 层）。把它并回上一层，或者等上层有了结论再开。"
                        % (task_id, task_id.count(".") + 1, caps["levels"]))
    return problems


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
    # 用和现在同一个解释器名（python3 或 python），照抄就能跑。
    python = Path(sys.executable).stem if sys.executable else "python3"
    print("填完运行：%s %s %s" % (python, checker, rel))


def make_kickoff(base, ledger, force):
    target = base / c.LEDGER_DIR / "KICKOFF.md"
    rel = "%s/KICKOFF.md" % c.LEDGER_DIR
    if target.exists() and not force:
        c.die("%s 已经存在。接着改它就行；初始设定或任务树变了要重新生成，加 --force。" % rel)

    charter, missing = c.charter_text(base)
    if charter is None:
        c.die("没找到 coord/CHARTER.md。先运行 init_ledger.py。")
    if missing:
        c.die("coord/CHARTER.md 还没写完，里面还有 %d 处 {{…}}，例如 %s。写完再生成开工确认。"
              % (len(missing), missing[0]))

    tasks = c.board_tasks(base)
    if tasks is None:
        c.die("coord/BOARD.md 的任务表认不出来了（表头要有“编号”“角色”“要回答的问题 / 要交付的”三列）。照模板改回来。")
    if not tasks:
        c.die("coord/BOARD.md 里还没有任务。先把任务树写进表里，一个任务一行，再生成开工确认。")
    lines = ["- %s %s｜%s" % task for task in tasks]
    lines += ["- 排队：%s" % item for item in c.board_queue(base)]

    values, _ = c.time_values(ledger)
    values["初始设定全文"] = charter
    values["任务树"] = "\n".join(lines)
    text = c.fill(c.read_text(c.TEMPLATE_DIR / "coord" / "KICKOFF.md"), values)
    c.write_text(target, text)

    print("已生成 %s（初始设定和 %d 个任务已经填进去）" % (rel, len(tasks)))
    finish(rel, text, ["任务树里没有监管者。在 BOARD.md 里补一行，再加 --force 重新生成。"]
           if not any(role.startswith("监管者") for _, role, _ in tasks) else [])


def make_brief(base, ledger, role, task_id, title, box, force, over_cap, handoff=None):
    if not task_id or not title:
        c.die("派工单要有编号和标题，例如：new_brief.py %s E1 \"一句话说这个任务管什么\"" % role)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(\.[0-9]+)*", task_id):
        c.die("编号“%s”不合规矩。写成 E1、B2、S1；子方向接在上级后面，例如 E1.1。" % task_id)

    target = base / c.LEDGER_DIR / "briefs" / (task_id + ".md")
    rel = "%s/briefs/%s.md" % (c.LEDGER_DIR, task_id)
    if target.exists() and not force:
        c.die("%s 已经存在。接着改它就行；确实要重新生成，加 --force。" % rel)
    template = c.TEMPLATE_DIR / ("brief-%s.md" % role)
    if not template.exists():
        c.die("没找到模板 %s。技能目录不完整，重新安装本技能。" % template)

    handoff_text = None
    if handoff:
        if role != "landing-builder":
            c.die("--handoff 只给落地建设者用：它把探索者的移交说明填进落地派工单。")
        source = base / c.LEDGER_DIR / "handoffs" / (handoff + ".md")
        if not source.exists():
            c.die("没找到 %s/handoffs/%s.md。先把探索者 %s 贴出来的移交说明全文存成这个文件，再来生成。"
                  % (c.LEDGER_DIR, handoff, handoff))
        handoff_text = c.read_text(source).strip()

    over = cap_problems(role, task_id, ledger)
    if over and not over_cap:
        # 派工单的时间盒从生成那一刻起算，所以排队的任务现在不生成。
        c.die("现在不该开这个任务，派工单没有生成。\n  " + "\n  ".join(over)
              + "\n  想清楚了确实要多开，加 --over-cap。")

    values, tz = c.time_values(ledger)
    now = c.now_in(tz)
    start = c.from_iso(ledger["start"])
    deadline = c.from_iso(ledger["deadline"])
    notes = []

    if box is not None:
        if box <= 0:
            c.die("--box 要是正数（分钟）。")
        box_end = now + timedelta(minutes=box)
        cap = ledger["caps"]["explorer_box_minutes"]
        if role == "explorer" and box > cap:
            notes.append("时间盒 %d 分钟，超过了单个探索的上限（%d 分钟）。问题太大就拆成两个探索者。" % (box, cap))
    else:
        box_end = default_box_end(role, now, ledger)
    if box_end > deadline:
        box_end = deadline
        notes.append("时间盒超过了交付时间，已经改成交付时间。")

    values.update({"编号": task_id, "标题": title, "现在": c.hm(now, start), "时间盒截止": c.hm(box_end, start)})
    if handoff_text:
        values["移交说明全文"] = handoff_text
    if role in NEEDS_CHARTER:
        charter, missing = c.charter_text(base)
        if charter and not missing:
            values["初始设定全文"] = charter
        else:
            notes.append("coord/CHARTER.md 还没写完，初始设定没能自动填进来。先写完它，再加 --force 重新生成。")

    text = c.fill(c.read_text(template), values)
    c.write_text(target, text)
    ledger.setdefault("briefs", {})[task_id] = {
        "role": role,
        "title": title,
        "created": now.isoformat(),
        "box_end": None if role == "supervisor" else box_end.isoformat(),
        "status": "open",
    }
    c.save_ledger(base, ledger)

    if role == "supervisor":
        print("已生成 %s（%s）" % (rel, c.ROLE_NAMES[role]))
    else:
        print("已生成 %s（%s，时间盒到 %s）" % (rel, c.ROLE_NAMES[role], c.hm(box_end, start)))
    finish(rel, text, notes + ["超过了并行上限，按你的要求照样生成了。"] * bool(over))


def main():
    c.setup_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", metavar="种类", help="kickoff / explorer / lead-builder / landing-builder / supervisor")
    parser.add_argument("task_id", metavar="编号", nargs="?", help="派工单的编号，例如 E1、E1.1、B1、S1")
    parser.add_argument("title", metavar="标题", nargs="?", help="一句话说这个任务管什么")
    parser.add_argument("--box", type=int, metavar="分钟", help="时间盒，从现在算起多少分钟")
    parser.add_argument("--dir", default=".", help="台账所在的目录（里面有 coord/ 的那一层），默认当前目录")
    parser.add_argument("--force", action="store_true", help="同名文件已存在时覆盖它")
    parser.add_argument("--over-cap", action="store_true", help="超过并行上限也照样生成")
    parser.add_argument("--handoff", metavar="编号", help="只给落地建设者：把 coord/handoffs/<编号>.md 的全文填进派工单")
    args = parser.parse_args()

    kind = ALIASES.get(args.kind.strip().lower())
    if not kind:
        c.die("不认识“%s”。可用的：kickoff、explorer、lead-builder、landing-builder、supervisor。" % args.kind)
    ledger = c.load_ledger(args.dir)
    base = Path(args.dir).resolve()

    if kind == "kickoff":
        make_kickoff(base, ledger, args.force)
    else:
        make_brief(base, ledger, kind, (args.task_id or "").strip(), (args.title or "").strip(),
                   args.box, args.force, args.over_cap, (args.handoff or "").strip() or None)


if __name__ == "__main__":
    main()
