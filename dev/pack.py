#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把技能打成可以上传到 Manus 的 zip，顺便做几项机械检查。

用法（在仓库根目录）：
  python dev/pack.py                    输出到 dist/demo-first.zip
  python dev/pack.py ../demo-first.zip  输出到指定位置

zip 里只放技能运行要用的：SKILL.md、scripts/、templates/、references/。
README、tests、dev 这些给人看的文件不放进去。
"""

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ("scripts", "templates", "references")

# Manus 的 skill.upload 文档：包是 zip，不超过 8 MiB；SKILL.md 在包的根目录或往下一层；
# 只读 name 和 description；description 超过 1000 字符会被截断；YAML 头的值里不能出现 ---。
# Agent Skills 规范：name 最长 64、只能用小写字母数字和连字符；SKILL.md 正文建议 500 行、5000 token 以内。
NAME_MAX = 64
DESCRIPTION_MAX = 1000
BODY_LINES_MAX = 500
BODY_TOKENS_MAX = 5000
ZIP_MAX = 8 * 1024 * 1024


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist" / "demo-first.zip"
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    problems = []

    match = re.match(r"^---\n(.*?)\n---\n", skill, re.S)
    if not match:
        sys.exit("SKILL.md 开头要有 YAML 头（--- 包起来的 name 和 description）。")
    head, body = match.group(1), skill[match.end():]
    if not re.search(r"^description:", head, re.M):
        # YAML 头在第一个 --- 处就结束了；description 的值里有 --- 的话，它会被截掉。
        problems.append("YAML 头里没读到 description。检查 name 或 description 的值里是不是出现了 ---。")
        head += "\ndescription: \"\""
    name = re.search(r"^name:\s*(.+)$", head, re.M).group(1).strip()
    description = re.search(r"^description:\s*(.+)$", head, re.M).group(1).strip().strip('"')
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > NAME_MAX:
        problems.append("name “%s” 不合规范：只能用小写字母、数字、连字符，最长 %d。" % (name, NAME_MAX))
    if name != ROOT.name:
        print("提醒：name 是 %s，目录名是 %s。规范要求两者一致；从 GitHub 导入时以仓库名为准。" % (name, ROOT.name))
    if len(description) > DESCRIPTION_MAX:
        problems.append("description 有 %d 个字符，超过 %d 会被 Manus 截断。" % (len(description), DESCRIPTION_MAX))
    lines = body.count("\n") + 1
    if lines > BODY_LINES_MAX:
        problems.append("SKILL.md 正文 %d 行，超过 %d。把细节挪到 references/。" % (lines, BODY_LINES_MAX))
    print("name: %s｜description: %d 字符｜正文: %d 行、%d 字符" % (name, len(description), lines, len(body)))
    try:
        import tiktoken  # 可选：装了就报真实的 token 数
        for encoding in ("cl100k_base", "o200k_base"):
            count = len(tiktoken.get_encoding(encoding).encode(body))
            print("  正文 token（%s）：%d" % (encoding, count))
            if count > BODY_TOKENS_MAX:
                problems.append("SKILL.md 正文按 %s 算有 %d token，超过 %d。" % (encoding, count, BODY_TOKENS_MAX))
    except ImportError:
        print("  没装 tiktoken，跳过 token 计数。")

    files = [ROOT / "SKILL.md"]
    for folder in INCLUDE:
        files += sorted(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)

    # SKILL.md、模板、参考文件里提到的路径都要真的在包里。
    packed = {p.relative_to(ROOT).as_posix() for p in files}
    pattern = re.compile(r"(?:scripts|templates|references)/[A-Za-z0-9_./-]+\.(?:md|py)")
    for path in files:
        if path.suffix != ".md":
            continue
        for ref in sorted(set(pattern.findall(path.read_text(encoding="utf-8")))):
            if ref not in packed:
                problems.append("%s 提到了 %s，包里没有这个文件。" % (path.relative_to(ROOT).as_posix(), ref))

    if problems:
        print("\n没打包，先改掉这些问题：")
        for item in problems:
            print("  - " + item)
        sys.exit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    size = out.stat().st_size
    if size > ZIP_MAX:
        sys.exit("zip 有 %d 字节，超过 Manus 的 8 MiB 上限。" % size)
    print("\n已打包：%s（%d 个文件，%d 字节）" % (out, len(files), size))
    for path in files:
        print("  " + path.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
