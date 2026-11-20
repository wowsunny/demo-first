# -*- coding: utf-8 -*-
"""demo-first 各脚本共用的函数。只用 Python 标准库，3.8 及以上都能跑。"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEDGER_DIR = "coord"
LEDGER_NAME = "ledger.json"
SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "templates"

# 模板里等人填的位置写成 {{说明}}。
PLACEHOLDER = re.compile(r"\{\{(.+?)\}\}")

ROLE_NAMES = {
    "explorer": "探索者",
    "lead-builder": "总建设者",
    "landing-builder": "落地建设者",
    "supervisor": "监管者",
}


def setup_output():
    """让中文在任何终端都打印得出来，不因为终端编码报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def die(message, code=2):
    print("错误：" + message, file=sys.stderr)
    sys.exit(code)


# ---------- 时间 ----------

def parse_tz(text):
    """把 +08:00、+8、-0530、UTC 这样的写法变成时区。"""
    t = text.strip().upper()
    if t in ("UTC", "Z", "GMT"):
        return timezone.utc
    m = re.fullmatch(r"(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?", t)
    if not m:
        die("看不懂时区“%s”。写成和 UTC 的时差，例如 +08:00（北京、新加坡）、-05:00、UTC。" % text)
    hours, minutes = int(m.group(2)), int(m.group(3) or 0)
    if hours > 14 or minutes > 59:
        die("时区“%s”超出了范围。" % text)
    sign = 1 if m.group(1) == "+" else -1
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def tz_label(tz):
    total = int(tz.utcoffset(None).total_seconds() // 60)
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return "%s%02d:%02d" % (sign, total // 60, total % 60)


def now_in(tz):
    """现在的时间，精确到分钟。

    测试时可以用环境变量 DEMO_FIRST_NOW 指定一个假的“现在”（ISO 格式），
    这样不用真的等几个小时就能看到各个关口前后的输出。
    """
    fake = os.environ.get("DEMO_FIRST_NOW")
    if fake:
        try:
            dt = datetime.fromisoformat(fake)
        except ValueError:
            die("环境变量 DEMO_FIRST_NOW 的值“%s”不是 ISO 时间。" % fake)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(tz).replace(second=0, microsecond=0)
    return datetime.now(timezone.utc).astimezone(tz).replace(second=0, microsecond=0)


def parse_clock(text, tz, ref, nearest=False):
    """解析用户给的时间。

    认三种写法：2026-11-22 18:30、2026-11-22T18:30、18:30。
    只写钟点时要猜是哪一天：
      默认取 ref 之后最近的那一次（交付时间总在开始之后）；
      nearest=True 时取离 ref 最近的那一次（开始时间可能刚过，也可能马上到）。
    """
    t = text.strip().replace("T", " ").replace("/", "-")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})", t)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups())
        try:
            return datetime(y, mo, d, h, mi, tzinfo=tz)
        except ValueError:
            die("时间“%s”不存在。" % text)
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            die("时间“%s”不存在。" % text)
        dt = ref.replace(hour=h, minute=mi, second=0, microsecond=0)
        if nearest:
            options = [dt - timedelta(days=1), dt, dt + timedelta(days=1)]
            return min(options, key=lambda x: abs(x - ref))
        if dt < ref:
            dt += timedelta(days=1)
        return dt
    die("看不懂时间“%s”。写成 2026-11-22 18:30 或 18:30。" % text)


def from_iso(text):
    return datetime.fromisoformat(text)


def hm(dt, ref=None):
    """钟点。和 ref 不在同一天时带上日期，免得跨天的项目看错。"""
    if ref is not None and dt.date() != ref.date():
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%H:%M")


def span(td):
    """时长写成 时:分；超过一天写成 N天 时:分。"""
    minutes = int(round(abs(td.total_seconds()) / 60))
    days, rest = divmod(minutes, 24 * 60)
    text = "%d:%02d" % (rest // 60, rest % 60)
    return ("%d天 %s" % (days, text)) if days else text


# ---------- 台账 ----------

def ledger_path(base):
    return Path(base) / LEDGER_DIR / LEDGER_NAME


def load_ledger(base):
    path = ledger_path(base)
    if not path.exists():
        die(
            "没找到 %s。\n"
            "  还没立项：先运行 init_ledger.py。\n"
            "  已经立项：用 --dir 指到台账所在的目录（里面有 coord/ 的那一层）。" % path
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        die("%s 不是合法的 JSON（%s）。它只该由脚本来写，手改坏了就照 BOARD.md 重建。" % (path, exc))


def save_ledger(base, data):
    path = ledger_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def read_text(path):
    return Path(path).read_text(encoding="utf-8-sig")


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def fill(text, values):
    """把 {{名字}} 换成 values 里的值；values 里没有的原样留着，等人填。"""
    def repl(match):
        key = match.group(1).strip()
        return values[key] if key in values else match.group(0)
    return PLACEHOLDER.sub(repl, text)


def charter_text(base):
    """读 coord/CHARTER.md，整理成能嵌进别的文件的样子。

    返回 (正文, 还没填的占位列表)。文件不存在时返回 (None, [])。
    """
    path = Path(base) / LEDGER_DIR / "CHARTER.md"
    if not path.exists():
        return None, []
    text = read_text(path)
    lines = []
    for line in text.splitlines():
        if line.startswith("# ") or line.startswith(">"):
            continue  # 去掉总标题和写给调度者自己的备注
        if line.startswith("#"):
            line = "#" + line  # 标题降一级，免得和外层文件自己的小节混在一起
        lines.append(line)
    return "\n".join(lines).strip(), placeholders(text)


def board_tasks(base):
    """从 coord/BOARD.md 的任务表里读出任务，返回 [(编号, 角色, 要做的事)]，不含调度者自己。

    表被改得认不出来时返回 None，由调用方提示手工填。
    """
    path = Path(base) / LEDGER_DIR / "BOARD.md"
    if not path.exists():
        return None
    header, rows = None, []
    for line in read_text(path).splitlines():
        if not line.strip().startswith("|"):
            if header is not None and rows:
                break  # 任务表结束了
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            if "编号" in cells and "角色" in cells:
                header = cells
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue  # 表头下面的分隔行
        rows.append(cells)
    if header is None:
        return None
    id_at, role_at = header.index("编号"), header.index("角色")
    what_at = next((i for i, name in enumerate(header) if name.startswith("要回答的问题")), None)
    if what_at is None:
        return None
    tasks = []
    for cells in rows:
        if len(cells) <= max(id_at, role_at, what_at):
            continue
        task_id, role, what = cells[id_at], cells[role_at], cells[what_at]
        if not task_id or task_id == "D" or role == "调度者":
            continue
        tasks.append((task_id, role, what))
    return tasks


def board_queue(base):
    """coord/BOARD.md 里“排队”一节下面的条目。"""
    path = Path(base) / LEDGER_DIR / "BOARD.md"
    if not path.exists():
        return []
    items, inside = [], False
    for line in read_text(path).splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().startswith("排队")
            continue
        if inside and line.strip().startswith("- "):
            item = line.strip()[2:].strip()
            if item:
                items.append(item)
    return items


def placeholders(text):
    """文本里还没填的 {{…}}，去重，保持出现的先后。"""
    seen = []
    for match in PLACEHOLDER.finditer(text):
        item = match.group(0)
        if item not in seen:
            seen.append(item)
    return seen


def time_values(ledger, now=None):
    """各模板都会用到的时间字段。"""
    tz = parse_tz(ledger["tz"])
    start = from_iso(ledger["start"])
    gates = {k: from_iso(v) for k, v in ledger["gates"].items()}
    deadline = from_iso(ledger["deadline"])
    values = {
        "目标": ledger["goal"],
        "项目一句话": ledger["goal"],
        "时区": ledger["tz"],
        "开始": hm(start, start),
        "立项截止": hm(gates["kickoff_end"], start),
        "探索截止": hm(gates["explore_end"], start),
        "功能冻结": hm(gates["freeze"], start),
        "开始交付": hm(gates["deliver"], start),
        "交付时间": hm(deadline, start),
    }
    if now is not None:
        values["现在"] = hm(now, start)
    return values, tz
