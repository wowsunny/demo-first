#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查仓库里所有 Markdown：表格每行列数一致，代码块都闭合，样例里填好的阶段报告合乎格式的限制。

用法（在仓库根目录）：python dev/lint.py
退出码：0 没问题；1 有问题。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_brief  # noqa: E402  阶段报告的规矩只在那里定义一次


def check_markdown(path, problems):
    lines = path.read_text(encoding="utf-8").splitlines()
    rel = path.relative_to(ROOT).as_posix()
    in_code, columns, block, tables = False, None, [], 0
    for number, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            if in_code:
                check_report(rel, number, block, problems)
            in_code, columns, block = not in_code, None, []
            continue
        if in_code:
            block.append(line)
            continue
        text = line.strip()
        if text.startswith("|") and text.endswith("|"):
            count = text.count("|") - 1
            if columns is None:
                columns, tables = count, tables + 1
            elif count != columns:
                problems.append("%s 第 %d 行：表格这一行有 %d 列，表头是 %d 列。" % (rel, number, count, columns))
        else:
            columns = None
    if in_code:
        problems.append("%s：有一个代码块没有闭合。" % rel)
    return tables


def check_report(rel, end_line, block, problems):
    """代码块如果是一份填好的阶段报告，就用检查脚本的规矩查一遍。"""
    if not block or not block[0].startswith(check_brief.REPORT_HEAD):
        return
    found, _ = check_brief.report_problems("\n".join(block))
    for item in found:
        problems.append("%s 第 %d 行结束的样例：%s" % (rel, end_line, item))


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    problems, tables, count = [], 0, 0
    for path in sorted(ROOT.rglob("*.md")):
        if "dist" in path.parts:
            continue
        tables += check_markdown(path, problems)
        count += 1
    print("查了 %d 个 Markdown 文件、%d 张表。" % (count, tables))
    if problems:
        for item in problems:
            print("  问题：" + item)
        sys.exit(1)
    print("没有问题。")


if __name__ == "__main__":
    main()
