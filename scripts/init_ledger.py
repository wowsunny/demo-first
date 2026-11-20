#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""立项时运行一次：建好台账目录 coord/，算出时间关口和并行上限。

用法：
  python3 init_ledger.py --goal "一句话目标" --hours 4 --tz +08:00
  python3 init_ledger.py --goal "一句话目标" --deadline "2026-11-22 18:30" --tz +08:00
  python3 init_ledger.py --goal "一句话目标" --deadline 18:30 --start 14:30 --tz +08:00

台账已经存在时不会覆盖，只提示怎么接着做。交付时间变了，用 --retime 重算关口：
  python3 init_ledger.py --retime --deadline 19:00

退出码：0 成功；2 参数有问题；3 台账已经存在。
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

# 三个关口各占总时长的比例。
# 探索截止 50%：过半还没试出结论，剩下的时间就不够把结论写进正式项目了。
# 功能冻结 70%：留出两成时间只修不加，最后联调时总会冒出问题。
# 开始交付 90%：留一成时间逐条验收、写交付说明。
EXPLORE_END = 0.50
FREEZE = 0.70
DELIVER = 0.90

# 立项占总时长的 5%：再多就挤占了试和建的时间。
# 下限 10 分钟：写清初始设定和任务树至少要这么久。
# 上限 60 分钟：按天算的项目，立项也不该拖过一小时。
KICKOFF_SHARE = 0.05
KICKOFF_MIN = timedelta(minutes=10)
KICKOFF_MAX = timedelta(minutes=60)

# 单个探索的时间盒不超过总时长的 15%：一个问题占得再多，就该拆小或者降级了。
EXPLORER_BOX_SHARE = 0.15

# 不到一天算冲刺档。冲刺档限制并行数量，因为每多一个任务，用户就多一处要看的地方。
SPRINT_LIMIT = timedelta(hours=24)
SPRINT_CAPS = {"explorers": 2, "builders": 2, "supervisors": 1, "levels": 2}

FILES = ["CHARTER.md", "BOARD.md", "DECISIONS.md"]


def build_times(start, deadline):
    total = deadline - start
    kickoff = min(max(total * KICKOFF_SHARE, KICKOFF_MIN), KICKOFF_MAX)
    gates = {
        "kickoff_end": start + kickoff,
        "explore_end": start + total * EXPLORE_END,
        "freeze": start + total * FREEZE,
        "deliver": start + total * DELIVER,
    }
    gates = {k: v.replace(second=0, microsecond=0) for k, v in gates.items()}
    sprint = total <= SPRINT_LIMIT
    box = max(1, int(total.total_seconds() * EXPLORER_BOX_SHARE // 60))
    caps = dict(SPRINT_CAPS) if sprint else {"explorers": None, "builders": None, "supervisors": 1, "levels": None}
    caps["explorer_box_minutes"] = box
    return total, gates, ("sprint" if sprint else "project"), caps


def describe(ledger):
    start = c.from_iso(ledger["start"])
    deadline = c.from_iso(ledger["deadline"])
    gates = {k: c.from_iso(v) for k, v in ledger["gates"].items()}
    caps = ledger["caps"]
    mode = "冲刺档" if ledger["mode"] == "sprint" else "项目档"
    lines = [
        "总时长 %s（%s），时区 %s" % (c.span(deadline - start), mode, ledger["tz"]),
        "  开始      %s" % c.hm(start, start),
        "  立项截止  %s   到点还没发出开工确认，就砍掉细节先发" % c.hm(gates["kickoff_end"], start),
        "  探索截止  %s   到点每个探索都要定稿，或给出降级方案" % c.hm(gates["explore_end"], start),
        "  功能冻结  %s   到点只修不加" % c.hm(gates["freeze"], start),
        "  开始交付  %s   到点只做交付" % c.hm(gates["deliver"], start),
        "  交付      %s" % c.hm(deadline, start),
        "",
    ]
    if ledger["mode"] == "sprint":
        lines.append(
            "并行上限：同时最多 %d 个探索者、%d 个建设者（含总建设者）、%d 个监管者；任务树最多 %d 层"
            % (caps["explorers"], caps["builders"], caps["supervisors"], caps["levels"])
        )
    else:
        lines.append("并行上限：探索者和建设者不设上限，监管者 1 个。先读 references/long-project.md")
    box = caps["explorer_box_minutes"]
    if box < 120:
        lines.append("单个探索的时间盒：最长 %d 分钟" % box)
    else:
        lines.append("单个探索的时间盒：最长约 %d 小时" % round(box / 60))
    return "\n".join(lines)


def main():
    c.setup_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--goal", help="一句话目标，会写进初始设定和每份派工单")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--hours", type=float, help="从开始时间算起，总共多少小时")
    group.add_argument("--deadline", help="交付时间，例如 “2026-11-22 18:30” 或 18:30")
    parser.add_argument("--tz", help="用户的时区，写成和 UTC 的时差，例如 +08:00")
    parser.add_argument("--start", help="开始时间，默认是现在。计时早就开始了的时候用")
    parser.add_argument("--dir", default=".", help="台账建在哪个目录下，默认是当前目录")
    parser.add_argument("--retime", action="store_true", help="台账已存在，只按新的时间重算关口")
    args = parser.parse_args()

    base = Path(args.dir).resolve()
    coord = base / c.LEDGER_DIR
    exists = c.ledger_path(base).exists()

    if exists and not args.retime:
        print("台账已经在 %s 里了，这个项目立过项。不要重新立项：" % coord)
        print("  1. 运行 clock.py 看现在到哪个关口了；")
        print("  2. 读 coord/BOARD.md，从 SKILL.md 的第 3 步（巡检）接着做。")
        print("交付时间变了，才用 --retime 加新的 --deadline 或 --hours 重算关口。")
        sys.exit(3)

    if args.retime:
        if not exists:
            c.die("--retime 是给已有台账重算时间用的，这里还没有台账。去掉 --retime 再运行。")
        ledger = c.load_ledger(base)
        tz = c.parse_tz(args.tz or ledger["tz"])
        now = c.now_in(tz)
        start = c.parse_clock(args.start, tz, now, nearest=True) if args.start else c.from_iso(ledger["start"])
        if args.hours is not None:
            deadline = start + timedelta(hours=args.hours)
        elif args.deadline:
            deadline = c.parse_clock(args.deadline, tz, start)
        else:
            c.die("--retime 需要一个新的 --deadline 或 --hours。")
    else:
        if not args.goal:
            c.die("缺 --goal：用一句话写清要做什么。")
        if not args.tz:
            c.die("缺 --tz：写用户所在的时区，例如 +08:00。不确定就问用户，别猜。")
        if args.hours is None and not args.deadline:
            c.die("缺总时长：用 --hours 4，或用 --deadline 18:30 写交付时间。不确定就问用户。")
        tz = c.parse_tz(args.tz)
        now = c.now_in(tz)
        start = c.parse_clock(args.start, tz, now, nearest=True) if args.start else now
        if args.hours is not None:
            deadline = start + timedelta(hours=args.hours)
        else:
            deadline = c.parse_clock(args.deadline, tz, start)
        ledger = {"version": 1, "goal": args.goal.strip(), "report_seq": 0, "briefs": {}}

    if deadline <= start:
        c.die("交付时间 %s 不晚于开始时间 %s。" % (c.hm(deadline), c.hm(start)))
    total, gates, mode, caps = build_times(start, deadline)

    ledger.update({
        "tz": c.tz_label(tz),
        "start": start.isoformat(),
        "deadline": deadline.isoformat(),
        "mode": mode,
        "gates": {k: v.isoformat() for k, v in gates.items()},
        "caps": caps,
    })
    c.save_ledger(base, ledger)

    if args.retime:
        print("已按新的时间重算关口（%s 里的其他文件没动）。\n" % coord)
        print(describe(ledger))
        print("\n下一步：把新的关口抄进 coord/CHARTER.md 的时间表，记一条到 coord/DECISIONS.md，")
        print("        再把新的时间发给所有任务。")
        return

    values, _ = c.time_values(ledger, now)
    made = [c.LEDGER_NAME]
    for name in FILES:
        target = coord / name
        if target.exists():
            continue  # 已经有人写过的文件不动
        c.write_text(target, c.fill(c.read_text(c.TEMPLATE_DIR / "coord" / name), values))
        made.append(name)
    instruction = coord / "PROJECT_INSTRUCTION.md"
    if not instruction.exists():
        c.write_text(instruction, c.fill(c.read_text(c.TEMPLATE_DIR / "project-instruction.md"), values))
        made.append(instruction.name)
    for folder in ("briefs", "handoffs"):
        (coord / folder).mkdir(parents=True, exist_ok=True)
        made.append(folder + "/")

    print("台账建在 %s" % coord)
    print("  " + "  ".join(made))
    print()
    if total < timedelta(hours=1):
        print("提醒：总时长不到一小时。这么短的活拆成多个任务，开销比收益大，直接在一个任务里做更快。\n")
    print(describe(ledger))
    print()
    print("下一步：写完 coord/CHARTER.md → 把任务树写进 coord/BOARD.md → 运行 new_brief.py kickoff 生成开工确认")


if __name__ == "__main__":
    main()
