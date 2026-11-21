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
    "builder": "建设者",
    "supervisor": "监管者",
}


def project_name(ledger):
    """项目短名：所有会话的名字都用它开头。老台账里没有，就取目标的前十个字。"""
    return ledger.get("name") or ledger.get("goal", "")[:10]


def session_name(ledger, role, title=""):
    """会话名：项目名 - 角色 - 细分。没有细分就只有前两段。"""
    parts = [project_name(ledger), ROLE_NAMES.get(role, role)]
    if title:
        parts.append(title)
    return " - ".join(parts)


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

    认三种写法：2026-03-14 18:30、2026-03-14T18:30、18:30。
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
    die("看不懂时间“%s”。写成 2026-03-14 18:30 或 18:30。" % text)


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
            "  还没建台账：先运行 init_ledger.py。\n"
            "  已经建了：用 --dir 指到台账所在的目录（里面有 coord/ 的那一层）。" % path
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


def embed_text(text):
    """把一个独立的 Markdown 文件整理成能嵌进别的文件的样子。"""
    lines = []
    for line in text.splitlines():
        if line.startswith("# ") or line.startswith(">"):
            continue  # 去掉总标题和写给读这个文件的人自己的备注
        if line.startswith("#"):
            line = "#" + line  # 标题降一级，免得和外层文件自己的小节混在一起
        lines.append(line)
    return "\n".join(lines).strip()


def charter_text(base):
    """读 coord/CHARTER.md，整理成能嵌进别的文件的样子。

    返回 (正文, 还没填的占位列表)。文件不存在时返回 (None, [])。
    """
    path = Path(base) / LEDGER_DIR / "CHARTER.md"
    if not path.exists():
        return None, []
    text = read_text(path)
    return embed_text(text), placeholders(text)


def context_state(base):
    """coord/CONTEXT.md（深聊纪要）写了没有。

    返回 (文件在不在, 还没填的占位列表)。
    """
    path = Path(base) / LEDGER_DIR / "CONTEXT.md"
    if not path.exists():
        return False, []
    return True, placeholders(read_text(path))


def is_shared(ledger):
    """各会话是不是共用一个文件夹（台账里记着，init_ledger.py 定的）。"""
    return bool(ledger.get("shared"))


def role_notes(name, role):
    """从 templates/<name> 里取出给某个角色的那一节（二级标题是角色的中文名），没有就返回空。"""
    path = TEMPLATE_DIR / name
    if not path.exists():
        return ""
    wanted, lines, inside = ROLE_NAMES.get(role, role), [], False
    for line in read_text(path).splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == wanted
            continue
        if inside:
            lines.append(line)
    return "\n".join(lines).strip()


def board_tasks(base):
    """从 coord/BOARD.md 的分工表里读出会话，不含调度者自己。

    返回 [{"id": 编号, "role": 角色, "title": 细分, "what": 要做的事, "link": 任务链接}]。
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
    # “细分”和“任务链接”两列是后加的，没有也认。
    title_at = header.index("细分") if "细分" in header else None
    link_at = header.index("任务链接") if "任务链接" in header else None

    def cell(cells, at):
        return cells[at] if at is not None and at < len(cells) else ""

    tasks = []
    for cells in rows:
        if len(cells) <= max(id_at, role_at, what_at):
            continue
        task_id, role, what = cells[id_at], cells[role_at], cells[what_at]
        if not task_id or task_id == "D" or role == "调度者":
            continue
        tasks.append({"id": task_id, "role": role, "title": cell(cells, title_at),
                      "what": what, "link": cell(cells, link_at)})
    return tasks


def board_list(base, section):
    """coord/BOARD.md 里某一节（按标题开头认）下面的条目。"""
    path = Path(base) / LEDGER_DIR / "BOARD.md"
    if not path.exists():
        return []
    items, inside = [], False
    for line in read_text(path).splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().startswith(section)
            continue
        if inside and line.strip().startswith("- "):
            item = line.strip()[2:].strip()
            if item:
                items.append(item)
    return items


def role_key(role_cn):
    """把分工表里写的角色（探索者、建设者、监管者）换成脚本里用的名字。认不出来返回 None。"""
    for key, name in ROLE_NAMES.items():
        if role_cn.startswith(name):
            return key
    return None


def refresh_progress(base):
    """重新生成全景（coord/PROGRESS.md 和 coord/progress.html）。

    全景只是给用户看的出口，它出了错不该拦住正事，所以只提醒一句。
    """
    try:
        import progress  # 和本文件在同一个目录
        progress.rebuild(Path(base) / LEDGER_DIR)
    except Exception as exc:  # noqa: BLE001
        print("提醒：全景没能更新（%s）。不影响别的。" % exc)


def placeholders(text):
    """文本里还没填的 {{…}}，去重，保持出现的先后。"""
    seen = []
    for match in PLACEHOLDER.finditer(text):
        item = match.group(0)
        if item not in seen:
            seen.append(item)
    return seen


def base_values(ledger):
    """各模板都会用到的字段。

    里面没有期限：节奏由用户掌握，期限只显示在全景页上给用户看，不写进任何发给会话的文字。
    """
    tz = parse_tz(ledger["tz"])
    values = {
        "目标": ledger["goal"],
        "项目一句话": ledger["goal"],
        "项目名": project_name(ledger),
    }
    return values, tz
