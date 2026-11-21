#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发出之前检查：有没有没填的地方、有没有对方看不懂的话；太长的告诉你怎么发。
派工单、分工确认、阶段报告都用它查；阶段报告另外查行数和“要你做的”的件数。

用法：
  python3 check_brief.py coord/briefs/E1.md
  python3 check_brief.py coord/KICKOFF.md
  python3 check_brief.py coord/reports/2.md

退出码：0 全部通过；1 有文件没通过；2 文件不存在。
“问题”必须改掉再发；“提醒”自己判断要不要改；“怎么发”照着做。
派工单太长不算问题，不要为了变短删内容：各会话共用文件夹时（台账里记着）它是文件，对方自己读；
不共用时，脚本会打印“怎么发”：先当文件附上，附不了就在它说的位置分成几条消息。
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as c  # noqa: E402

# 新会话看不到调度者的对话。出现这些说法，说明派工单在指望一段对方看不到的上下文。
CONTEXT_PHRASES = [
    "见上文", "如上所述", "如前所述", "上面说的", "上面提到", "上文提到", "前面提到", "前面说的",
    "之前说过", "之前讨论", "之前聊过", "刚才说的", "刚才讨论", "我们聊过", "我们讨论过", "按之前的",
    "the chat above", "as discussed", "see above", "as mentioned",
]

# Manus 的接口文档写：一条消息的文字大约限 5000 个估算 token。留一成余量。
# 派工单超过它不拦、也不让人压短（压短会丢内容，还要来回试好几轮）：内容走文件，
# 共用文件夹时对方自己读，不共用时当附件发或分成几条发，见 how_to_send。
TOKEN_LIMIT = 4500

# 估算 token：非 ASCII 字符（汉字、全角标点）每个算 1.15，ASCII 每 2.5 个字符算 1。
# 平台用哪种分词器没有公开，所以这两个系数是拿本技能的模板和填好的派工单，
# 对照 cl100k、o200k 两种常见分词器的实际结果定的：估出来的数比两者都高一点，宁可高估，不可低估。
WIDE_WEIGHT = 1.15
ASCII_PER_TOKEN = 2.5

ROLE_BY_NAME = {v: k for k, v in c.ROLE_NAMES.items()}
def parse_title(first):
    """派工单的第一行就是会话名：# 项目名 - 角色 - 细分（细分可以没有）。

    返回 {"role_cn": 角色, "title": 细分}；第一行不是这个样子就返回 None。
    """
    if not first.startswith("#"):
        return None
    parts = [part.strip() for part in first.lstrip("#").strip().split(" - ")]
    if len(parts) < 2:
        return None
    for at, part in enumerate(parts[1:], 1):
        if part in ROLE_BY_NAME:  # 项目名里自己带“ - ”也认得出来
            return {"role_cn": part, "title": " - ".join(parts[at + 1:])}
    return {"role_cn": parts[1], "title": " - ".join(parts[2:])}

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
    in_briefs = Path(path).parent.name == "briefs"
    title = parse_title(first)
    role = ROLE_BY_NAME.get(title["role_cn"]) if title else None
    if not in_briefs and not role:
        title = None  # 不在 briefs/ 里、第一行又不是会话名：当成给用户的消息，不按派工单查
    kind = c.ROLE_NAMES.get(role, "一般文件")

    for number, line in enumerate(lines, 1):
        for match in c.PLACEHOLDER.finditer(line):
            problems.append("第 %d 行还有没填的 %s。填上它；用不着的整行删掉。" % (number, match.group(0)))
        if not title and not in_briefs:
            continue  # 只有派工单是发给看不到对话的新会话的；给用户的消息不查这一条
        lowered = line.lower()
        for phrase in CONTEXT_PHRASES:
            if phrase in lowered:
                problems.append("第 %d 行写了“%s”。新会话看不到你的对话，把指的那段内容原文抄进来。" % (number, phrase))

    if in_briefs and not title:
        problems.append("第一行要是会话名“# <项目名> - <角色> - <细分>”，现在认不出这是给谁的派工单。照模板改回来。")

    if first.strip().startswith(REPORT_HEAD):
        kind = "阶段报告"
        more_problems, more_hints = report_problems(text)
        problems += more_problems
        hints += more_hints

    if title and not role:
        problems.append("第一行的角色“%s”不认识。只能是：探索者、建设者、监管者。" % title["role_cn"])
    if role == "explorer" and not title["title"]:
        problems.append("探索者的会话名要有第三段（细分），说明它试的是什么。")

    if role:
        found = sections(text)
        have = {name: (body, at) for name, body, at in found}
        template = c.TEMPLATE_DIR / ("brief-%s.md" % role)
        if template.exists():
            for name, _, _ in sections(c.read_text(template)):
                if name not in have:
                    problems.append("少了“## %s”一节。这一节是给新会话定规矩的，不能删；从模板里补回来。" % name)
        for name, (body, at) in have.items():
            if not body:
                problems.append("第 %d 行“## %s”下面是空的。" % (at, name))
        if role == "explorer":
            for name, (body, at) in have.items():
                if name.startswith("你要回答的问题"):
                    marks = body.count("？") + body.count("?")
                    if marks > 1:
                        hints.append("第 %d 行起“%s”里有 %d 个问号。一个探索者只回答一个问题；"
                                     "两个问题分不开（改这边、那边必须跟着改），就合成一句来问；"
                                     "分得开，就各开一个探索者。" % (at, name, marks))
        if role != "builder" and "不发布" not in text:
            problems.append("全文没有“不发布”。除了建设者，谁都不该发布正式站；从模板里把这条规矩补回来。")

    tokens = estimate_tokens(text)
    how = []
    if role or in_briefs:
        # 派工单太长不拦，也不让人压短：内容走文件。
        if tokens > TOKEN_LIMIT and as_file(path):
            hints.append("估算约 %d token。派工单是文件，对方自己读，长度不用管：不要为了变短删内容。" % tokens)
        elif tokens > TOKEN_LIMIT:
            how = how_to_send(text, path, first.lstrip("#").strip(), tokens)
    elif tokens > TOKEN_LIMIT:
        problems.append("估算约 %d token，超过了 %d。一条消息装不下：删掉和这个任务无关的事实，"
                        "长的材料改成文件或任务引用。" % (tokens, TOKEN_LIMIT))
    elif tokens > TOKEN_LIMIT * 0.85:
        hints.append("估算约 %d token，快到上限（%d）了。" % (tokens, TOKEN_LIMIT))

    return problems, hints, tokens, kind, how


def how_to_send(text, path, name, tokens):
    """派工单一条消息装不下时怎么发。返回要打印的几行：先当文件附上，附不了就分成几条。

    分的位置只落在二级标题上：从头往后装，装不下了就在下一个标题前断开。
    """
    chunks, at = [], None  # [(标题, 这一块的 token)]，开头到第一个标题之间的那块标题是 None
    block = []
    for line in text.splitlines() + ["## "]:
        if line.startswith("## "):
            chunks.append((at, estimate_tokens("\n".join(block))))
            at, block = line.strip(), []
        block.append(line)
    cuts, big, used = [], [], 0
    for heading, size in chunks:
        if used and used + size > TOKEN_LIMIT:
            cuts.append(heading)
            used = 0
        used += size
        if size > TOKEN_LIMIT:
            big.append(heading or "开头")
    file_name = Path(path).name
    lines = ["估算约 %d token，一条消息装不下（约 %d）。内容不用删，也不用压短，照下面的发：" % (tokens, TOKEN_LIMIT),
             "1. 先试当文件发：把 %s 作为附件附上，第一条消息只发这三行：" % file_name,
             "     # %s" % name,
             "     你的派工单是附上的文件 %s。现在把它完整读一遍，照它做。" % file_name,
             "     读不到这个文件，就只回一句“读不到派工单”，然后停下。"]
    if cuts:
        lines.append("2. 附不了：分 %d 条消息发，在这几处之前断开：%s。" % (len(cuts) + 1, "、".join("“%s”" % c_ for c_ in cuts)))
    else:
        lines.append("2. 附不了：分两条消息发。")
    if big:
        lines.append("   %s 这一节自己就超过一条消息：在它里面的空行处再断开。" % "、".join("“%s”" % b for b in big))
    total = "N" if big else str(len(cuts) + 1 if cuts else 2)
    lines.append("   第一条的末尾加一句“派工单共 %s 条，全部收到再动手”；后面每条的开头写“派工单第几条”。" % total)
    return lines


def as_file(path):
    """这份东西是不是让对方自己去读的文件：在 coord/briefs/ 里，而且台账里记着各会话共用文件夹。"""
    folder = Path(path).resolve().parent
    if folder.name != "briefs":
        return False
    ledger = folder.parent / c.LEDGER_NAME
    if not ledger.exists():
        return False
    try:
        return c.is_shared(json.loads(ledger.read_text(encoding="utf-8")))
    except ValueError:
        return False


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
        problems, hints, tokens, kind, how = check(path)
        if problems:
            failed += 1
            print("没通过：%s（%s，约 %d token）" % (raw, kind, tokens))
            for item in problems:
                print("  问题：" + item)
        else:
            print("通过：%s（%s，约 %d token）" % (raw, kind, tokens))
        for item in hints:
            print("  提醒：" + item)
        for number, item in enumerate(how):
            print(("  怎么发：" if number == 0 else "    ") + item)
    if failed:
        print("\n改完再运行一次，全部通过了才发。")
        sys.exit(1)


if __name__ == "__main__":
    main()
