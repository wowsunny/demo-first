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
DAY = "2026-03-14T%s:00+08:00"
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
        # 默认按“各会话各有各的机器”测：脚本自己猜的结果随运行测试的系统变，所以这里写明。
        if "--shared" not in extra:
            extra += ("--not-shared",)
        code, out = self.run_script("14:32", "init_ledger.py", "--name", "语音待办",
                                    "--goal", "说一段话，自动整理成待办清单", *extra)
        self.assertEqual(code, 0, out)
        return out

    def write_charter_and_board(self, links=True):
        self.fill_all("coord/CHARTER.md", "按住说话 → 清单里多出两条待办")
        self.fill_all("coord/CONTEXT.md", "用户原话：松手以后要马上有反应")
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
        for name in ("CHARTER.md", "CONTEXT.md", "BOARD.md", "DECISIONS.md", "PROJECT_INSTRUCTION.md", "briefs",
                     "progress.py", "progress.html", "progress.data.js", "PROGRESS.md"):
            self.assertTrue((self.base / "coord" / name).exists(), name)
        self.assertIs(ledger["shared"], False)
        self.assertIn("各会话：各有各的机器", out)
        self.assertIn("深聊纪要", out)
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
        # 时区和期限都可以不写：钟点统一按 +08:00 记，不跟着机器的时区走；
        # 各会话是不是共用文件夹，脚本按运行它的系统猜
        code, out = self.run_script("14:32", "init_ledger.py", "--name", "x", "--goal", "x")
        self.assertEqual(code, 0, out)
        ledger = json.loads(self.read("coord/ledger.json"))
        self.assertEqual(ledger["tz"], "+08:00")
        self.assertIs(ledger["shared"], sys.platform in ("win32", "darwin"))
        # 猜得不对随时改，只动这一项
        code, out = self.run_script("14:33", "init_ledger.py", "--shared")
        self.assertEqual(code, 0, out)
        self.assertIn("各会话：共用这个文件夹", out)
        self.assertIs(json.loads(self.read("coord/ledger.json"))["shared"], True)
        code, out = self.run_script("14:34", "init_ledger.py", "--not-shared")
        self.assertEqual(code, 0, out)
        ledger = json.loads(self.read("coord/ledger.json"))
        self.assertIs(ledger["shared"], False)
        self.assertEqual(ledger["name"], "x")

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
        self.assertIn('"deadline": "2026-03-14T18:30:00+08:00"', self.read("coord/progress.html"))
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
        # 深聊纪要是所有会话共同的背景：没写完，也不生成分工确认
        self.fill_all("coord/CHARTER.md", "按住说话 → 清单里多出两条待办")
        code, out = self.run_script("14:50", "new_brief.py", "kickoff")
        self.assertEqual(code, 2)
        self.assertIn("CONTEXT.md（深聊纪要）还没写完", out)
        self.write_charter_and_board()
        code, out = self.run_script("14:58", "new_brief.py", "kickoff")
        self.assertEqual(code, 0, out)
        text = self.read("coord/KICKOFF.md")
        self.assertIn("coord/CONTEXT.md", text)
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
        self.fill_all("coord/CONTEXT.md", "归纳好了")
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
        for clock, role, task_id, title, effort in (("15:00", "explorer", "E1", "说话到出字", "高"),
                                                    ("15:01", "探索者", "E2", "口语拆待办", "高"),
                                                    ("15:02", "builder", "B1", "", "高"),
                                                    ("15:03", "supervisor", "S1", "", "超高")):
            args = [role, task_id] + ([title] if title else [])
            code, out = self.run_script(clock, "new_brief.py", *args)
            self.assertEqual(code, 0, out)
            # 每份派工单都给出会话名和思考强度，以及它在各平台上叫什么
            self.assertIn("会话名：语音待办 - ", out)
            self.assertIn("思考强度：%s（" % effort, out)
            self.assertNotIn("时间盒", out)
            outs[task_id] = out
        self.assertIn("Max 的高档 max-high", outs["E1"])
        self.assertIn("Max 的超高档 max-extra", outs["S1"])
        # 各会话各有各的机器：深聊纪要作为文件附上，后开的引用先开的，第一条消息发全文
        self.assertIn("要附的：把 coord/CONTEXT.md 和 coord/CHARTER.md 作为文件附上", outs["E1"])
        self.assertIn("把探索者的任务都作为任务引用附上", outs["B1"])
        self.assertIn("连同你自己这个任务", outs["S1"])
        for out in outs.values():
            self.assertIn("coord/CHARTER.md 作为文件附上", out)
            self.assertIn("第一条消息：派工单全文", out)
        ledger = json.loads(self.read("coord/ledger.json"))
        self.assertEqual(ledger["briefs"]["S1"]["effort"], "超高")
        self.assertEqual(ledger["briefs"]["B1"]["effort"], "高")
        self.assertEqual(ledger["briefs"]["E2"]["name"], "语音待办 - 探索者 - 口语拆待办")
        self.assertNotIn("box_end", ledger["briefs"]["E1"])

        # 第一行就是会话名；子代理的规矩嵌进去了；记进展用的是现在这个解释器的名字
        e2 = self.read("coord/briefs/E2.md")
        self.assertTrue(e2.startswith("# 语音待办 - 探索者 - 口语拆待办\n"))
        self.assertIn("## 什么时候收", e2)
        self.assertIn("同一个方向来回了三轮还定不下来", e2)
        self.assertIn("【交回 <名字>】", e2)
        self.assertIn("同一个难题有几条做法时，不同时试", e2)
        self.assertIn("深聊纪要（`CONTEXT.md`）和初始设定（`CHARTER.md`）已经作为文件附给你", e2)
        self.assertNotIn("只有这台电脑打得开", e2)  # 共用文件夹才有的须知，这里不该出现
        self.assertIn("`%s coord/progress.py --help`" % PYTHON, e2)
        # 建设者：探索清单从分工表里取，连链接一起；监管者：整份不用手填
        b1 = self.read("coord/briefs/B1.md")
        self.assertTrue(b1.startswith("# 语音待办 - 建设者\n"))
        self.assertIn("- E1｜语音待办 - 探索者 - 说话到出字｜松手后 3 秒内出字｜https://manus.im/app/E1", b1)
        self.assertIn("- 待探索，还没开：首页视觉", b1)
        self.assertIn("它在 `coord/handoffs/<编号>.md`，demo 在 `lab/<编号>/`", b1)
        s1 = self.read("coord/briefs/S1.md")
        # 初始设定不嵌进派工单（嵌进去的会过时，还会把派工单撑过长度上限），作为文件附上
        self.assertIn("初始设定（`CHARTER.md`）已经作为文件附给你", s1)
        self.assertNotIn("### 验收项", s1)
        self.assertIn("- B1｜语音待办 - 建设者｜", s1)
        self.assertNotIn("- S1｜", s1)
        self.assertIn("每 15 分钟在这个任务里巡检一次", s1)
        self.assertIn("无变化", s1)
        # 定时的那几次只看新的；巡检子代理带上以往的清单和用户的批复
        self.assertIn("只看上次巡检之后有新记录的会话", s1)
        self.assertIn("用户批复过的不再报", s1)
        self.assertIn("用户的批复（时间、针对哪一条、用户原话）", s1)
        # 只读也包括不运行会改文件的命令；钟点照脚本打印的写
        self.assertIn("也不运行会改文件的命令", s1)
        self.assertIn("它每次都打印项目钟点", s1)
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

    def test_shared_folder_builder_first_and_briefs_point_to_files(self):
        self.init("--shared")
        self.write_charter_and_board(links=False)  # 一个会话都还没开，分工表里没有链接

        # 建设者第一个开：不用等探索者的链接，也不用附什么
        code, out = self.run_script("15:00", "new_brief.py", "builder", "B1")
        self.assertEqual(code, 0, out)
        self.assertIn("思考强度：高（", out)
        self.assertIn("要附的：没有。各会话共用这个文件夹", out)
        self.assertNotIn("链接还没记", out)
        # 第一条消息只发三行，脚本直接给出来
        self.assertIn("第一条消息：只发下面三行", out)
        self.assertIn("    # 语音待办 - 建设者", out)
        self.assertIn("你的派工单在工作区的 coord/briefs/B1.md", out)
        self.assertIn("读不到派工单", out)

        b1 = self.read("coord/briefs/B1.md")
        self.assertIn("项目的来龙去脉在 `coord/CONTEXT.md`（深聊纪要）", b1)
        self.assertIn("初始设定在 `coord/CHARTER.md`", b1)  # 以文件为准，不再嵌一份会过时的全文
        self.assertNotIn("### 验收项", b1)
        self.assertIn("- E1｜语音待办 - 探索者 - 说话到出字｜松手后 3 秒内出字\n", b1)
        self.assertIn("正式项目要建成 Manus 托管的网站项目", b1)
        self.assertNotIn("{{共用文件夹须知}}", b1)

        code, out = self.run_script("15:01", "new_brief.py", "explorer", "E1", "说话到出字")
        self.assertEqual(code, 0, out)
        e1 = self.read("coord/briefs/E1.md")
        self.assertIn("预览链接只有这台电脑打得开", e1)
        self.assertIn("动手前把这两份读完", e1)
        code, out = self.run_script("15:02", "new_brief.py", "supervisor", "S1")
        self.assertEqual(code, 0, out)
        s1 = self.read("coord/briefs/S1.md")
        self.assertIn("初始设定在 `coord/CHARTER.md`", s1)
        self.assertIn("- B1｜语音待办 - 建设者｜架构和骨架；落地和交付\n", s1)
        code, out = self.run_script("15:03", "check_brief.py", "coord/briefs/S1.md")
        self.assertEqual(code, 0, out)

        # 接口约定在 BOARD.md 里，建设者自己读得到：派工单只指过去，不留一处要调度者抄的
        self.assertIn("接口约定：在 `coord/BOARD.md` 的“接口约定”一节，以它为准", b1)
        self.assertNotIn("从 BOARD.md 的“接口约定”抄", b1)

        # 派工单太长不拦，也不让人压短。共用文件夹：它是文件，对方自己读
        self.fill_all("coord/briefs/B1.md")
        self.edit("coord/briefs/B1.md", [("## 节奏", "用户的原话，一句都不删。" * 150 + "\n\n## 节奏")])
        code, out = self.run_script("15:04", "check_brief.py", "coord/briefs/B1.md")
        self.assertEqual(code, 0, out)
        self.assertIn("长度不用管：不要为了变短删内容", out)
        self.assertNotIn("怎么发", out)
        # 不共用：同一份照样通过，脚本说怎么发。先当文件附上，附不了就在二级标题处分成几条
        code, out = self.run_script("15:05", "init_ledger.py", "--not-shared")
        self.assertEqual(code, 0, out)
        code, out = self.run_script("15:06", "check_brief.py", "coord/briefs/B1.md")
        self.assertEqual(code, 0, out)
        self.assertIn("怎么发：估算约", out)
        self.assertIn("内容不用删，也不用压短", out)
        self.assertIn("把 B1.md 作为附件附上，第一条消息只发这三行", out)
        self.assertIn("    # 语音待办 - 建设者", out)
        self.assertRegex(out, r"附不了：分 \d 条消息发，在这几处之前断开：“## [^”]+”")
        self.assertNotIn("没通过", out)
        # 哪一节自己就装不下一条消息，也照实说
        self.edit("coord/briefs/B1.md", [("## 节奏", "用户的原话，一句都不删。" * 300 + "\n\n## 节奏")])
        code, out = self.run_script("15:07", "check_brief.py", "coord/briefs/B1.md")
        self.assertEqual(code, 0, out)
        self.assertIn("这一节自己就超过一条消息", out)

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
        code, out = self.run_script("15:05", own, "E1", "进行中", "分两块做", "E1.1", "进行中", "反馈动画",
                                    "E1.2", "进行中", "格式兼容", "E1.3", "待做")
        self.assertEqual(code, 0, out)
        self.assertIn("已记：E1.2 进行中 格式兼容", out)
        # 每次都说出项目钟点：各会话自己看到的是机器的时间，和台账记的对不上
        self.assertIn("项目钟点：15:05（+08:00）", out)
        code, out = self.run_script("15:12", own, "E1.1", "不成", "一种手机上不转", "E1.2", "完成", "两种格式都认",
                                    "E1", "等用户", "来试一下")
        self.assertEqual(code, 0, out)
        self.assertIn("1 处等用户", out)
        # 每个会话一个文件，只往后加行
        log = self.read("coord/progress/E1.md")
        self.assertIn("- 2026-03-14 15:05｜E1.1｜进行中｜反馈动画", log)
        self.assertIn("- 2026-03-14 15:12｜E1.1｜不成｜一种手机上不转", log)
        self.assertFalse((self.base / "coord/progress/B1.md").exists())

        # 交给子代理的那块活：第一次记时在编号后面加“子代理”，之后不用再加，全景里一直认得
        code, out = self.run_script("15:14", own, "E1.4", "子代理", "进行中", "录音时长上限", "E1.5", "待做", "自己收尾")
        self.assertEqual(code, 0, out)
        self.assertIn("已记：E1.4 进行中 录音时长上限（子代理）", out)
        self.assertIn("- 2026-03-14 15:14｜E1.4｜进行中｜录音时长上限｜子代理", self.read("coord/progress/E1.md"))
        code, out = self.run_script("15:16", own, "E1.4", "完成", "60 秒自动停")
        self.assertEqual(code, 0, out)

        # 监管者的清单单列出来；处理掉的不再列
        code, out = self.run_script("15:20", own, "S1.1", "待做", "分享页谁都能改（去建设者说）", "S1.2", "待做", "首屏慢",
                                    "S1", "进行中", "巡检 #1：2 条提醒")
        self.assertEqual(code, 0, out)
        code, out = self.run_script("15:30", own, "S1.2", "完成", "建设者改了")
        self.assertEqual(code, 0, out)
        # 同一句话记了两遍：第二遍不算结果，全景上不重复显示
        for _ in range(2):
            code, out = self.run_script("15:30", own, "S1.3", "待做", "改名后第一下被吞")
            self.assertEqual(code, 0, out)
        # “待探索”里写的“无。……”“（已开出……）”不是一项，不画成排队的会话；真的一项照旧
        self.edit("coord/BOARD.md", [("- 首页视觉（等 E1 定稿后再开）",
                                      "- 首页视觉（等 E1 定稿后再开）\n- 无。别的都已由小样定稿\n- （已开出：E9 别的）\n- 无障碍适配")])
        code, out = self.run_script("15:30", own)
        self.assertEqual(code, 0, out)
        self.assertIn("项目钟点：15:30", out)

        md = self.read("coord/PROGRESS.md")
        self.assertNotIn("改名后第一下被吞 — 改名后第一下被吞", md)
        self.assertNotIn("已由小样定稿", md)
        self.assertNotIn("已开出", md)
        self.assertIn("无障碍适配", md)
        self.assertIn("- 语音待办 - 探索者 - 说话到出字：来试一下（15:12 起）", md)
        self.assertIn("监管者的清单（没处理的 2 条，已处理 1 条）：", md)
        self.assertIn("- 待做 S1.1 分享页谁都能改（去建设者说）", md)
        self.assertIn("- 等用户 E1 语音待办 - 探索者 - 说话到出字（高） — 来试一下", md)
        self.assertIn("  - 不成 E1.1 反馈动画 — 一种手机上不转", md)
        self.assertIn("  - 完成 E1.2 格式兼容 — 两种格式都认", md)
        self.assertIn("  - 完成 E1.4 （子代理）录音时长上限 — 60 秒自动停", md)
        self.assertIn("  - 待做 E1.5 自己收尾", md)
        self.assertIn("- 已开 B1 语音待办 - 建设者", md)
        self.assertIn("- 待开 E2 语音待办 - 探索者 - 口语拆待办", md)
        self.assertIn("- 待探索，还没开：首页视觉", md)
        page = self.read("coord/progress.html")
        self.assertNotIn('http-equiv="refresh"', page)  # 不整页刷新：开着的页面自己去读 progress.data.js
        self.assertIn('"progress.data.js?t="', page)
        self.assertIn("监管者的提醒", page)
        self.assertIn("格式兼容", page)
        self.assertIn("没有设期限，节奏由你掌握", page)
        self.assertNotIn("时间盒", page)
        self.assertNotIn("__", page.split("<script>")[0])  # 模板里的占位都换掉了
        for outside in ("http://", "https://", "url(", "@import", "<link"):  # 离线双击就能开：不引任何外面的东西
            self.assertNotIn(outside, page.split("<script>")[0])
        self.assertIn('id="links"', page)  # 树：宽窗口画成分叉图，连线画在这里
        self.assertIn("子代理", page)
        # 页面里嵌的数据和 progress.data.js 里的是同一份；第一次记的文字算标题，之后的算结果
        boot = json.loads(page.split("window.__DF_BOOT__ = ", 1)[1].split(";</script>", 1)[0])
        side = self.read("coord/progress.data.js")
        self.assertTrue(side.startswith("window.__demoFirstUpdate && window.__demoFirstUpdate("), side[:60])
        self.assertEqual(json.loads(side.split("(", 1)[1].rsplit(");", 1)[0]), boot)
        self.assertEqual(boot["nodes"]["S1.2"], {"id": "S1.2", "title": "首屏慢", "note": "建设者改了", "status": "完成",
                                                 "at": "2026-03-14T15:30:00+08:00", "children": [], "agent": False})
        self.assertEqual(boot["nodes"]["E1"]["children"], ["E1.1", "E1.2", "E1.3", "E1.4", "E1.5"])
        self.assertTrue(boot["nodes"]["E1.4"]["agent"])
        self.assertFalse(boot["nodes"]["E1.5"]["agent"])
        self.assertNotIn("feed", boot)
        e1 = next(s for s in boot["sessions"] if s["id"] == "E1")
        self.assertEqual((e1["title"], e1["status"], e1["note"]), ("说话到出字", "等用户", "来试一下"))
        self.assertEqual(boot["nodes"]["E1.1"]["at"], "2026-03-14T15:12:00+08:00")

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
