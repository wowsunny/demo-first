#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深聊开头运行一次：建好台账目录 coord/。

用法：
  python3 init_ledger.py --name 项目短名 --goal "一句话目标"
  python3 init_ledger.py --name 项目短名 --goal "一句话目标" --tz -05:00

项目短名十个字以内，所有会话的名字都用它开头：项目短名 - 角色 - 细分。
钟点统一按 +08:00（北京、新加坡）换算和记录，和机器自己的时区无关；用户明说要别的时区才写 --tz。

各会话是不是共用一个文件夹，决定派工单怎么发、建设者什么时候开（见 new_brief.py）。脚本自己猜：
在 Windows、macOS 上运行，当成用户自己的电脑，记“共用”；在 Linux 上运行，当成云端的机器，记“不共用”。
猜得不对，或者后来发现不对，随时改（台账已存在时只改这一项）：
  python3 init_ledger.py --shared                         各会话共用这个文件夹
  python3 init_ledger.py --not-shared                     各会话各有各的机器

节奏由用户掌握：脚本不设期限，也不给各会话定时间盒。用户自己提到了期限，才记下来，
它只显示在全景页上给用户看，不写进派工单：
  python3 init_ledger.py --name 项目短名 --goal "一句话目标" --deadline "2026-03-14 18:30"
  python3 init_ledger.py --retime --deadline 19:00        台账已存在，改期限
  python3 init_ledger.py --retime --no-deadline           台账已存在，去掉期限

台账已经存在时不会覆盖，只提示怎么接着做。
退出码：0 成功；2 参数有问题；3 台账已经存在。
"""

import argparse
import shutil
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

# 同时开着的探索者不超过 3 个。这个数和时间无关：每多一个会话，用户就多一处要去的地方。
# 建设者和监管者都只有一个：正式项目只归一个会话，落地由它内部的子代理分担。
EXPLORERS_AT_ONCE = 3

FILES = ["CHARTER.md", "CONTEXT.md", "BOARD.md", "DECISIONS.md"]

# 钟点统一按这个时区换算和记录。机器自己的时区靠不住：云端的机器、系统时区没调过的电脑，
# 都会和用户看的钟点对不上。
DEFAULT_TZ = "+08:00"


def describe(ledger, now):
    start = c.from_iso(ledger["start"])
    lines = ["项目“%s”｜开始 %s（%s）" % (c.project_name(ledger), c.hm(start, now), ledger["tz"])]
    if ledger.get("deadline"):
        deadline = c.from_iso(ledger["deadline"])
        left = "还有 %s" % c.span(deadline - now) if now < deadline else "已经过了 %s" % c.span(now - deadline)
        lines.append("用户定的期限：%s（%s）。它只显示在全景页上给用户看，不写进派工单。" % (c.hm(deadline, now), left))
    else:
        lines.append("没有设期限：节奏由用户掌握。")
    lines.append("会话上限：同时最多 %d 个探索者；建设者 1 个，监管者 1 个" % ledger["caps"]["explorers"])
    lines.append(describe_shared(ledger))
    return "\n".join(lines)


def describe_shared(ledger):
    if c.is_shared(ledger):
        return ("各会话：共用这个文件夹。派工单只发路径，建设者第一个开，全景页可用。"
                "开出来的会话说读不到派工单，就运行 init_ledger.py --not-shared。")
    return ("各会话：各有各的机器，互相看不到文件。派工单发全文，后开的会话靠任务引用读先开的。"
            "实际上共用一个文件夹（桌面应用的本机模式、常开的云端机器），就运行 init_ledger.py --shared。")


def read_deadline(args, tz, start):
    if args.hours is not None:
        return start + timedelta(hours=args.hours)
    if args.deadline:
        return c.parse_clock(args.deadline, tz, start)
    return None


def main():
    c.setup_output()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="项目短名，十个字以内。所有会话的名字都用它开头")
    parser.add_argument("--goal", help="一句话目标，会写进初始设定和每份派工单")
    parser.add_argument("--tz", help="钟点按哪个时区记，写成和 UTC 的时差。不写就是 +08:00（北京、新加坡）")
    share = parser.add_mutually_exclusive_group()
    share.add_argument("--shared", action="store_true", help="各会话共用这个文件夹。台账已存在时只改这一项")
    share.add_argument("--not-shared", action="store_true", help="各会话各有各的机器。台账已存在时只改这一项")
    parser.add_argument("--start", help="开始时间，默认是现在")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--deadline", help="用户自己提到的期限，例如 “2026-03-14 18:30” 或 18:30。可以不写")
    group.add_argument("--hours", type=float, help="期限的另一种写法：从开始时间算起多少小时")
    group.add_argument("--no-deadline", action="store_true", help="和 --retime 一起用：去掉期限")
    parser.add_argument("--dir", default=".", help="台账建在哪个目录下，默认是当前目录")
    parser.add_argument("--retime", action="store_true", help="台账已存在，只改期限")
    args = parser.parse_args()

    base = Path(args.dir).resolve()
    coord = base / c.LEDGER_DIR
    exists = c.ledger_path(base).exists()

    if exists and not args.retime and (args.shared or args.not_shared):
        ledger = c.load_ledger(base)
        ledger["shared"] = bool(args.shared)
        c.save_ledger(base, ledger)
        print("已经改了（%s 里的其他文件没动）。" % coord)
        print(describe_shared(ledger))
        print("已经生成的派工单不会跟着变：还没发出去的，加 --force 重新生成。")
        return

    if exists and not args.retime:
        print("台账已经在 %s 里了，这个项目立过项。不要重新立项：" % coord)
        print("  1. 运行 clock.py 看哪些会话还开着；")
        print("  2. 读 coord/BOARD.md：会话还没开完就接着开；开完了，照 SKILL.md 第 4 步的“被叫回来时”做。")
        sys.exit(3)

    if args.retime:
        if not exists:
            c.die("--retime 是给已有台账改期限用的，这里还没有台账。去掉 --retime 再运行。")
        ledger = c.load_ledger(base)
        tz = c.parse_tz(args.tz or ledger["tz"])
        now = c.now_in(tz)
        start = c.from_iso(ledger["start"])
        if args.no_deadline:
            deadline = None
        else:
            deadline = read_deadline(args, tz, now if args.deadline else start)
            if deadline is None:
                c.die("--retime 需要一个新的 --deadline 或 --hours；要去掉期限，写 --no-deadline。")
    else:
        if not args.name or not args.name.strip():
            c.die("缺 --name：给项目起个短名，十个字以内，例如 --name 语音待办。所有会话的名字都用它开头。")
        if not args.goal:
            c.die("缺 --goal：用一句话写清要做什么。")
        if args.no_deadline:
            c.die("--no-deadline 只和 --retime 一起用。新建台账时不写 --deadline 就是没有期限。")
        tz = c.parse_tz(args.tz or DEFAULT_TZ)
        now = c.now_in(tz)
        start = c.parse_clock(args.start, tz, now, nearest=True) if args.start else now
        deadline = read_deadline(args, tz, start)
        ledger = {"version": 3, "name": args.name.strip(), "goal": args.goal.strip(), "report_seq": 0, "briefs": {}}
        # 没明说就猜：Windows、macOS 是用户自己的电脑，各会话共用这个文件夹；Linux 当成云端的机器。
        ledger["shared"] = args.shared or (not args.not_shared and sys.platform in ("win32", "darwin"))

    if deadline is not None and deadline <= start:
        c.die("期限 %s 不晚于开始时间 %s。" % (c.hm(deadline), c.hm(start)))

    ledger.update({
        "tz": c.tz_label(tz),
        "start": start.isoformat(),
        "deadline": deadline.isoformat() if deadline else None,
        "caps": {"explorers": EXPLORERS_AT_ONCE},
    })
    c.save_ledger(base, ledger)

    if args.retime:
        c.refresh_progress(base)
        print("期限已经改了（%s 里的其他文件没动）。\n" % coord)
        print(describe(ledger, now))
        print("\n期限是给用户自己看的。要让各会话换挡，把用户的原话发给它们（SKILL.md 第 4 步的“被叫回来时”）。")
        return

    values, _ = c.base_values(ledger)
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
    (coord / "briefs").mkdir(parents=True, exist_ok=True)
    made.append("briefs/")
    # 记进展的脚本复制一份进台账：各会话共用这个文件夹时，它们不用找技能目录就能运行它。
    shutil.copyfile(Path(__file__).resolve().parent / "progress.py", coord / "progress.py")
    made.append("progress.py")
    c.refresh_progress(base)

    print("台账建在 %s" % coord)
    print("  " + "  ".join(made))
    print("全景页：%s（各会话共用这个文件夹时，请用户用浏览器打开它，开着就行，它自己会更新；"
          "一棵树，颜色就是状态，等用户处理的事在最上面）" % (coord / "progress.html"))
    print()
    print(describe(ledger, now))
    print()
    print("下一步：接着和用户聊，边聊边写 coord/CHARTER.md；没把握的点当场归类（小样或待探索），记进 coord/BOARD.md。")
    print("聊完、定了分工：把来龙去脉归纳进 coord/CONTEXT.md（深聊纪要），再生成分工确认。")


if __name__ == "__main__":
    main()
