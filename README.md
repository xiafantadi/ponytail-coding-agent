<div align="center">

# PonyCode

**仓库级 Issue 修复与评测框架**

PonyCode 将真实 Issue、固定仓库版本、修改范围和外部测试组织成可执行任务合同，
让模型在本地完成定位、最小补丁、回归验证和运行证据落盘。

</div>

---

## PonyCode 是什么

PonyCode 是一个 Code Agent Runtime & Evaluation Harness，重点解决 AI SDK 和 Agent 基础设施仓库中的 Provider 兼容、SSE 流式响应、usage 字段、工具协议与跨平台缺陷。一次任务按以下链路执行：

```text
历史 Issue + 修复前 commit + 失败测试
-> 任务合同与修改范围
-> Agent 定位与最小补丁
-> Fail2Pass + Pass2Pass + 范围检查
-> patch + task state + trace + report
```

Runtime 将一次运行拆成几个可观察部分：

- **provider profile**：决定调用哪个模型、哪个 endpoint、用什么协议。
- **context**：把系统提示、仓库信息、skills、记忆和最近对话装进 prompt。
- **tools**：文件读取、搜索、shell、写文件、patch、子 agent 都走统一工具协议。
- **approval / sandbox**：写操作和 shell 命令可以被审批或沙箱限制。
- **session / run evidence**：对话、事件流、trace、report 都写入工作区运行目录。
- **memory / dream**：把 daily log 整理成长期 topic，下次 session 可以继续用。

PonyCode 关注的不是模型是否“声称完成”，而是补丁是否真正修复目标失败、是否破坏已有行为、是否越过改动范围，以及失败发生在哪一层。

## 真实缺陷评测

当前公开证据来自 [`openai/openai-agents-python`](https://github.com/openai/openai-agents-python) 的 3 个历史缺陷。模型只接收缺陷描述和固定在修复前 commit 的仓库，不接收上游补丁；成功由外部测试决定。

| 任务 | 结果 | 主要问题 |
| --- | --- | --- |
| [Issue #3994](https://github.com/openai/openai-agents-python/issues/3994) | 通过 | 空 streamed input 在调用模型前被错误拒绝 |
| [Issue #4144](https://github.com/openai/openai-agents-python/issues/4144) | 未通过，保留失败归因 | handoff 事件被重复发为 `tool_called` |
| [PR #4190](https://github.com/openai/openai-agents-python/pull/4190) | 通过 | 空 session 写入触发无意义远程 Conversation 创建 |

- 3 个真实上游缺陷，5 次真实模型运行，2 个任务至少成功一次。
- 成功补丁均通过 Fail2Pass、Pass2Pass 和修改范围检查。
- 成功补丁平均修改 1.5 个文件、14.5 行；失败运行完整保留在逐行结果中。
- 该结果是小规模案例级修复证据，不是官方 SWE-bench 成绩，也不代表开放任务通用成功率。

完整任务定义、逐行结果、汇总和脱敏补丁见 [evidence/real-issues](evidence/real-issues/README.md)。

其他可复算与回归证据：

| 证据包 | 内容 |
| --- | --- |
| [Minimal-change experiment](evidence/minimal-change/README.md) | 54 次策略对照、逐行结果、usage 与配对差值 |
| [Context and memory ablations](evidence/ablations/README.md) | 上下文与记忆历史消融口径、聚合结果和边界 |
| [Baseline](evidence/baseline/README.md) | 二次开发前的测试与真实 Provider 基线 |
| [Current regression](evidence/regression/README.md) | 当前主分支的全量测试和静态检查结果 |

## SWE-bench-Live 轻量评测

在固定的 SWE-bench-Live `lite` 四题子集上，PonyCode 使用真实模型完成单次修复并接受官方容器终验：

- PonyCode 与固定版本 mini-SWE-agent 均解决 `3/4`，PonyCode 的 Fail2Pass / Pass2Pass 为 `3/4`。
- 四题均在 Agent 运行前冻结；正确补丁、隐藏测试和 Fail2Pass / Pass2Pass 列表不进入 Prompt、Memory 或工作区。
- 两个按实例 ID 哈希固定选择的任务完成真实跨进程恢复：第一进程在第 5 个成功工具步骤及 checkpoint 落盘后终止，第二进程加载同一 Session 继续，`2/2` 正常结束、官方解决 `1/2`。
- 单独的记忆新鲜度探针识别出 `partial-stale`，使 1 条过期文件摘要失效，误信过期状态为 `0`。

这是求职规模的固定子集实验，不是完整榜单成绩，也不证明相对基线具有效率优势。任务清单、逐行结果、补丁和脱敏 Trace 摘要见 [SWE-bench-Live evidence](evidence/swebench-live/README.md)。

## 安装

要求：Python 3.10+，以及至少一个可用的模型 provider key。

一键安装：

```bash
curl -fsSL https://raw.githubusercontent.com/xiafantadi/ponytail-coding-agent/main/install.sh | bash
```

源码安装：

```bash
git clone https://github.com/xiafantadi/ponytail-coding-agent.git
cd ponytail-coding-agent
pip install -e .
```

开发 checkout 里也可以直接跑：

```bash
uv run ponytail
```

## 配置 provider

PonyCode 启动前先解析一个 **provider profile**，主要包含请求协议、API key、服务地址和模型名称：

| 字段 | 作用 |
| --- | --- |
| `protocol` | 请求协议，目前支持 `openai` 和 `anthropic`。 |
| `api_key` | 发给 provider 的 key。 |
| `base_url` | provider endpoint。 |
| `model` | 本次请求使用的模型名。 |

可以通过项目配置、环境变量或命令行参数选择 provider。命令行临时覆盖示例：

```bash
ponytail --provider openai --model gpt-5.4 --base-url https://api.openai.com/v1
ponytail --provider deepseek --approval ask --max-steps 80
ponytail --config /path/to/custom.toml --cwd /path/to/repo
```

完整配置说明见 [docs/configuration.md](docs/configuration.md)。

## 启动

常用入口：

```bash
ponytail                              # 默认 Textual TUI
ponytail --repl                       # 普通终端 REPL
ponytail "找出测试失败的根因"        # one-shot 任务
ponytail --resume latest              # 续接最近 session
ponytail --cwd /path/to/repo          # 指定工作目录
```

常用运行参数：

```bash
ponytail --approval ask               # shell / 写文件前询问
ponytail --approval auto              # 普通操作自动通过
ponytail --approval never             # 非交互模式
ponytail --sandbox best_effort        # 尽量隔离 shell 命令
ponytail --no-auto-dream              # 关闭后台 memory 整合
```

## 日常用法

进入 TUI 或 REPL 后可以直接输入自然语言，也可以用 slash command：

```text
> /help
> /skills
> 找出测试失败的根因
> /plan 重构 provider 配置加载逻辑
> /review
> /test tests/test_config.py
> /remember 这个项目用 DeepSeek 的 Anthropic-compatible endpoint
> /dream
```

常用命令：

| 命令 | 作用 |
| --- | --- |
| `/help` | 查看内置命令。 |
| `/skills` | 列出可用 skills。 |
| `/session` | 查看当前 session、events、run 路径。 |
| `/history` | 列出历史 session。 |
| `/resume latest` | 续接最近 session。 |
| `/context` | 查看 prompt context 使用情况。 |
| `/usage` | 查看 provider、model、token 元数据。 |
| `/memory` | 查看 durable memory 索引。 |
| `/working-memory` | 查看当前 session 工作记忆。 |
| `/remember <text>` | 保存一条 durable note 到 daily log。 |
| `/dream` | 把 daily log 整合成 durable memory topics。 |
| `/plan <topic>` | 进入 plan mode。 |
| `/plan-exit` | 退出 plan mode。 |
| `/agents` | 查看子 agent 状态。 |
| `/model <name>` | 当前 session 临时切模型。 |
| `/compact` | 压缩较早的对话历史。 |
| `/clear` | 开一个新的空 session。 |
| `/exit` | 退出 PonyCode。 |

## PonyCode 能做什么

| 能力 | 说明 |
| --- | --- |
| TUI / REPL / one-shot | 同一个 runtime，通过不同入口使用。 |
| 工具执行 | 文件列表、读文件、搜索、shell、写文件、patch、ask_user、子 agent、todo。 |
| Plan mode | 先读代码和拆计划，再进入可写执行阶段。 |
| 子 agent | 启动 bounded Explore / Worker 任务。 |
| Skills | 复用 `/review`、`/test`、`/commit`、`/simplify` 等工作流。 |
| Memory | working memory、daily logs、durable topics、auto-dream。 |
| Evidence | session JSON、event stream、run trace、task state、report。 |
| Sandbox | 对 `run_shell` 做可选隔离。 |

## 项目结构

```text
ponytail/
├── cli.py                 # CLI 参数、启动模式、REPL 命令
├── config/                # provider profile、TOML、env 解析
├── core/                  # runtime、engine、session、workers、context
├── features/              # memory、skills、sandbox
├── providers/             # OpenAI-compatible / Anthropic-compatible client
├── tools/                 # tool registry 和具体工具
├── tui/                   # Textual TUI
└── evaluation/            # run evidence、metrics、evaluation helpers
```

## 测试

当前工作树在 Windows / Python 3.13 下完成全量回归：`617 passed, 3 skipped`，Ruff 全仓检查通过。执行环境、命令和 warning 说明见 [current regression evidence](evidence/regression/README.md)。

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

## 文档

| 入口 | 内容 |
| --- | --- |
| [配置](docs/configuration.md) | provider profile、环境变量和 sandbox 配置。 |
| [分层记忆 + auto-dream](docs/memory.md) | working memory、daily logs、durable topics 和后台整合。 |
| [Skills](docs/skills.md) | `SKILL.md` 目录结构、内置技能和自定义 workflow。 |
| [Sandbox](docs/sandbox.md) | `run_shell` 隔离模式、backend 选择和文件系统边界。 |

### v3 发布包

| 入口 | 内容 |
| --- | --- |
| [Release pack](release/v3/README.md) | v3 发布材料入口。 |
| [Changelog](release/v3/CHANGELOG.md) | v3 变更摘要。 |
| [Review pack](release/v3/REVIEW.md) | 项目 pitch、架构地图、边界和评审材料。 |
| [Testing](release/v3/TESTING.md) | v3 测试范围和执行摘要。 |
| [真人场景测试包](release/v3/testing/README.md) | 50 个真实使用场景的测试入口。 |
| [测试设计](release/v3/testing/01-test-design.md) | 场景设计、覆盖面和验收口径。 |
| [执行记录](release/v3/testing/02-execution-record.md) | 全量执行结果和失败修复记录。 |
| [Runner 与证据](release/v3/testing/03-runner-and-evidence.md) | 测试 runner、输出目录和证据文件说明。 |
| [场景检查清单](release/v3/testing/04-scenario-checklist.md) | 50 个场景的逐项状态。 |

### v3 学习文档

按这个顺序读，能从整体架构一路落到模块和测试：

| 顺序 | 文档 |
| --- | --- |
| 0 | [阅读索引](release/v3/learning/00-reading-map.md) |
| 1 | [总体架构](release/v3/learning/01-overall-architecture.md) |
| 2 | [Runtime 和 Engine](release/v3/learning/02-runtime-engine.md) |
| 3 | [上下文、记忆和压缩](release/v3/learning/03-context-memory-compact.md) |
| 4 | [工具、权限和沙箱](release/v3/learning/04-tools-permissions-sandbox.md) |
| 5 | [子 agent、计划模式和 Todo](release/v3/learning/05-workers-plan-todo.md) |
| 6 | [Provider 和配置](release/v3/learning/06-providers-config.md) |
| 7 | [Skills、命令、CLI 和 TUI](release/v3/learning/07-skills-commands-cli-tui.md) |
| 8 | [Session、Run 和 Evaluation](release/v3/learning/08-session-run-evaluation.md) |
| 9 | [模块地图](release/v3/learning/09-module-map.md) |
| 10 | [模块学习指南](release/v3/learning/10-module-learning-guide.md) |
| 11 | [Dream 后台记忆整合](release/v3/learning/11-dream-memory-consolidation.md) |

## 许可与分发

当前仓库未附独立开源许可证。公开或再分发前，应以原始代码授权和购买协议为准；本说明不构成额外授权。
