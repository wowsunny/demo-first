#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五个脚本的自动测试：在临时目录里把一个项目从深聊走到收尾。

用法（在仓库根目录）：python tests/test_scripts.py
只用标准库。时间用环境变量 DEMO_FIRST_NOW 假装，不用真的等。
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
DAY = "2026-11-22T%s:00+08:00"
D_ROW = "| D | 调度者 | | 深聊、定分工、派工；之后被叫回来才动 | 进行中 | |\n"
PYTHON = Path(sys.executable).stem


class ProjectFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, clock, name, *args, cwd=None):
        env = dict(os.environ, DEMO_FIRST_NOW=DAY % clock, PYTHONIOENCODING="utf-8")
        script = name if os.path.isabs(str(name)) else str(SCRIPTS / name)
        done = subprocess.run([sys.executable, script, *args], cwd=str(cwd or self.base), env=env,
                              capture_output=True, text=True, encoding="utf-8")
        return done.returncode, done.stdout + done.stderr

    def read(self, rel):
        return (self.base / rel).read_text(encoding="utf-8")

    def edit(self, rel, pairs):
        text = self.read(rel)
        for old, new in pairs:
            self.assertIn(old, text, "%s 里没找到 %s" % (rel, old))
            text = text.replace(old, new)
        (self.base / rel).write_text(text, encoding="utf-8", newline="\n")

    def fill_all(self, rel, value="已填"):
        """把文件里剩下的 {{…}} 全换成同一个值。"""
        text = re.sub(r"\{\{.+?\}\}", value, self.read(rel))
        (self.base / rel).write_text(text, encoding="utf-8", newline="\n")

    def init(self, *extra):
        code, out = self.run_script("14:32", "init_ledger.py", "--name", "语音待办",
                                    "--goal", "说一段话，自动整理成待办清单", "--tz", "+08:00", *extra)
        self.assertEqual(code, 0, out)
        return out

    def write_charter_and_board(self, links=True):
        self.fill_all("coord/CHARTER.md", "按住说话 → 清单里多出两条待办")
        link = lambda task_id: ("https://manus.im/app/" + task_id) if links else ""  # noqa: E731
        self.edit("coord/BOARD.md", [(D_ROW, D_ROW
                                      + "| E1 | 探索者 | 说话到出字 | 松手后 3 秒内出字 | 待开 | %s |\n" % link("E1")
                                      + "| E2 | 探索者 | 口语拆待办 | 10 句样例能对几句 | 待开 | %s |\n" % link("E2")
                                      + "| B1 | 建设者 | | 架构和骨架；落地和交付 | 待开 | %s |\n" % link("B1")
                                      + "| S1 | 监管者 | | 全局巡检和验收 | 待开 | |\n"),
                                     ("会话有名额了，就开最前面的那个。\n\n- ",
                                      "会话有名额了，就开最前面的那个。\n\n- 首页视觉（等 E1 定稿后再开）")])

    def test_init_sets_up_the_ledger_without_any_deadline(self):
        out = self.init()
        ledger = json.loads(self.read("coord/ledger.json"))
        self.assertEqual(ledger["name"], "语音待办")
        self.assertEqual(ledger["tz"], "+08:00")
        self.assertIsNone(ledger["deadline"])  # 节奏由用户掌握：不给期限就没有期限
        self.assertNotIn("gates", ledger)
        self.assertEqual(ledger["caps"]["explorers"], 3)
        for name in ("CHARTER.md", "BOARD.md", "DECISIONS.md", "PROJECT_INSTRUCTION.md", "briefs",
                     "progress.py", "progress.html", "PROGRESS.md"):
            self.assertTrue((self.base / "coord" / name).exists(), name)
        self.assertIn("没有设期限：节奏由用户掌握。", out)
        self.assertIn("同时最多 3 个探索者", out)
        self.assertIn("语音待办 - 角色 - 细分", self.read("coord/BOARD.md"))
        # 项目主指令是直接给各会话看的：占位都填好了，里面没有钟点
        instruction = self.read("coord/PROJECT_INSTRUCTION.md")
        self.assertNotIn("{{", instruction)
        self.assertIn("节奏由用户掌握，没有时间盒", instruction)
        for name in ("CHARTER.md", "PROJECT_INSTRUCTION.md"):
            for word in ("关口", "截止"):
                self.assertNotIn(word, self.read("coord/" + name))
        code, out = self.run_script("15:00", "init_ledger.py", "--name", "另一个", "--goal", "另一个")
        self.assertEqual(code, 3, out)
        self.assertIn("不要重新立项", out)

    def test_init_needs_name_and_goal_but_not_time(self):
        code, out = self.run_script("14:32", "init_ledger.py", "--goal", "x")
        self.assertEqual(code, 2)
        self.assertIn("--name", out)
        code, out = self.run_script("14:32", "init_ledger.py", "--name", "x")
        self.assertEqual(code, 2)
        self.assertIn("--goal", out)
        # 时区和期限都可以不写
        code, out = self.run_script("14:32", "init_ledger.py", "--name", "x", "--goal", "x")
        self.assertEqual(code, 0, out)
        self.assertRegex(json.loads(self.read("coord/ledger.json"))["tz"], r"^[+-]\d\d:\d\d$")

    def test_deadline_is_optional_and_only_for_the_user(self):
        out = self.init("--deadline", "18:30")
        self.assertIn("用户定的期限：18:30（还有 3:58）", out)
        self.assertIn("不写进派工单", out)
        self.write_charter_and_board()
        code, out = self.run_script("15:00", "new_brief.py", "explorer", "E1", "说话到出字")
        self.assertEqual(code, 0, out)
        code, out = self.run_script("15:01", "new_brief.py", "builder", "B1")
        self.assertEqual(code, 0, out)
        for task_id in ("E1", "B1"):
            brief = self.read("coord/briefs/%s.md" % task_id)
            self.assertNotIn("18:30", brief)
            self.assertIn("节奏由用户掌握，这里没有时间盒", brief)
        self.assertIn('"deadline": "2026-11-22T18:30:00+08:00"', self.read("coord/progress.html"))
        code, out = self.run_script("15:40", "clock.py")
        self.assertIn("用户定的期限 18:30，还有 2:50", out)
        # 改期限、去掉期限
        code, out = self.run_script("15:41", "init_ledger.py", "--retime", "--deadline", "19:00")
        self.assertEqual(code, 0, out)
        self.assertIn("用户定的期限：19:00", out)
        code, out = self.run_script("15:42", "init_ledger.py", "--retime", "--no-deadline")
        self.assertEqual(code, 0, out)
        self.assertIsNone(json.loads(self.read("coord/ledger.json"))["deadline"])
        code, out = self.run_script("15:43", "init_ledger.py", "--retime")
        self.assertEqual(code, 2)
        self.assertIn("--no-deadline", out)

    def test_kickoff_waits_for_charter_then_embeds_it(self):
        self.init()
        code, out = self.run_script("14:36", "new_brief.py", "kickoff")
        self.assertEqual(code, 2)
        self.assertIn("CHARTER.md 还没写完", out)
        self.write_charter_and_board()
        code, out = self.run_script("14:58", "new_brief.py", "kickoff")
        self.assertEqual(code, 0, out)
        text = self.read("coord/KICKOFF.md")
        self.assertIn("- 语音待办 - 探索者 - 说话到出字（E1）｜松手后 3 秒内出字", text)
        self.assertIn("- 语音待办 - 建设者（B1）｜", text)
        self.assertIn("- 待探索，现在不开：首页视觉", text)
        self.assertIn("### 验收项", text)  # 初始设定的标题降了一级
        code, out = self.run_script("14:58", "check_brief.py", "coord/KICKOFF.md")
        self.assertEqual(code, 1)  # 还有两处要人填
        self.fill_all("coord/KICKOFF.md")
        code, out = self.run_script("14:59", "check_brief.py", "coord/KICKOFF.md")
        self.assertEqual(code, 0, out)
        # 分工表写好之后，全景里就看得到要开的会话
        self.assertIn("待开 E1 语音待办 - 探索者 - 说话到出字", self.read("coord/PROGRESS.md"))

    def test_kickoff_warns_about_a_bad_split(self):
        self.init()
        self.fill_all("coord/CHARTER.md", "按住说话 → 清单里多出两条待办")
        self.edit("coord/BOARD.md", [(D_ROW, D_ROW + "| E1 | 探索者 | | 松手后 3 秒内出字 | 待开 | |\n")])
        code, out = self.run_script("14:58", "new_brief.py", "kickoff")
        self.assertEqual(code, 0, out)
        self.assertIn("没写细分", out)
        self.assertIn("只能有一个建设者", out)
        self.assertIn("没有监管者", out)

    def test_briefs_caps_checks_and_clock(self):
        self.init()
        self.write_charter_and_board()
        outs = {}
        for clock, role, task_id, title, effort in (("15:00", "explorer", "E1", "说话到出字", "超高"),
                                                    ("15:01", "探索者", "E2", "口语拆待办", "超高"),
                                                    ("15:02", "builder", "B1", "", "超高"),
                                                    ("15:03", "supervisor", "S1", "", "极致")):
            args = [role, task_id] + ([title] if title else [])
            code, out = self.run_script(clock, "new_brief.py", *args)
            self.assertEqual(code, 0, out)
            # 每份派工单都给出会话名和思考强度，以及它在各平台上叫什么
            self.assertIn("会话名：语音待办 - ", out)
            self.assertIn("思考强度：%s（" % effort, out)
            self.assertNotIn("时间盒", out)
            outs[task_id] = out
        self.assertIn("Max 的超高档 max-extra", outs["E1"])
        self.assertIn("要附的：没有。", outs["E1"])
        self.assertIn("Max 的极致档 max-ultra", outs["S1"])
        self.assertIn("把探索者的任务都作为任务引用附上", outs["B1"])
        self.assertIn("连同你自己这个任务", outs["S1"])
        ledger = json.loads(self.read("coord/ledger.json"))
        self.assertEqual(ledger["briefs"]["S1"]["effort"], "极致")
        self.assertEqual(ledger["briefs"]["B1"]["effort"], "超高")
        self.assertEqual(ledger["briefs"]["E2"]["name"], "语音待办 - 探索者 - 口语拆待办")
        self.assertNotIn("box_end", ledger["briefs"]["E1"])

        # 第一行就是会话名；子代理的规矩嵌进去了；记进展用的是现在这个解释器的名字
        e2 = self.read("coord/briefs/E2.md")
        self.assertTrue(e2.startswith("# 语音待办 - 探索者 - 口语拆待办\n"))
        self.assertIn("## 什么时候收", e2)
        self.assertIn("同一个方向来回了三轮还定不下来", e2)
        self.assertIn("【交回 <名字>】", e2)
        self.assertIn("`%s coord/progress.py --help`" % PYTHON, e2)
        # 建设者：探索清单从分工表里取，连链接一起；监管者：整份不用手填
        b1 = self.read("coord/briefs/B1.md")
        self.assertTrue(b1.startswith("# 语音待办 - 建设者\n"))
        self.assertIn("- E1｜语音待办 - 探索者 - 说话到出字｜松手后 3 秒内出字｜https://manus.im/app/E1", b1)
        self.assertIn("- 待探索，还没开：首页视觉", b1)
        self.assertIn("它在 `coord/handoffs/<编号>.md`，demo 在 `lab/<编号>/`", b1)
        s1 = self.read("coord/briefs/S1.md")
        self.assertIn("### 验收项", s1)
        self.assertIn("- B1｜语音待办 - 建设者｜", s1)
        self.assertNotIn("- S1｜", s1)
        code, out = self.run_script("15:04", "check_brief.py", "coord/briefs/S1.md")
        self.assertEqual(code, 0, out)
        # 发给会话的文字里没有钟点压力
        for task_id in ("E1", "E2", "B1", "S1"):
            brief = self.read("coord/briefs/%s.md" % task_id)
            for word in ("截止", "关口", "到点"):
                self.assertNotIn(word, brief, "%s 里出现了“%s”" % (task_id, word))

        # 档位只认四档
        code, out = self.run_script("15:04", "new_brief.py", "explorer", "E9", "x", "--effort", "极高")
        self.assertEqual(code, 2)
        self.assertIn("标准、高、超高、极致", out)
        # 探索者必须写细分；第四个探索者超过上限；建设者只有一个；不再有落地建设者
        code, out = self.run_script("15:04", "new_brief.py", "explorer", "E3")
        self.assertEqual(code, 2)
        self.assertIn("细分", out)
        code, out = self.run_script("15:04", "new_brief.py", "explorer", "E3", "首页视觉")
        self.assertEqual(code, 0, out)
        code, out = self.run_script("15:05", "new_brief.py", "explorer", "E4", "再来一个")
        self.assertEqual(code, 2)
        self.assertIn("会话上限", out)
        self.assertFalse((self.base / "coord/briefs/E4.md").exists())
        code, out = self.run_script("15:05", "new_brief.py", "builder", "B2")
        self.assertEqual(code, 2)
        self.assertIn("已经有建设者 B1", out)
        code, out = self.run_script("15:05", "new_brief.py", "landing-builder", "B2", "落地")
        self.assertEqual(code, 2)
        self.assertIn("不再单开落地建设者", out)

        # 没填完不通过；填完通过
        code, out = self.run_script("15:06", "check_brief.py", "coord/briefs/E1.md")
        self.assertEqual(code, 1)
        self.assertIn("还有没填的", out)
        for task_id in ("B1", "E1", "E2"):
            self.fill_all("coord/briefs/%s.md" % task_id)
            code, out = self.run_script("15:06", "check_brief.py", "coord/briefs/%s.md" % task_id)
            self.assertEqual(code, 0, out)

        # 指望对方看不到的上下文、删掉规矩的小节、认不出是给谁的，都拦下来
        self.edit("coord/briefs/E2.md", [("已填\n\n## 你需要知道的事实", "细节见上文\n\n## 你需要知道的事实")])
        code, out = self.run_script("15:07", "check_brief.py", "coord/briefs/E2.md")
        self.assertEqual(code, 1)
        self.assertIn("见上文", out)
        text = self.read("coord/briefs/E1.md")
        cut = text[:text.index("## 范围")] + text[text.index("## 怎么做"):]
        (self.base / "coord/briefs/E1.md").write_text(cut.replace("# 语音待办 - 探索者 - 说话到出字", "# 派工单"),
                                                      encoding="utf-8", newline="\n")
        code, out = self.run_script("15:07", "check_brief.py", "coord/briefs/E1.md")
        self.assertEqual(code, 1)
        self.assertIn("第一行要是会话名", out)
        (self.base / "coord/briefs/E1.md").write_text(cut, encoding="utf-8", newline="\n")
        code, out = self.run_script("15:07", "check_brief.py", "coord/briefs/E1.md")
        self.assertEqual(code, 1)
        self.assertIn("少了“## 范围”一节", out)

        # 看一眼：进行了多久、哪些会话开着。不催任何人
        code, out = self.run_script("15:42", "clock.py", "--card")
        self.assertEqual(code, 0, out)
        self.assertIn("现在 15:42（+08:00）｜已进行 1:10｜没有设期限", out)
        self.assertIn("E1  语音待办 - 探索者 - 说话到出字｜开了 0:42", out)
        self.assertIn("【阶段报告 #1｜15:42｜已进行 1:10】", out)
        self.assertIn("探索者 3/3，建设者 1/1，监管者 1/1", out)
        for word in ("已超", "截止", "该给结论"):
            self.assertNotIn(word, out)

        # 阶段报告的草稿：抬头已经填好；没填完、超过 20 行、待办超过 3 件，都拦下来
        self.assertTrue(self.read("coord/reports/1.md").startswith("【阶段报告 #1｜15:42｜已进行 1:10】"))
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

        # E1 结束后名额空出来，E4 可以开了
        code, out = self.run_script("15:43", "clock.py", "--done", "E1")
        self.assertEqual(code, 0, out)
        code, out = self.run_script("15:44", "new_brief.py", "explorer", "E4", "再来一个")
        self.assertEqual(code, 0, out)

    def test_clock_before_any_session_says_deep_chat(self):
        self.init()
        code, out = self.run_script("14:40", "clock.py")
        self.assertEqual(code, 0, out)
        self.assertIn("还没开出会话：现在在深聊。", out)

    def test_progress_records_and_builds_the_panorama(self):
        self.init()
        self.write_charter_and_board()
        for clock, role, task_id, title in (("15:00", "explorer", "E1", "说话到出字"), ("15:02", "builder", "B1", ""),
                                            ("15:03", "supervisor", "S1", "")):
            code, out = self.run_script(clock, "new_brief.py", *([role, task_id] + ([title] if title else [])))
            self.assertEqual(code, 0, out)
        own = self.base / "coord" / "progress.py"  # 各会话用的是复制进台账的这一份

        # 帮助里的例子用的是现在这个解释器的名字（Windows 上多半没有 python3）
        code, out = self.run_script("15:04", own, "--help")
        self.assertEqual(code, 0, out)
        self.assertIn("%s coord/progress.py E1.1 进行中" % PYTHON, out)
        self.assertIn("先推进，再记", out)

        # 一条命令记几条；文字可以不写
        code, out = self.run_script("15:05", own, "E1", "进行中", "试两条路", "E1.1", "进行中", "路线甲",
                                    "E1.2", "进行中", "路线乙", "E1.3", "待做")
        self.assertEqual(code, 0, out)
        self.assertIn("已记：E1.2 进行中 路线乙", out)
        code, out = self.run_script("15:12", own, "E1.1", "不成", "部分手机拿不到结果", "E1.2", "完成", "两秒出字",
                                    "E1", "等用户", "来试一下")
        self.assertEqual(code, 0, out)
        self.assertIn("1 处等用户", out)
        # 每个会话一个文件，只往后加行
        log = self.read("coord/progress/E1.md")
        self.assertIn("- 2026-11-22 15:05｜E1.1｜进行中｜路线甲", log)
        self.assertIn("- 2026-11-22 15:12｜E1.1｜不成｜部分手机拿不到结果", log)
        self.assertFalse((self.base / "coord/progress/B1.md").exists())

        # 监管者的清单单列一栏；处理掉的不再列
        code, out = self.run_script("15:20", own, "S1.1", "待做", "分享页谁都能改（去建设者说）", "S1.2", "待做", "首屏慢",
                                    "S1", "进行中", "巡检 #1：2 条提醒")
        self.assertEqual(code, 0, out)
        code, out = self.run_script("15:30", own, "S1.2", "完成", "建设者改了")
        self.assertEqual(code, 0, out)

        md = self.read("coord/PROGRESS.md")
        self.assertIn("- 语音待办 - 探索者 - 说话到出字：来试一下（15:12 起）", md)
        self.assertIn("监管者的清单（没处理的 1 条，已处理 1 条）：", md)
        self.assertIn("- 待做 S1.1 分享页谁都能改（去建设者说）", md)
        self.assertIn("- 等用户 E1 语音待办 - 探索者 - 说话到出字（超高） — 来试一下", md)
        self.assertIn("  - 不成 E1.1 路线甲 — 部分手机拿不到结果", md)
        self.assertIn("  - 完成 E1.2 路线乙 — 两秒出字", md)
        self.assertIn("- 已开 B1 语音待办 - 建设者", md)
        self.assertIn("- 待开 E2 语音待办 - 探索者 - 口语拆待办", md)
        self.assertIn("- 待探索，还没开：首页视觉", md)
        page = self.read("coord/progress.html")
        self.assertIn('<meta http-equiv="refresh" content="10">', page)
        self.assertIn("监管者的清单", page)
        self.assertIn("路线乙", page)
        self.assertIn("没有设期限，节奏由你掌握", page)
        self.assertNotIn("时间盒", page)
        self.assertNotIn("__", page.split("<script>")[0])  # 模板里的占位都换掉了

        # 换个目录运行台账里的那一份，也认得自己的台账；不记只重建也行
        code, out = self.run_script("15:31", own, cwd=self.base.parent)
        self.assertEqual(code, 0, out)
        self.assertIn("全景已更新", out)

        # 状态只认七个词；编号要合规矩
        code, out = self.run_script("15:32", own, "E1.4", "搞定", "x")
        self.assertEqual(code, 2)
        self.assertIn("待做、进行中、等用户、完成、不成、卡住、放弃", out)
        code, out = self.run_script("15:32", own, "一号", "完成")
        self.assertEqual(code, 2)
        self.assertIn("不是编号", out)

    def test_clock_without_ledger_explains(self):
        code, out = self.run_script("15:00", "clock.py")
        self.assertEqual(code, 2)
        self.assertIn("init_ledger.py", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
