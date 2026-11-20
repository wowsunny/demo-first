#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看一眼：项目进行了多久、哪些会话还开着。被叫回来时先运行它。

用法：
  python3 clock.py              只看
  python3 clock.py --card       同时生成这一份阶段报告的草稿 coord/reports/<序号>.md（序号加一）
  python3 clock.py --done E1    把 E1 记成已结束：不再占会话名额
  python3 clock.py --reopen E1  记错了，改回进行中

它不催任何人：节奏由用户掌握。用户自己定过期限的话，这里会顺带显示离期限还有多久。
退出码：0 成功；2 参数有问题或没找到台账。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402


def main():
    c.setup_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=".", help="台账所在的目录（里面有 coord/ 的那一层），默认当前目录")
    parser.add_argument("--card", action="store_true", help="生成阶段报告的草稿，序号加一")
    parser.add_argument("--done", nargs="+", metavar="编号", help="把这些会话记成已结束")
    parser.add_argument("--reopen", nargs="+", metavar="编号", help="把这些会话改回进行中")
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
    if args.done or args.reopen:
        print()

    tz = c.parse_tz(ledger["tz"])
    now = c.now_in(tz)
    start = c.from_iso(ledger["start"])
    deadline = c.from_iso(ledger["deadline"]) if ledger.get("deadline") else None

    running = c.span(now - start) if now >= start else "0:00"
    if deadline is None:
        limit = "没有设期限"
    elif now < deadline:
        limit = "用户定的期限 %s，还有 %s" % (c.hm(deadline, now), c.span(deadline - now))
    else:
        limit = "用户定的期限 %s，已经过了 %s" % (c.hm(deadline, now), c.span(now - deadline))
    print("现在 %s（%s）｜已进行 %s｜%s" % (c.hm(now, start), ledger["tz"], running, limit))

    open_briefs = [(k, v) for k, v in briefs.items() if v.get("status") != "done"]
    if not briefs:
        print("还没开出会话：现在在深聊。聊清楚了就定分工，发分工确认。")
    elif open_briefs:
        print()
        print("没结束的会话")
        for task_id, info in open_briefs:
            name = info.get("name") or c.session_name(ledger, info.get("role", ""), info.get("title", ""))
            line = "  %s  %s" % (task_id, name)
            if info.get("created"):
                line += "｜开了 %s" % c.span(now - c.from_iso(info["created"]))
            print(line)
        print("  （会话结束后运行 clock.py --done <编号>，它就不再出现在这里）")
    else:
        print("会话都结束了。")

    if briefs:
        counts = {"explorer": 0, "builder": 0, "supervisor": 0}
        for _, info in open_briefs:
            role = info.get("role", "")
            key = "builder" if role.endswith("builder") else role
            if key in counts:
                counts[key] += 1
        cap = ledger.get("caps", {}).get("explorers")
        explorers = ("%d/%d" % (counts["explorer"], cap)) if cap else str(counts["explorer"])
        print()
        print("在跑：探索者 %s，建设者 %d/1，监管者 %d/1" % (explorers, counts["builder"], counts["supervisor"]))

    if args.card:
        ledger["report_seq"] = int(ledger.get("report_seq", 0)) + 1
        changed = True
        seq = ledger["report_seq"]
        header = "【阶段报告 #%d｜%s｜已进行 %s】" % (seq, c.hm(now, start), running)
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
    c.refresh_progress(args.dir)  # 顺手把全景更新一遍：分工表里新记的链接、刚结束的会话都反映进去


if __name__ == "__main__":
    main()
