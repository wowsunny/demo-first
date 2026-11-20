# TODO

## 先做

- [ ] 在 Claude Code 里用 `/demo-first` 真实试用一次（`tests/claude-code-trial.md`），记下它在哪一步没照做。斜杠命令加载、终端里的命令行版、真人用户，这三样实跑时都没覆盖到。
- [ ] 在 Manus 上做 `tests/manus-mechanics.md` 第四组的四个小测试（P1～P4），按结果定：派工单怎么发最省（附件、斜杠命令触发技能、规矩进项目主指令，还是整份发），各角色用哪一档。
- [ ] 在真实的 Manus 账号上试用一次技能本身（`tests/manus-mechanics.md` 第〇组），记下它在哪一步没照 SKILL.md 做。
- [ ] 跑完 `tests/manus-mechanics.md` 前三组，把每个编号的结论填进结果表；结论和现在的假设不一样的，改 SKILL.md 的默认做法和 `references/manus-platform.md` 第一节。
- [ ] 用一次完整的冲刺验证整套流程：几小时做一个应用，记下每个环节实际花的时间，尤其是立项到开出任务用了多久。
- [ ] 根据实测定默认值：冲刺档同时开几个任务、探索时间盒的比例、监管者怎么醒来。

## 之后

- [ ] 英文版 SKILL.md、派工单模板和 README。
- [ ] 监管者的检查清单按项目类型细分：网页应用、游戏、浏览器插件。
- [ ] `clock.py` 直接读 `BOARD.md` 的状态，省掉 `--done` 这一步。
- [ ] 支持其他主流 agent。角色、台账和脚本不变，每个平台只换三件事：怎么开任务、怎么读结果、文档放哪。每个平台一份 `references/<平台>-platform.md`。
  - [x] Claude Code：两种开法都写进了 `references/claude-code-platform.md`。后台子代理（主会话替用户和探索者传话）实跑过三轮
  - [ ] Claude Code：子会话的开法（桌面应用里把探索者和建设者开成子会话，用户直接进去聊）实跑一遍，现在只写进了适配文件
  - [ ] SKILL.md 正文现在照 Manus 的说法写，Claude Code 靠适配文件对照着换。把正文改成中性的说法，Manus 的动作也挪进它自己的适配文件
  - [ ] Claude Code 命令行版：现在只能用后台子代理。试一下用 `claude --bg` 开后台会话，或者 Agent Teams，让终端里的用户也能直接和探索者聊
  - [ ] Claude Code：落地建设者用 git worktree 隔离
  - [ ] Claude Code：做成插件，能从插件市场装
  - [ ] Codex
  - [ ] Cursor
  - [ ] Gemini CLI
  - [ ] 其他
