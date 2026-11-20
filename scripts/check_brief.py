#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发出之前检查：有没有没填的地方、有没有对方看不懂的话、会不会太长。
派工单、开工确认、阶段报告都用它查；阶段报告另外查行数和“要你做的”的件数。

用法：
  python3 check_brief.py coord/briefs/E1.md
  python3 check_brief.py coord/KICKOFF.md
  python3 check_brief.py coord/reports/2.md

退出码：0 全部通过；1 有文件没通过；2 文件不存在。
“问题”必须改掉再发；“提醒”自己判断要不要改。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

# 新任务看不到调度者的对话。出现这些说法，说明派工单在指望一段对方看不到的上下文。
CONTEXT_PHRASES = [
    "见上文", "如上所述", "如前所述", "上面说的", "上面提到", "上文提到", "前面提到", "前面说的",
    "之前说过", "之前讨论", "之前聊过", "刚才说的", "刚才讨论", "我们聊过", "我们讨论过", "按之前的",
    "the chat above", "as discussed", "see above", "as mentioned",
]

# Manus 的接口文档写：一条消息的文字大约限 5000 个估算 token。留一成余量。
TOKEN_LIMIT = 4500

# 估算 token：非 ASCII 字符（汉字、全角标点）每个算 1.15，ASCII 每 2.5 个字符算 1。
# 平台用哪种分词器没有公开，所以这两个系数是拿本技能的模板和填好的派工单，
# 对照 cl100k、o200k 两种常见分词器的实际结果定的：估出来的数比两者都高一点，宁可高估，不可低估。
WIDE_WEIGHT = 1.15
ASCII_PER_TOKEN = 2.5

ROLE_BY_NAME = {v: k for k, v in c.ROLE_NAMES.items()}
TITLE = re.compile(r"^#\s*派工单\s+([^\s（]+)（(.+?)）")
CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")

# 阶段报告的两条限制。用户同一时刻只顾得上很少的事：
# 超过 20 行就没人从头读到尾，超过 3 件待办就等于没排先后。
REPORT_HEAD = "【阶段报告 #"
REPORT_LINES_MAX = 20
REPORT_ASKS_MAX = 3
REPORT_PARTS = ["一句话", "任务", "要你做的", "我替你定了的", "监管者的提醒", "接下来", "风险"]
NUMBERED = re.compile(r"^\d+[.、．]\s*")


def report_problems(text):
    """按阶段报告的格式查一遍，返回 (问题, 提醒)。"""
    lines = [line.strip() for line in text.splitlines()]
    problems, hints = [], []
    filled = [line for line in lines if line]
    if len(filled) > REPORT_LINES_MAX:
        problems.append("阶段报告有 %d 行（不算空行），超过 %d 行。把没变化的任务合成一行，"
                        "细节留在 BOARD.md 里。" % (len(filled), REPORT_LINES_MAX))
    for part in REPORT_PARTS:
        if not any(line.startswith(part) for line in lines):
            problems.append("阶段报告少了“%s”这一段。没有内容也要留着，写“无”。" % part)
    asks, inside = [], False
    for line in lines:
        if line.startswith("要你做的"):
            inside = True
        elif inside and (not line or any(line.startswith(p) for p in REPORT_PARTS)):
            inside = False
        elif inside and NUMBERED.match(line):
            asks.append(NUMBERED.sub("", line))
    if len(asks) > REPORT_ASKS_MAX:
        problems.append("“要你做的”有 %d 件，超过 %d 件。把次要的按你的推荐定掉，挪进“我替你定了的”。"
                        % (len(asks), REPORT_ASKS_MAX))
    for ask in asks:
        # “在这里”：这件事就在调度者这个任务里做，不用去别的任务。
        if not ask.startswith(("去", "在这里")) and "没有" not in ask and ask != "无":
            hints.append("“要你做的”里有一条没写去哪个任务：%s……" % ask[:20])
    return problems, hints


def estimate_tokens(text):
    wide = sum(1 for ch in text if ord(ch) > 127)
    narrow = len(text) - wide
    return int(wide * WIDE_WEIGHT + narrow / ASCII_PER_TOKEN + 0.5)


def sections(text):
    """按二级标题切开，返回 [(标题, 正文, 标题所在行号)]。"""
    result, title, body, at = [], None, [], 0
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            if title is not None:
                result.append((title, "\n".join(body).strip(), at))
            title, body, at = line[3:].strip(), [], number
        elif title is not None:
            body.append(line)
    if title is not None:
        result.append((title, "\n".join(body).strip(), at))
    return result


def check(path):
    text = c.read_text(path)
    lines = text.splitlines()
    problems, hints = [], []

    first = next((line for line in lines if line.strip()), "")
    title = TITLE.match(first)
    role = ROLE_BY_NAME.get(title.group(2)) if title else None
    kind = c.ROLE_NAMES.get(role, "一般文件")

    for number, line in enumerate(lines, 1):
        for match in c.PLACEHOLDER.finditer(line):
            problems.append("第 %d 行还有没填的 %s。填上它；用不着的整行删掉。" % (number, match.group(0)))
        if not title:
            continue  # 只有派工单是发给看不到对话的新任务的；给用户的消息不查这一条
        lowered = line.lower()
        for phrase in CONTEXT_PHRASES:
            if phrase in lowered:
                problems.append("第 %d 行写了“%s”。新任务看不到你的对话，把指的那段内容原文抄进来。" % (number, phrase))

    if Path(path).parent.name == "briefs" and not title:
        problems.append("第一行要是“# 派工单 <编号>（<角色>）：<标题>”，现在认不出这是给谁的派工单。照模板改回来。")

    if first.strip().startswith(REPORT_HEAD):
        kind = "阶段报告"
        more_problems, more_hints = report_problems(text)
        problems += more_problems
        hints += more_hints

    if title and not role:
        problems.append("第一行的角色“%s”不认识。只能是：探索者、总建设者、落地建设者、监管者。" % title.group(2))

    if role:
        found = sections(text)
        have = {name: (body, at) for name, body, at in found}
        template = c.TEMPLATE_DIR / ("brief-%s.md" % role)
        if template.exists():
            for name, _, _ in sections(c.read_text(template)):
                if name not in have:
                    problems.append("少了“## %s”一节。这一节是给新任务定规矩的，不能删；从模板里补回来。" % name)
        for name, (body, at) in have.items():
            if not body:
                problems.append("第 %d 行“## %s”下面是空的。" % (at, name))
        if "时间盒" in have and not CLOCK.search(have["时间盒"][0]):
            problems.append("“## 时间盒”里没有具体的钟点。写成“到 15:10 必须……”，新任务才知道什么时候该收。")
        if role == "explorer":
            for name, (body, at) in have.items():
                if name.startswith("你要回答的问题"):
                    marks = body.count("？") + body.count("?")
                    if marks > 1:
                        hints.append("第 %d 行起“%s”里有 %d 个问号。一个探索者只回答一个问题；"
                                     "确实是两个互不依赖的问题，就拆成两个探索者。" % (at, name, marks))
        if role != "lead-builder" and "不发布" not in text:
            problems.append("全文没有“不发布”。除了总建设者，谁都不该发布正式站；从模板里把这条规矩补回来。")

    tokens = estimate_tokens(text)
    if tokens > TOKEN_LIMIT:
        problems.append("估算约 %d token，超过了 %d。一条消息装不下：删掉和这个任务无关的事实，"
                        "长的材料改成文件或任务引用。" % (tokens, TOKEN_LIMIT))
    elif tokens > TOKEN_LIMIT * 0.85:
        hints.append("估算约 %d token，快到上限（%d）了。" % (tokens, TOKEN_LIMIT))

    return problems, hints, tokens, kind


def main():
    c.setup_output()
    paths = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not paths or len(paths) != len(sys.argv) - 1:
        print(__doc__.strip())
        sys.exit(0 if any(a in ("-h", "--help") for a in sys.argv[1:]) else 2)

    failed = 0
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            c.die("没找到文件 %s。" % raw)
        problems, hints, tokens, kind = check(path)
        if problems:
            failed += 1
            print("没通过：%s（%s，约 %d token）" % (raw, kind, tokens))
            for item in problems:
                print("  问题：" + item)
        else:
            print("通过：%s（%s，约 %d token）" % (raw, kind, tokens))
        for item in hints:
            print("  提醒：" + item)
    if failed:
        print("\n改完再运行一次，全部通过了才发。")
        sys.exit(1)


if __name__ == "__main__":
    main()
