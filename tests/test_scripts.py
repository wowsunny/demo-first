#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""四个脚本的自动测试：在临时目录里把一次冲刺从立项走到交付。

用法（在仓库根目录）：python tests/test_scripts.py
只用标准库。时间用环境变量 DEMO_FIRST_NOW 假装，不用真的等。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
DAY = "2026-11-22T%s:00+08:00"


class SprintFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, clock, name, *args):
        env = dict(os.environ, DEMO_FIRST_NOW=DAY % clock, PYTHONIOENCODING="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=str(self.base), env=env,
                              capture_output=True, text=True, encoding="utf-8")
        return done.returncode, done.stdout + done.stderr

    def edit(self, rel, pairs):
        path = self.base / rel
        text = path.read_text(encoding="utf-8")
        for old, new in pairs:
            self.assertIn(old, text, "%s 里没找到 %s" % (rel, old))
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8", newline="\n")

    def fill_all(self, rel, value="已填"):
        """把文件里剩下的 {{…}} 全换成同一个值。"""
        import re
        path = self.base / rel
        text = re.sub(r"\{\{.+?\}\}", value, path.read_text(encoding="utf-8"))
        path.write_text(text, encoding="utf-8", newline="\n")

    def init(self):
        code, out = self.run_script("14:32", "init_ledger.py", "--goal", "说一段话，自动整理成待办清单",
                                    "--deadline", "18:30", "--start", "14:30", "--tz", "+08:00")
        self.assertEqual(code, 0, out)
        return out

    def write_charter_and_board(self):
        self.fill_all("coord/CHARTER.md", "按住说话 → 清单里多出两条待办")
        row = "| D | 调度者 | 拆、派、收、报；交付时逐条验收，写交付说明 | 进行中 | | `coord/` | | |\n"
        self.edit("coord/BOARD.md", [(row, row
                                      + "| B1 | 总建设者 | 边界、架构和骨架 | 排队 | | | | |\n"
                                      + "| E1 | 探索者 | 语音转文字走哪条路 | 排队 | | | | |\n"
                                      + "| S1 | 监管者 | 全局巡检 | 排队 | | | | |\n")])

    def test_init_computes_gates_and_refuses_to_run_twice(self):
        out = self.init()
        ledger = json.loads((self.base / "coord/ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["mode"], "sprint")
        self.assertEqual(ledger["gates"]["explore_end"], DAY % "16:30")
        self.assertEqual(ledger["gates"]["freeze"], DAY % "17:18")
        self.assertEqual(ledger["gates"]["deliver"], DAY % "18:06")
        self.assertEqual(ledger["caps"]["explorer_box_minutes"], 36)
        for name in ("CHARTER.md", "BOARD.md", "DECISIONS.md", "PROJECT_INSTRUCTION.md", "briefs", "handoffs"):
            self.assertTrue((self.base / "coord" / name).exists(), name)
        self.assertIn("探索截止  16:30", out)
        code, out = self.run_script("15:00", "init_ledger.py", "--goal", "另一个", "--hours", "4", "--tz", "+08:00")
        self.assertEqual(code, 3, out)
        self.assertIn("不要重新立项", out)

    def test_init_needs_timezone_and_duration(self):
        code, out = self.run_script("14:32", "init_ledger.py", "--goal", "x", "--hours", "4")
        self.assertEqual(code, 2)
        self.assertIn("--tz", out)
        code, out = self.run_script("14:32", "init_ledger.py", "--goal", "x", "--tz", "+08:00")
        self.assertEqual(code, 2)
        self.assertIn("--hours", out)

    def test_long_project_has_no_caps(self):
        code, out = self.run_script("14:32", "init_ledger.py", "--goal", "x", "--hours", "72", "--tz", "+08:00")
        self.assertEqual(code, 0, out)
        self.assertIn("项目档", out)
        ledger = json.loads((self.base / "coord/ledger.json").read_text(encoding="utf-8"))
        self.assertIsNone(ledger["caps"]["explorers"])

    def test_kickoff_waits_for_charter_then_embeds_it(self):
        self.init()
        code, out = self.run_script("14:36", "new_brief.py", "kickoff")
        self.assertEqual(code, 2)
        self.assertIn("CHARTER.md 还没写完", out)
        self.write_charter_and_board()
        code, out = self.run_script("14:38", "new_brief.py", "kickoff")
        self.assertEqual(code, 0, out)
        text = (self.base / "coord/KICKOFF.md").read_text(encoding="utf-8")
        self.assertIn("- E1 探索者｜语音转文字走哪条路", text)
        self.assertIn("### 验收项", text)  # 初始设定的标题降了一级
        code, out = self.run_script("14:38", "check_brief.py", "coord/KICKOFF.md")
        self.assertEqual(code, 1)  # 还有两处要人填
        self.fill_all("coord/KICKOFF.md")
        code, out = self.run_script("14:39", "check_brief.py", "coord/KICKOFF.md")
        self.assertEqual(code, 0, out)

    def test_briefs_caps_checks_and_clock(self):
        self.init()
        self.write_charter_and_board()
        for clock, role, task_id in (("14:44", "lead-builder", "B1"), ("14:44", "explorer", "E1"),
                                     ("14:46", "探索者", "E2"), ("14:48", "supervisor", "S1")):
            code, out = self.run_script(clock, "new_brief.py", role, task_id, "标题 " + task_id)
            self.assertEqual(code, 0, out)
        self.assertIn("到 15:20 必须", (self.base / "coord/briefs/E1.md").read_text(encoding="utf-8"))
        self.assertIn("### 验收项", (self.base / "coord/briefs/S1.md").read_text(encoding="utf-8"))

        # 第三个探索者超过并行上限：不生成
        code, out = self.run_script("14:50", "new_brief.py", "explorer", "E3", "首页视觉")
        self.assertEqual(code, 2)
        self.assertIn("并行上限", out)
        self.assertFalse((self.base / "coord/briefs/E3.md").exists())

        # 没填完不通过；填完通过
        code, out = self.run_script("14:50", "check_brief.py", "coord/briefs/E1.md")
        self.assertEqual(code, 1)
        self.assertIn("还有没填的", out)
        for task_id in ("B1", "E1", "E2", "S1"):
            self.fill_all("coord/briefs/%s.md" % task_id)
            code, out = self.run_script("14:52", "check_brief.py", "coord/briefs/%s.md" % task_id)
            self.assertEqual(code, 0, out)

        # 指望对方看不到的上下文、删掉规矩的小节、时间盒没有钟点，都拦下来
        self.edit("coord/briefs/E2.md", [("已填\n\n## 你需要知道的事实", "细节见上文\n\n## 你需要知道的事实"),
                                          ("到 15:22 必须", "到点必须")])
        code, out = self.run_script("14:53", "check_brief.py", "coord/briefs/E2.md")
        self.assertEqual(code, 1)
        self.assertIn("见上文", out)
        self.assertIn("没有具体的钟点", out)
        text = (self.base / "coord/briefs/E1.md").read_text(encoding="utf-8")
        cut = text[:text.index("## 范围")] + text[text.index("## 怎么做"):]
        (self.base / "coord/briefs/E1.md").write_text(cut, encoding="utf-8", newline="\n")
        code, out = self.run_script("14:53", "check_brief.py", "coord/briefs/E1.md")
        self.assertEqual(code, 1)
        self.assertIn("少了“## 范围”一节", out)

        # 时钟：超时的时间盒、阶段、报告序号
        code, out = self.run_script("15:42", "clock.py", "--card")
        self.assertEqual(code, 0, out)
        self.assertIn("按时间现在该在：试与建", out)
        self.assertIn("E1  探索者  标题 E1｜时间盒到 15:20，已超 0:22", out)
        self.assertIn("【阶段报告 #1｜已用 1:12，剩 2:48｜阶段：试与建】", out)
        self.assertIn("探索者 2/2", out)

        # 阶段报告的草稿：抬头已经填好；没填完、超过 20 行、待办超过 3 件，都拦下来
        report = self.base / "coord/reports/1.md"
        self.assertTrue(report.read_text(encoding="utf-8").startswith("【阶段报告 #1｜已用 1:12，剩 2:48｜阶段：试与建】"))
        code, out = self.run_script("15:42", "check_brief.py", "coord/reports/1.md")
        self.assertEqual(code, 1)
        self.fill_all("coord/reports/1.md", "去 E1：看第一版。要你看")
        code, out = self.run_script("15:42", "check_brief.py", "coord/reports/1.md")
        self.assertEqual(code, 0, out)
        self.assertIn("阶段报告", out)
        self.edit("coord/reports/1.md", [("1. 去 E1：看第一版。要你看",
                                          "1. 去 E1：看。\n2. 去 E2：看。\n3. 去 B1：定。\n4. 去 S1：看。")])
        code, out = self.run_script("15:42", "check_brief.py", "coord/reports/1.md")
        self.assertEqual(code, 1)
        self.assertIn("“要你做的”有 4 件", out)
        self.edit("coord/reports/1.md", [("\n4. 去 S1：看。", ""), ("\n风险\n", "\n" + "- 多一行\n" * 8 + "\n风险\n")])
        code, out = self.run_script("15:42", "check_brief.py", "coord/reports/1.md")
        self.assertEqual(code, 1)
        self.assertIn("超过 20 行", out)

        # E1 结束后名额空出来，E3 可以开了
        code, out = self.run_script("15:43", "clock.py", "--done", "E1")
        self.assertEqual(code, 0, out)
        code, out = self.run_script("15:44", "new_brief.py", "explorer", "E3", "首页视觉")
        self.assertEqual(code, 0, out)

        # 落地建设者：第一个可以，第二个超过建设者上限
        # 默认时间盒：现在加总时长的两成（48 分钟），并在功能冻结（17:18）前留出 12 分钟给总建设者发布
        # --handoff 把存好的移交说明填进派工单；文件还没存就不生成，也不占名额
        code, out = self.run_script("15:50", "new_brief.py", "landing-builder", "B2", "把语音输入写进正式项目",
                                    "--handoff", "E1")
        self.assertEqual(code, 2)
        self.assertIn("handoffs/E1.md", out)
        self.assertFalse((self.base / "coord/briefs/B2.md").exists())
        (self.base / "coord/handoffs/E1.md").write_text("1. 结论：成。用浏览器自带的识别。\n", encoding="utf-8", newline="\n")
        code, out = self.run_script("15:50", "new_brief.py", "landing-builder", "B2", "把语音输入写进正式项目",
                                    "--handoff", "E1")
        self.assertEqual(code, 0, out)
        self.assertIn("时间盒到 16:38", out)
        self.assertIn("用浏览器自带的识别", (self.base / "coord/briefs/B2.md").read_text(encoding="utf-8"))
        code, out = self.run_script("15:51", "new_brief.py", "landing-builder", "B3", "再来一个")
        self.assertEqual(code, 2)
        self.assertIn("由它来落地", out)

        code, out = self.run_script("17:30", "clock.py", "--card")
        self.assertIn("按时间现在该在：收尾", out)
        self.assertIn("【阶段报告 #2｜已用 3:00，剩 1:00｜阶段：收尾】", out)
        code, out = self.run_script("18:45", "clock.py")
        self.assertIn("已过交付时间", out)

    def test_retime_keeps_other_files(self):
        self.init()
        before = (self.base / "coord/CHARTER.md").read_text(encoding="utf-8")
        code, out = self.run_script("15:00", "init_ledger.py", "--retime", "--deadline", "19:00")
        self.assertEqual(code, 0, out)
        self.assertIn("探索截止  16:45", out)
        self.assertEqual(before, (self.base / "coord/CHARTER.md").read_text(encoding="utf-8"))

    def test_clock_without_ledger_explains(self):
        code, out = self.run_script("15:00", "clock.py")
        self.assertEqual(code, 2)
        self.assertIn("init_ledger.py", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
