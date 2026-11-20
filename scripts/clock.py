#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每一轮巡检开头运行：现在几点、剩多少时间、过了哪个关口、哪个时间盒超了。

用法：
  python3 clock.py              只看时间
  python3 clock.py --card       同时生成这一份阶段报告的草稿 coord/reports/<序号>.md（序号加一）
  python3 clock.py --done E1    把 E1 记成已结束：不再提醒它的时间盒，也不再占并行名额
  python3 clock.py --reopen E1  记错了，改回进行中

退出码：0 成功；2 参数有问题或没找到台账。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

# 每个阶段一句话：现在该做什么。顺序和关口一致。
PHASES = [
    ("kickoff_end", "立项", "发出开工确认，等用户回“开”。"),
    ("explore_end", "试与建", "探索者试，总建设者搭骨架。探索定稿一个，就落地一个。"),
    ("freeze", "落地", "探索已截止。还没结论的探索，现在就要它在成、不成、降级方案里选一个。剩下的时间用来落地。"),
    ("deliver", "收尾", "功能已冻结，只修不加。把监管者的延后清单交给用户挑。"),
    ("deadline", "交付", "只做交付：在线上链接上逐条走验收项，写交付说明。"),
]
GATE_LABELS = [
    ("kickoff_end", "立项截止"),
    ("explore_end", "探索截止"),
    ("freeze", "功能冻结"),
    ("deliver", "开始交付"),
    ("deadline", "交付"),
]


def current_phase(now, points):
    for key, name, hint in PHASES:
        if now < points[key]:
            return name, hint
    return "已过交付时间", "马上交出现有的东西，在交付说明里写明没做完的。"


def main():
    c.setup_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=".", help="台账所在的目录（里面有 coord/ 的那一层），默认当前目录")
    parser.add_argument("--card", action="store_true", help="生成阶段报告的草稿，序号加一")
    parser.add_argument("--done", nargs="+", metavar="编号", help="把这些任务记成已结束")
    parser.add_argument("--reopen", nargs="+", metavar="编号", help="把这些任务改回进行中")
    args = parser.parse_args()

    ledger = c.load_ledger(args.dir)
    briefs = ledger.setdefault("briefs", {})
    changed = False

    for ids, status in ((args.done, "done"), (args.reopen, "open")):
        for task_id in ids or []:
            if task_id not in briefs:
                known = "、".join(sorted(briefs)) or "（还没有）"
                c.die("台账里没有编号为 %s 的派工单。现有的：%s" % (task_id, known))
            briefs[task_id]["status"] = status
            changed = True
            print("%s 已记成%s。" % (task_id, "已结束" if status == "done" else "进行中"))

    tz = c.parse_tz(ledger["tz"])
    now = c.now_in(tz)
    start = c.from_iso(ledger["start"])
    deadline = c.from_iso(ledger["deadline"])
    points = {k: c.from_iso(v) for k, v in ledger["gates"].items()}
    points["deadline"] = deadline

    if args.done or args.reopen:
        print()

    if now < start:
        print("现在 %s（%s）｜还没开始，离开始还有 %s｜总时长 %s"
              % (c.hm(now, start), ledger["tz"], c.span(start - now), c.span(deadline - start)))
        phase, hint = "立项", PHASES[0][2]
        elapsed_text, left_text = "0:00", c.span(deadline - start)
    else:
        phase, hint = current_phase(now, points)
        if phase == "立项" and briefs:
            # 已经生成过派工单，说明立项做完了：不再按钟点把阶段报成“立项”。
            phase, hint = PHASES[1][1], PHASES[1][2]
        elapsed_text = c.span(now - start)
        if now < deadline:
            left_text = c.span(deadline - now)
            print("现在 %s（%s）｜已用 %s，剩 %s｜总时长 %s"
                  % (c.hm(now, start), ledger["tz"], elapsed_text, left_text, c.span(deadline - start)))
        else:
            left_text = "0:00"
            print("现在 %s（%s）｜已用 %s，超时 %s｜总时长 %s"
                  % (c.hm(now, start), ledger["tz"], elapsed_text, c.span(now - deadline), c.span(deadline - start)))
    print("按时间现在该在：%s。%s" % (phase, hint))
    print()

    print("关口")
    for key, label in GATE_LABELS:
        at = points[key]
        if now >= at:
            print("  [过] %s  %s" % (label.ljust(4, "　"), c.hm(at, start)))
        else:
            print("  [  ] %s  %s  还有 %s" % (label.ljust(4, "　"), c.hm(at, start), c.span(at - now)))

    open_briefs = [(k, v) for k, v in briefs.items() if v.get("status") != "done"]
    if open_briefs:
        print()
        print("没结束的任务")
        open_briefs.sort(key=lambda kv: kv[1].get("box_end") or "9999")
        for task_id, info in open_briefs:
            role = c.ROLE_NAMES.get(info.get("role"), info.get("role", ""))
            line = "  %s  %s  %s" % (task_id, role, info.get("title", ""))
            if info.get("box_end"):
                end = c.from_iso(info["box_end"])
                if now >= end:
                    line += "｜时间盒到 %s，已超 %s" % (c.hm(end, start), c.span(now - end))
                    if info.get("role") == "explorer":
                        line += " ← 发消息要它三选一：成、不成、降级方案"
                    elif info.get("role") == "lead-builder":
                        # 总建设者要留到交付负责发布，所以过了时间盒也不算“该结束了”。
                        line += " ← 骨架和接入位该交了，没交就读它的回报"
                    else:
                        line += " ← 读它的回报，看卡在哪"
                else:
                    line += "｜时间盒到 %s，还有 %s" % (c.hm(end, start), c.span(end - now))
            print(line)
        print("  （任务结束后运行 clock.py --done <编号>，它就不再出现在这里）")

    caps = ledger.get("caps", {})
    if caps.get("explorers"):
        running = {"explorer": 0, "builder": 0, "supervisor": 0}
        for _, info in open_briefs:
            role = info.get("role", "")
            key = "builder" if role.endswith("builder") else role
            if key in running:
                running[key] += 1
        print()
        print("在跑：探索者 %d/%d，建设者 %d/%d，监管者 %d/%d"
              % (running["explorer"], caps["explorers"], running["builder"], caps["builders"],
                 running["supervisor"], caps["supervisors"]))

    if args.card:
        ledger["report_seq"] = int(ledger.get("report_seq", 0)) + 1
        changed = True
        seq = ledger["report_seq"]
        if now >= deadline:
            header = "【阶段报告 #%d｜已用 %s，已超时 %s｜阶段：%s】" % (seq, elapsed_text, c.span(now - deadline), phase)
        else:
            header = "【阶段报告 #%d｜已用 %s，剩 %s｜阶段：%s】" % (seq, elapsed_text, left_text, phase)
        # 报告先写成文件：发出前能检查，发出后留在台账里，接手的人看得到之前跟用户说过什么。
        rel = "%s/reports/%d.md" % (c.LEDGER_DIR, seq)
        draft = c.fill(c.read_text(c.TEMPLATE_DIR / "coord" / "REPORT.md"), {"抬头": header})
        c.write_text(Path(args.dir) / c.LEDGER_DIR / "reports" / ("%d.md" % seq), draft)
        checker = str(Path(__file__).resolve().parent / "check_brief.py")
        if " " in checker:
            checker = '"%s"' % checker
        python = Path(sys.executable).stem if sys.executable else "python3"
        print()
        print("阶段报告的草稿：%s（抬头已经填好）" % rel)
        print("  " + header)
        print("填完运行：%s %s %s，通过后把全文发给用户" % (python, checker, rel))

    if changed:
        c.save_ledger(args.dir, ledger)


if __name__ == "__main__":
    main()
