# 最小改动策略与端到端 Token 治理实施任务书

> 用途：作为后续 Vibe Coding 的唯一实施基线。任何 Agent 或开发者都必须按 Step 顺序推进，并以命令、测试和运行产物作为完成证据。

## 0. 项目目标

在现有 Code Agent Runtime & Evaluation Harness 中增加一套可持久化、可恢复、可审计、可评测的最小改动策略，将 Token 治理从输入侧扩展到输出和执行侧：

- 输入侧继续通过分层上下文、历史压缩、记忆召回和 prompt cache 控制成本。
- 输出侧优先复用仓库代码、标准库、平台原生能力和已有依赖，减少无必要代码、文件和依赖。
- 质量侧使用 verifier、Fail2Pass 和 Pass2Pass 证明节省没有破坏正确性、安全性和回归测试。
- 证据侧使用真实模型 A/B 实验，而不是把脚本化回归测试或 Ponytail 官方数据写成本项目结果。

最终能力名称建议统一为：

> Minimal Change Policy（最小改动策略）与 End-to-End Token Governance（端到端 Token 治理）

## 1. 三类完成状态

后续执行中禁止只写“已完成”。必须明确属于以下哪一类：

| 状态 | 定义 | 最低证据 |
| --- | --- | --- |
| `implementation_complete` | 功能已经落入 Runtime，自动化测试通过 | 代码 diff、目标测试、全量测试、trace/report 样例 |
| `experiment_complete` | 真实模型对照实验完整执行，原始数据可复算 | manifest、runs.csv、summary.json、全部运行目录 |
| `resume_ready` | 质量门禁通过，收益达到预注册标准，可以写入简历 | 可复现报告、失败案例、实际指标、公开复现命令 |

以下情况只能标记为 `in_progress`：

- 只创建了类、函数、命令或空目录。
- 只写了测试，但测试没有先失败再通过。
- 只运行了单个 happy path（正常路径）。
- 只使用 `ScriptedModelClient`（脚本化模型客户端）验证行为。
- 只生成汇总报告，没有保留原始运行记录。
- 真实模型实验只有一组，没有 baseline（基线组）。
- Token 降低了，但 verifier、Fail2Pass、Pass2Pass 或安全测试下降。

## 2. 全局执行规则

### 2.1 Agent 每次只能执行一个 Step

交给 Coding Agent 时使用以下任务头：

```text
只执行 MINIMAL_CHANGE_VIBECODING_IMPLEMENTATION_GUIDE.md 中的 Step N。
开始前读取该 Step 的目标、允许改动范围、前置条件和验收门禁。
不得顺手实现后续 Step，不得修改验收标准，不得删除或跳过失败测试。
结束时必须报告：修改文件、测试命令、退出码、产物路径、未完成项。
只有全部硬门禁通过，才允许将 Step 标记为 completed。
```

### 2.2 禁止伪完成

- 禁止通过修改测试预期来迎合错误实现。
- 禁止把测试改成 `skip`、`xfail` 或降低断言强度。
- 禁止删除失败运行、超时运行和成本较高的样本。
- 禁止只汇报最好一次结果，正式实验必须包含全部 repetition（重复运行）。
- 禁止使用估算 Token 替代 provider 返回的 usage；缺失时必须记录为 `null`。
- 禁止把 Ponytail 的官方数据、其他模型数据或历史版本数据写成本轮结果。
- 禁止在看完结果后删除不利任务、修改主要指标或调整成功阈值。
- 禁止以模型最终回答中的“完成”作为任务通过依据。

### 2.3 每个 Step 的证据格式

每步完成后追加一条实施记录：

```markdown
## Step N 执行记录

- git_commit: <sha>
- started_at: <ISO-8601>
- finished_at: <ISO-8601>
- changed_files: [...] 
- commands:
  - command: <完整命令>
    exit_code: 0
    output_path: <日志路径>
- artifacts: [...] 
- acceptance: passed | failed
- unresolved: [...] 
```

原始日志放入 `artifacts/minimal-change/<run_stamp>/`。面向求职公开的脱敏汇总放入 `evidence/minimal-change/`。

## 3. 最终目录规划

```text
pico/features/minimal_policy.py
pico/evaluation/minimal_change.py
scripts/run_minimal_change_experiment.py
benchmarks/minimal_change/tasks.json
benchmarks/minimal_change/fixtures/
tests/test_minimal_policy.py
tests/test_minimal_policy_prompt.py
tests/test_minimal_policy_resume.py
tests/test_minimal_policy_acceptance.py
tests/test_minimal_policy_safety.py
tests/test_minimal_change_evaluator.py
tests/test_minimal_change_metrics.py
tests/test_minimal_change_reproducibility.py
evidence/minimal-change/README.md
evidence/minimal-change/manifest.json
evidence/minimal-change/runs.csv
evidence/minimal-change/summary.json
evidence/minimal-change/report.md
```

实际实现可以根据现有模块边界微调文件名，但不得把策略、评测器和原始证据混在单个大文件中。

---

## Step 0：冻结基线与证据合同

### 目标

在修改功能前记录当前仓库状态、测试状态和现有 benchmark 性质，避免后续无法判断变化来自新策略还是原有代码。

### 任务

1. 确认当前目录属于版本化 Git 仓库；若不是，立即停止并由用户决定指向正确仓库或完成版本化，不得由 Agent 擅自初始化并伪造历史基线。
2. 记录 Git SHA、工作区 dirty 状态、Python 版本、操作系统、依赖版本和时区。
3. 运行 lint、全量测试、现有 12 个固定 Harness 回归和优先级人工场景门禁。
4. 明确现有 12 个任务使用脚本化模型，只证明 Runtime 合同稳定，不证明真实模型效果。
5. 创建证据 schema，冻结后续主要指标、计算公式和成功阈值。

### 必须执行

```powershell
git rev-parse --show-toplevel
git status --short
git rev-parse HEAD
uv run ruff check .
uv run pytest tests -q
uv run pytest tests/test_evaluator.py -q
uv run python scripts/run_v3_human_scenario_gate.py
```

### 硬验收门禁

- 所有命令保存完整输出和退出码。
- `git rev-parse --show-toplevel` 和 `git rev-parse HEAD` 必须成功；正式实验不接受仅用当前时间或随机 UUID 代替源码版本。
- `ruff`、全量 `pytest`、`test_evaluator.py` 的退出码均为 0。
- 人工场景门禁若失败，必须先记录既有失败并判断是否与本项目相关，不能静默忽略。
- `manifest.json` 至少包含 `git_sha`、`dirty`、`python`、`platform`、`timezone`、`test_commands`。
- 指标定义在实验前落盘，至少包括 verifier pass rate、Fail2Pass、Pass2Pass、billable tokens、added LOC、changed files、tool steps、attempts、duration 和 cost。

### 不通过条件

- 没有保存基线命令输出。
- 当前目录不是 Git 仓库但仍继续实施或运行正式实验。
- 基线测试失败但继续开发。
- 使用当前简历中的历史数字代替本次基线。
- 没有区分脚本化回归和真实模型评测。

### 产物

```text
artifacts/minimal-change/baseline/manifest.json
artifacts/minimal-change/baseline/ruff.txt
artifacts/minimal-change/baseline/pytest.txt
artifacts/minimal-change/baseline/harness-regression.txt
artifacts/minimal-change/baseline/scenario-gate.txt
```

---

## Step 1：建立最小改动策略领域模型

### 目标

实现一个不依赖 CLI、Prompt 或 provider 的纯策略模块，确保模式、规则版本和安全边界有单一事实来源。

### 允许改动范围

```text
pico/features/minimal_policy.py
tests/test_minimal_policy.py
```

### 必须实现

- 模式：`off`、`observe`、`enforce`。
- 默认模式：`off`，避免功能上线后无意改变所有任务。
- `observe`：只记录最小化机会，不改变 Prompt。
- `enforce`：向模型注入紧凑规则。
- 规则版本：例如 `minimal-policy-v1`。
- 核心决策阶梯：不实现、复用仓库、标准库、平台原生、已有依赖、最少自定义代码。
- 安全保留项：输入校验、数据安全异常处理、安全控制、权限控制、可访问性、明确需求、非平凡逻辑测试。
- 序列化和反序列化：能安全写入 session。

### 测试要求

先编写失败测试，再实现代码。测试至少覆盖：

- 默认关闭。
- 三种合法模式解析。
- 非法模式拒绝且不修改旧状态。
- 规则文本包含全部安全保留项。
- 序列化再恢复后字段一致。
- 同一版本规则哈希稳定。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_policy.py -q
uv run ruff check pico/features/minimal_policy.py tests/test_minimal_policy.py
```

- 目标测试退出码为 0。
- 测试数量不少于 6 个。
- 核心模块不得导入 CLI、Runtime、provider 或 evaluator。
- 规则文本必须控制在预设长度内，建议不超过 800 个字符；超出必须说明原因并增加 Token 成本测试。

### 不通过条件

- 只有常量字符串，没有模式、版本和序列化合同。
- 通过全局变量保存状态。
- 为追求短代码删除安全边界。

---

## Step 2：增加 CLI 与 Skill 入口

### 目标

让用户可以显式查看和切换策略，并提供一次性最小化审查能力。

### 允许改动范围

```text
pico/cli.py
pico/commands/slash.py
pico/features/skills_bundled.py
pico/features/minimal_policy.py
tests/test_minimal_policy.py
tests/test_minimal_policy_acceptance.py
```

### 必须实现

- `/minimal`：显示当前模式、规则版本和是否进入 Prompt。
- `/minimal off|observe|enforce`：切换模式，不调用模型。
- `/minimal-review [focus]`：审查当前 diff 中的重复实现、无必要抽象、新依赖和多余文件。
- 模式切换产生结构化 `minimal_policy_changed` 事件。
- CLI 错误必须明确返回合法选项，不得静默回退。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_policy.py tests/test_minimal_policy_acceptance.py -q
uv run pytest tests/test_skills_acceptance.py tests/test_pico.py tests/test_v3_runtime.py -q
```

- `/minimal` 和模式切换过程中模型调用次数为 0。
- `/minimal-review` 可以进入现有 Skill Runtime，并受现有工具权限约束。
- `/skills` 能列出审查 Skill。
- 原有 `/review`、`/test`、`/commit`、`/simplify` 行为不变。

### 不通过条件

- 每次查看状态都会调用模型。
- `/minimal-review` 绕过工具白名单或权限审批。
- 模式只存在 CLI 局部变量中，下一轮立即丢失。

---

## Step 3：接入 Prompt 与 Prompt Cache

### 目标

只在 `enforce` 模式向稳定前缀注入紧凑规则，并确保缓存身份随模式和规则版本正确变化。

### 允许改动范围

```text
pico/core/runtime.py
pico/core/context_manager.py
pico/core/context_report.py
pico/core/context_usage.py
pico/features/minimal_policy.py
tests/test_minimal_policy_prompt.py
tests/test_context_manager.py
tests/test_context_orchestrator.py
```

### 必须实现

- `off` 和 `observe` 不增加模型 Prompt 字符数。
- `enforce` 只注入紧凑规则，不注入完整 Ponytail `SKILL.md`。
- 规则放入稳定前缀的 Rules 区域，不能仅依赖易被裁剪的历史消息。
- Prefix hash 必须包含模式、规则版本和规则文本。
- 同一模式连续请求的 prefix hash 保持稳定。
- 模式或规则版本变化时 prefix hash 必须变化。
- prompt metadata 记录模式、规则版本、规则字符数和规则哈希。

### 测试要求

- 对比三种模式生成的 Prompt。
- 构造高压上下文，确认 `current_request` 仍完整保留。
- 确认 `enforce` 规则未被普通 history 裁剪移除。
- 确认 `off -> enforce -> off` 的缓存 key 按预期变化和恢复。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_policy_prompt.py tests/test_context_manager.py tests/test_context_orchestrator.py -q
uv run pytest tests/test_context_governance_acceptance.py -q
```

- 所有目标测试通过。
- `off` 相对基线 Prompt 增量为 0。
- `enforce` 的规则增量有明确断言，不能只断言“包含某个单词”。
- current request 完整保留率在测试用例中为 100%。

### 不通过条件

- 每轮把完整 Skill 正文重复塞进 Prompt。
- 模式变化但缓存 key 不变。
- 为保留策略规则而裁掉当前请求。

---

## Step 4：实现 Session、Checkpoint 与 Resume 联动

### 目标

确保策略状态能够跨轮次和中断恢复，同时不把过期代码事实当作策略状态恢复。

### 允许改动范围

```text
pico/core/runtime.py
pico/core/task_state.py
pico/core/checkpoint*.py
pico/features/minimal_policy.py
tests/test_minimal_policy_resume.py
```

### 必须实现

- session 保存模式、规则版本、激活来源和更新时间。
- checkpoint 保存当时模式和规则哈希。
- resume 后恢复策略模式。
- 工作区漂移时策略配置可以保留，但旧文件摘要仍按 freshness 规则失效。
- 未识别的未来规则版本不得悄悄按当前版本执行，应进入兼容性提示或安全回退。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_policy_resume.py tests/test_runtime.py tests/test_context_retention.py tests/test_llm_handoff_e2e.py -q
```

- 正常恢复、文件 freshness mismatch、workspace mismatch 三类场景均有测试。
- 恢复后 Prompt 中的策略状态与 session 一致。
- stale file summary 不因策略恢复重新进入 Prompt。
- report 和 trace 能定位恢复采用的策略版本。

### 不通过条件

- 只测试同一进程内的对象复用，没有从落盘 JSON 恢复。
- 工作区漂移后继续信任旧摘要。
- 未知版本直接忽略且不留事件。

---

## Step 5：增加 Trace、Task State 与 Report 证据字段

### 目标

让每次运行都能回答：是否启用策略、策略增加了多少 Prompt、改了多少代码、是否新增依赖、是否通过验证。

### 允许改动范围

```text
pico/core/task_state.py
pico/core/runtime.py
pico/core/run_store.py
pico/core/completion_governance.py
pico/core/runtime_consumers.py
tests/test_minimal_policy_acceptance.py
tests/test_run_store.py
```

### 必须记录

```text
minimal_policy_mode
minimal_policy_version
minimal_policy_hash
minimal_policy_prompt_chars
changed_files
added_lines
deleted_lines
dependencies_added
input_tokens
cached_input_tokens
output_tokens
reasoning_tokens
tool_steps
attempts
duration_ms
verification_status
```

无法从 provider 或代码差异可靠获得的字段必须写 `null`，不得填 0 冒充已测量。

### 必须新增事件

- `minimal_policy_changed`
- `minimal_policy_applied`
- `minimality_audit_completed`

事件必须包含 `run_id`、时间、模式、版本和规则哈希。不得在每个无关工具调用后重复写相同大段规则文本。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_policy_acceptance.py tests/test_run_store.py tests/test_engine_transitions.py -q
```

- `task_state.json`、`trace.jsonl` 和 `report.json` 对同一 run 的模式、版本和哈希一致。
- trace 保持 append-only（只追加）语义。
- 敏感 provider 配置、API key、完整环境变量不得进入产物。
- `null` 与真实 0 在 schema 中可区分。

### 不通过条件

- 只在日志字符串中记录，没有结构化字段。
- summary 中出现了原始 runs 无法复算的数据。
- Token 缺失时使用字符数估算后仍命名为 `input_tokens`。

---

## Step 6：实现最小化审计与安全门禁

### 目标

把“少写代码”约束为可检查的工程结果，而不是模型自我评价。

### 必须实现

- 统计新增/删除代码行和修改文件数。
- 检测 `pyproject.toml`、`package.json` 等依赖清单中的新增依赖。
- 根据任务合同检查是否修改允许范围之外的文件。
- 检查 changed paths 是否有对应验证证据。
- 安全任务由外部 verifier 执行，策略文本不能替代安全测试。
- 审计发现只作为结构化 finding（发现项）；除明确安全和范围违规外，不因代码行较多直接阻断任务。

### 测试要求

- 新增无必要依赖能够被发现。
- 修改范围外文件能够被阻断或判失败。
- 删除输入校验后安全 verifier 必须失败。
- 合理的多文件根因修复不能仅因文件多而误判失败。
- 非 Git 工作区的指标行为有明确定义，无法计算时写 `null`。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_policy_safety.py tests/test_final_readiness.py tests/test_verification.py -q
```

- 至少包含 1 个故意不安全的实现作为负例，测试必须证明 verifier 能抓住它。
- 至少包含 1 个合法多文件修改作为反误报用例。
- 审计结果进入 report，并能从原始 diff 或任务合同复算。

### 不通过条件

- 让 LLM 自己判断“我的实现很精简”作为唯一证据。
- 以固定 LOC 上限阻断所有复杂任务。
- 最小化规则可以覆盖权限、安全或 verifier 结果。

---

## Step 7：建立最小改动 Benchmark Schema

### 目标

为真实代码任务定义固定、可验证、可扩展的任务合同，且与现有 Harness 回归任务严格分开。

### 允许改动范围

```text
benchmarks/minimal_change/tasks.json
pico/evaluation/minimal_change.py
tests/test_minimal_change_evaluator.py
```

### 每个任务必填字段

```text
task_id
category
fixture_repo
fixture_revision
prompt
allowed_tools
step_budget
timeout_seconds
failing_tests
regression_tests
holdout_verifier
allowed_change_paths
forbidden_change_paths
expected_behavior
overbuild_opportunity
```

`target_files` 可以用于事后定位分析，但不得直接泄露给模型，除非任务本身应该提供该信息。

### 加载时必须校验

- ID 唯一。
- fixture 和验证命令存在。
- `failing_tests` 在未修复 fixture 上确实失败。
- `regression_tests` 在未修复 fixture 上确实通过。
- allowed 和 forbidden 范围不冲突。
- 每个任务使用全新 fixture copy、全新 session 和全新 run 目录。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_change_evaluator.py -q
```

- schema 缺少任一必填字段时加载失败。
- 前置测试状态不符合合同的任务必须标记为 `invalid_task`，不能进入实验。
- fixture 原目录在实验后内容哈希不变。
- 每行结果可以反查 task state、trace、report 和 patch。

### 不通过条件

- 复用现有 12 个脚本化任务并改名为真实模型 benchmark。
- verifier 只检查文件是否存在。
- Prompt 中直接给出正确补丁或精确答案。

---

## Step 8：构建 18 个真实任务 Fixture

### 目标

形成对最小改动策略有区分度、同时覆盖正确性和安全性的本地代码任务集。

### 任务分布

| 类别 | 数量 | 最低覆盖 |
| --- | ---: | --- |
| 过度实现陷阱 | 6 | 仓库复用、标准库、平台原生、已有依赖、无必要抽象、无必要文件 |
| 真实缺陷修复 | 6 | 单文件边界、多文件调用链、配置迁移、解析错误、共享根因、兼容性回归 |
| 安全与最小化对抗 | 6 | 路径逃逸、SQL 参数化、恶意 CSV、令牌校验、配额耗尽、数据丢失异常 |

### 每个 Fixture 的质量要求

- 至少 1 个修复前失败的目标测试。
- 至少 2 个修复前通过的回归测试；简单任务不足时需解释。
- 至少 1 个不在 Prompt 中明示的 holdout verifier（留出验证器）。
- 任务描述不能暗示具体实现路径。
- 正确解不唯一，但 verifier 必须验证行为而非字符串。
- 任务初始状态可重复构造，文件哈希固定。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_change_evaluator.py -q
uv run python scripts/run_minimal_change_experiment.py --validate-only
```

- 18 个任务全部通过任务合同预检。
- 每个任务修复前 `Fail2Pass` 目标确实失败，`Pass2Pass` 基线确实通过。
- 类别数量和覆盖项由自动化测试断言，不依赖人工数表格。
- 不得存在只替换一段固定文本就通过的“伪代码任务”。

### 不通过条件

- 任务主要是 README 或文本替换。
- 所有任务都只有 happy path。
- 验证器只检查关键字、文件存在或模型 final answer。

---

## Step 9：实现 Fail2Pass、Pass2Pass 与失败归因

### 目标

区分“修复目标测试”和“保持原有功能”，避免模型通过硬编码或破坏其他功能获得假通过。

### 必须执行的验证顺序

```text
复制 fixture
-> 修复前运行 failing_tests，必须失败
-> 修复前运行 regression_tests，必须通过
-> Agent 执行任务
-> 修复后运行 failing_tests
-> 修复后运行 regression_tests
-> 运行 holdout_verifier
-> 检查修改范围和运行状态
```

### 每次运行必须记录

```text
fail2pass_passed
fail2pass_total
pass2pass_passed
pass2pass_total
holdout_verifier_passed
verifier_exit_code
verifier_stdout_path
verifier_stderr_path
failure_category
```

### 失败分类至少包括

```text
invalid_task
model_error
tool_error
permission_denied
budget_exceeded
timeout
patch_not_applied
fail2pass_failed
pass2pass_regression
holdout_verifier_failed
scope_violation
missing_usage
infrastructure_error
```

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_change_evaluator.py tests/test_minimal_change_metrics.py -q
```

- 使用故意硬编码的补丁证明 Pass2Pass 或 holdout verifier 能将其判失败。
- 任何验证阶段失败都不能被最终回答覆盖。
- 失败任务仍保留 patch、trace、report 和 usage。
- 汇总结果中的计数与逐行结果严格一致。

### 不通过条件

- 用单个总测试命令替代 Fail2Pass 和 Pass2Pass 分项记录。
- 只记录布尔值，不记录测试数量和原始输出路径。
- 删除失败任务后再计算通过率。

---

## Step 10：实现三组真实模型实验 Runner

### 目标

在相同任务、相同模型和相同预算下隔离最小改动策略的真实效果。

### 三个实验组

| arm（实验组） | 配置 |
| --- | --- |
| `baseline` | 最小改动策略关闭，不追加 YAGNI 提示 |
| `short_yagni` | 只追加一句固定的 YAGNI 与优先最小实现提示 |
| `minimal_policy` | 启用完整 `enforce` 策略 |

### Runner 必须支持

```text
--provider-profile
--model
--tasks
--arms
--repetitions
--seed
--max-steps
--timeout
--output-dir
--validate-only
--resume-manifest
```

### 隔离要求

- 每个 `(task, arm, repetition)` 使用独立进程或等价的完全隔离上下文。
- 禁用用户全局 Skill、全局 memory 和非实验插件，防止 baseline 污染。
- 三组使用相同模型版本、解码参数、工具集合、步数预算和超时。
- 运行顺序由固定 seed 随机化，并写入 manifest。
- provider 自动重试必须计入 attempts、Token、成本和耗时。
- prompt cache 的启用状态必须三组一致；缓存输入和非缓存输入分开统计。

### 开发期门禁

```powershell
uv run python scripts/run_minimal_change_experiment.py --validate-only
uv run python scripts/run_minimal_change_experiment.py --tasks 3 --arms baseline,short_yagni,minimal_policy --repetitions 1 --output-dir artifacts/minimal-change/smoke
```

- 3 个任务、3 个实验组共 9 个运行全部产生完整工件。
- 如果 provider usage 缺失，Runner 必须明确标记 `missing_usage`，不能生成 Token 收益结论。
- baseline 的 Prompt 中不得出现 minimal policy 规则。
- minimal policy 组的 report 必须记录规则版本和哈希。

### 不通过条件

- 三组共享同一个 session/history。
- baseline 被项目级或用户级 Skill 污染。
- 失败后手动只重跑失败组且不记录重跑原因。

---

## Step 11：实现指标聚合与可复算报告

### 目标

从逐次运行原始数据生成统一结果，不允许在报告中手填指标。

### 主要指标公式

```text
verifier_pass_rate = verifier_passed_runs / valid_runs
fail2pass_rate = passed_failing_tests / total_failing_tests
pass2pass_rate = passed_regression_tests / total_regression_tests
tokens_per_verified_pass = all_billable_tokens / verifier_passed_runs
cost_per_verified_pass = all_cost_usd / verifier_passed_runs
task_level_token_delta = (treatment_tokens - baseline_tokens) / baseline_tokens
task_level_loc_delta = (treatment_added_loc - baseline_added_loc) / baseline_added_loc
```

当 `verifier_passed_runs = 0` 或 baseline 为 0 时必须输出 `null` 和原因，禁止除零后填 0。

### 报告必须同时展示

- 每个任务逐组结果。
- 平均值、中位数和任务级 paired delta（配对差值）。
- 全部失败分类和基础设施失败。
- Token、成本、LOC、文件数、依赖数、工具步数和耗时。
- 收益最大的任务、无收益任务和负收益任务。
- 模型、样本量、温度、缓存、超时和限制。

### 硬验收门禁

```powershell
uv run pytest tests/test_minimal_change_metrics.py tests/test_minimal_change_reproducibility.py -q
```

- 使用手工可计算的小样本 fixture 验证每个公式。
- `summary.json` 能完全由 `runs.csv` 重新生成，结果一致。
- 报告不得隐藏失败或只展示 treatment 相对最好的一组。
- 所有百分比同时展示分子、分母或样本量。

### 不通过条件

- 平均 Token 只统计成功运行，从而排除失败成本。
- 把输出 Token 降低直接等同于代码量降低。
- 把 cached input token 按完整价格计费或完全忽略缓存成本。

---

## Step 12：执行正式实验

### 目标

生成可以支持求职陈述的最终真实模型证据。

### 正式实验配置

- 任务数：18。
- 实验组：3。
- 每个 cell 重复：5 次。
- 总运行数：`18 × 3 × 5 = 270`。
- 主模型：固定一个明确版本，用于简历主结果。
- 泛化检查：可选第二模型，在 6 个代表任务上运行，不与主结果混合。

### 正式运行前硬门禁

- Step 0 至 Step 11 全部通过。
- Git 工作区干净或 manifest 完整记录 diff。
- 18 个任务预检全部通过。
- smoke run 无实验污染、usage 缺失或 schema 错误。
- provider 额度、超时和预估成本已确认。
- 成功阈值已冻结，不得在运行后修改。

### Resume-ready 预注册阈值

以下阈值是“可以形成强简历结果”的门禁，不是当前已有成果：

- `minimal_policy` verifier pass rate 不低于 baseline。
- Fail2Pass 不低于 baseline。
- Pass2Pass 不低于 baseline，安全任务 Pass2Pass 和 holdout verifier 为 100%。
- `tokens_per_verified_pass` 相对 baseline 降低至少 15%。
- 任务级 added LOC 中位数相对 baseline 降低至少 20%。
- 不得增加未授权依赖和范围外修改。

### 异常处理规则

- 模型失败、超时、权限拒绝均作为有效运行结果保留。
- 明确属于基础设施故障的运行标记 `infrastructure_error`，保留原始记录。
- 某个 cell 基础设施故障超过 5% 时，该 cell 整体重新执行，旧数据不得删除。
- 不得只重跑 treatment 直到结果变好。
- 如果结果未达阈值，功能可以是 `implementation_complete`，但不得标记 `resume_ready`。

### 硬验收门禁

- 270 个计划运行均能在 manifest 中找到状态。
- `runs.csv` 行数等于计划运行数，不因失败减少。
- 每行都能定位到 trace、report、patch 和 verifier 输出。
- summary 由固定脚本生成并可二次复算。
- 抽查至少 10 个运行，文件路径和指标与原始产物一致。

---

## Step 13：发布求职证据包

### 目标

让面试官无需相信口头描述，也能快速确认任务设计、运行方式、结果和限制。

### 必须发布

```text
evidence/minimal-change/README.md
evidence/minimal-change/manifest.json
evidence/minimal-change/runs.csv
evidence/minimal-change/summary.json
evidence/minimal-change/report.md
evidence/minimal-change/sample-runs/
```

### README 必须包含

- 解决的问题和策略边界。
- baseline、short YAGNI、minimal policy 三组定义。
- 任务类别、模型版本、样本量和运行命令。
- 主要质量和效率结果。
- 至少 1 个有效收益案例、1 个无收益案例、1 个失败或负收益案例。
- 复现步骤和预计成本。
- 已知限制，不得声称官方 SWE-bench 成绩。

### 脱敏要求

- 删除 API key、账户、内部 base URL 和本地绝对用户路径。
- 保留模型版本、公开 provider 类型、参数、Git SHA 和 fixture revision。
- trace/report 示例必须经过现有 redact（脱敏）链路。

### 硬验收门禁

- 在一个新的临时目录按 README 命令至少复现 3 个 smoke 任务。
- 公开 summary 与 runs.csv 重新聚合结果一致。
- 所有 Markdown 链接有效。
- 不包含 Ponytail 官方结果作为本项目结果。
- 不包含“生产上线”“企业内部使用”等未经证明的描述。

---

## Step 14：更新简历和面试材料

### 前置条件

只有 `resume_ready` 成立后才能执行。若正式实验未达阈值，只能写“实现最小改动策略及评测能力”，不能写收益数字。

### 简历解决方案候选表述

> **端到端 Token 与改动复杂度治理：** 输入侧通过分层上下文、记忆召回和缓存控制 Prompt 成本，输出侧引入最小改动策略，优先复用仓库能力、标准库和原生实现，并以外部测试约束安全与回归。

### 简历成果模板

> **策略收益验证：** 在 `<任务数>` 个真实仓库任务上完成基线、短提示和完整策略三组对照；在 verifier、Fail2Pass 和 Pass2Pass 不下降的前提下，每个验证通过任务 Token 降低 `<X%>`，新增代码量降低 `<Y%>`，工具步数降低 `<Z%>`。

`X/Y/Z` 必须直接来自最终 `summary.json`，且简历中的任务数、模型数和重复次数必须与 manifest 一致。

### 面试必须能回答

- 为什么完整 Skill 可能增加输入 Token？
- 为什么使用 `tokens_per_verified_pass` 而不是只看平均 Token？
- 如何证明最小化没有删除安全校验？
- baseline 如何避免被全局 Skill 污染？
- 为什么现有 12 个 ScriptedModelClient 任务不能证明模型效果？
- 哪些任务没有收益，原因是什么？
- 如果换模型后收益消失，项目结论应如何收缩？

### 硬验收门禁

- 简历每个数字都能定位到 `summary.json` 和计算公式。
- 面试文档保留失败样本和限制，不只背成功案例。
- 不使用“官方 SWE-bench 成绩”“生产效果”等越界表达。

## 4. 阶段总门禁

### Gate A：策略可用

需要通过 Step 0 至 Step 6。此时只能声称：

> 已将最小改动策略接入 Runtime，支持模式持久化、恢复联动和运行审计。

不能声称 Token 已下降。

### Gate B：评测可用

需要通过 Step 7 至 Step 11。此时只能声称：

> 已构建真实仓库任务、Fail2Pass / Pass2Pass 和三组对照评测框架。

不能声称策略有效，除非正式实验完成。

### Gate C：证据可用

需要通过 Step 12 和 Step 13。此时可以报告实际实验结果，但未达到预注册阈值时不得使用“显著降低”“保证不下降”等强结论。

### Gate D：求职可用

需要通过 Step 14，且所有数字可反查、可复算、可解释。只有此时才能把实际收益写入简历项目成果。

## 5. 每次提交前的最终检查表

```text
[ ] 本次只执行了一个 Step
[ ] 没有修改或弱化验收测试
[ ] 新增测试经历了失败到通过
[ ] 目标测试退出码为 0
[ ] 规定的回归测试退出码为 0
[ ] 运行产物已落盘且可反查
[ ] 缺失数据记录为 null，而不是 0
[ ] 失败和超时样本没有被删除
[ ] 文档中的状态符合 implementation / experiment / resume 三类定义
[ ] 没有把外部项目数据或历史数据当成本轮结果
```

## 6. 推荐实施节奏

| 时间 | 目标 | 对应 Step |
| --- | --- | --- |
| 第 0.5 天 | 冻结基线和证据合同 | Step 0 |
| 第 1 天 | 完成策略模型、CLI 和 Prompt 接入 | Step 1 至 Step 3 |
| 第 2 天 | 完成恢复、审计和安全门禁 | Step 4 至 Step 6 |
| 第 3 至 5 天 | 完成 schema、18 个 fixture 和双验证 | Step 7 至 Step 9 |
| 第 6 天 | 完成三组 Runner 与指标聚合 | Step 10 至 Step 11 |
| 第 7 天以后 | 运行正式实验、发布证据、更新简历 | Step 12 至 Step 14 |

进度以 Gate 是否通过为准，不以日期为准。日期到了但证据不足，状态仍然是未完成。
