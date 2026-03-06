# Junment Context Agent

这是一个面向 Claude Code hook 的前置上下文编排器。

它的目标不是替代 Claude Code，而是在 `UserPromptSubmit` 触发时，先用一个便宜或免费的 OpenAI-compatible 模型判断是否需要补充仓库上下文；如果需要，再结合本地确定性检索为 Claude Code 生成更干净、更聚焦的 `additionalContext`。

## 当前状态

- 已接入真实 `mcp-agent` runtime
- 已提供可执行 CLI：`context_agent.cli`
- 已兼容 Claude Code `UserPromptSubmit` 官方 JSON 输入
- 已接入 OpenAI-compatible provider 调用链
- 已支持 `gate_model` / `judge_model` / `summary_model` 分离配置
- 已实现异步并行 LLM rerank
- 已将 `basedpyright` 收紧为正式运行时依赖，GitHub + `uv` 安装时默认具备 Python LSP discovery 能力，并支持可选的 TS/JS LSP discovery
- 已修复 CLI 输出 hook JSON 后不退出的问题

## 当前工作流

当前主链路如下：

1. `gate`
   - 用小模型判断当前问题是否需要额外仓库上下文
   - 例如：`commit` 这类短操作通常会被判为不需要上下文
2. `planner`
   - 目前仍是本地轻量提取
   - 从 prompt 中提取路径、symbol、搜索词、任务类型
3. `discovery`
   - 使用本地确定性工具找候选：
     - 显式路径
     - LSP symbol
     - grep
     - docs
4. `judge`
   - 对每个候选做独立评分
   - 在 LLM workflow 已启用时，并行异步调用 `judge_model` 做 rerank
5. `selection`
   - 根据阈值、去重和 `top_k` 选出最终候选
6. `summarizer`
   - 在 LLM workflow 已启用时，使用 `summary_model` 对最终候选做压缩总结
   - 再拼装成 `additionalContext` 返回给 Claude Code

## Provider 配置

推荐策略：

- `API key` 用环境变量传入
- 默认情况下，只传 `API key` 就会使用 OpenRouter + `stepfun/step-3.5-flash:free`
- 如果你要切换 provider 或模型，再通过环境变量或 hook 命令参数覆盖 `base_url` / `model`
- 不要把密钥塞进 hook stdin payload

### 必要环境变量

- `JUNMENT_LLM_API_KEY`
  - provider API key

### 可选环境变量

- `JUNMENT_LLM_BASE_URL`
  - OpenAI-compatible endpoint 根地址
  - 默认值：`https://openrouter.ai/api/v1`
  - 例如 OpenRouter 常见写法：`https://openrouter.ai/api/v1`

### 模型配置

默认情况下，`JUNMENT_LLM_MODEL` 已内置为 `stepfun/step-3.5-flash:free`。

如果你要覆盖默认模型配置，仍然可以使用下面两种方式之一：

- 方式 1：设置 `JUNMENT_LLM_MODEL`
- 方式 2：同时设置：
  - `JUNMENT_GATE_MODEL`
  - `JUNMENT_JUDGE_MODEL`
  - `JUNMENT_SUMMARY_MODEL`

其中：

- `JUNMENT_LLM_MODEL`
  - 默认模型
  - 默认值：`stepfun/step-3.5-flash:free`
  - 如果未单独设置 gate / judge / summary，则会作为它们的默认值
- `JUNMENT_GATE_MODEL`
  - 用于判断是否需要上下文
- `JUNMENT_JUDGE_MODEL`
  - 用于逐候选 rerank
- `JUNMENT_SUMMARY_MODEL`
  - 用于压缩最终候选

### CLI 覆盖参数

下面这些配置也可以直接通过 CLI 参数覆盖，而不是必须写进环境变量：

- `--llm-base-url`
- `--llm-model`
- `--gate-model`
- `--judge-model`
- `--summary-model`

### 运行参数

- `JUNMENT_LLM_TIMEOUT_SECONDS`
  - LLM 请求超时，默认 `30`
- `JUNMENT_LLM_MAX_CONCURRENCY`
  - rerank 并发数，默认 `4`

### 本地选择参数

- `CONTEXT_AGENT_MAX_CANDIDATES`
  - discovery 阶段候选上限，默认 `12`
- `CONTEXT_AGENT_SCORE_THRESHOLD`
  - 最终保留阈值，默认 `55`
- `CONTEXT_AGENT_TOP_K`
  - 最终注入条目上限，默认 `6`
- `CONTEXT_AGENT_MAX_EXCERPT_LINES`
  - 文件摘录最大行数，默认 `60`

## 启用条件与短路行为

只有同时满足下面两个条件，才会进入完整的 LLM 上下文构造流程：

- 已有可用 provider 配置：
  - `llm_base_url`
  - `llm_api_key`
- 已有完整模型配置：
  - 默认的 `JUNMENT_LLM_MODEL`
  - 或完整的 `gate/judge/summary` 三模型配置

如果不满足这些条件，workflow 会：

- 直接返回空 `additionalContext`
- 不进入 discovery
- 不进入 rerank
- `summary` 中会写明是 provider 或 model 配置不完整

这是一个全新项目，当前**不保留旧环境变量兼容说明**。

## Claude Code hook 最小接入

在项目根目录创建 `.claude/settings.json`：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && JUNMENT_LLM_API_KEY=\"$OPENROUTER_API_KEY\" uv run python -m context_agent.cli",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

说明：

- `UserPromptSubmit` 不支持 `matcher`，每次提交用户问题都会触发
- `CLAUDE_PROJECT_DIR` 用来确保命令在当前项目根目录运行
- 如果你更喜欢脚本入口，也可以改成 `uv run junment-context-agent`
- 最小可用方式是只传 `API key`；如果要换 provider 或模型，再显式覆盖 `base_url` / `model`
- 如果你已经在外层 shell 导出了环境变量，也可以继续全部用环境变量

### 在 Claude Code 里怎么使用

#### 配置文件放在哪里

- 把 hook 配置写到**目标项目**根目录的 `.claude/settings.json`
- 这里的“目标项目”是指：你平时在 Claude Code 里实际提问和编码的那个仓库
- `CLAUDE_PROJECT_DIR` 会指向这个目标项目根目录，因此命令里通常先 `cd "$CLAUDE_PROJECT_DIR"`

#### 方式 1：当前项目里就放着这个工具仓库

适合场景：

- 你正在开发或调试 `Junment`
- 或者你就是把这个工具直接放在当前 Claude Code 打开的仓库里使用

这种情况下，最直接的写法就是继续用 `uv run`：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && JUNMENT_LLM_API_KEY=\"$OPENROUTER_API_KEY\" uv run python -m context_agent.cli",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

如果你已经配置了脚本入口，也可以改成：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && JUNMENT_LLM_API_KEY=\"$OPENROUTER_API_KEY\" uv run junment-context-agent",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

#### 方式 2：工具仓库独立维护，通过 GitHub + `uvx` 临时运行

适合场景：

- 你不想在每个项目里都 checkout 一份 `Junment`
- 想直接从 GitHub 拉起最新版本试用

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && JUNMENT_LLM_API_KEY=\"$OPENROUTER_API_KEY\" uvx --from git+https://github.com/<your-user>/Junment.git junment-context-agent",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

#### 方式 3：先安装成 tool，再在 Claude Code 里直接调用

适合场景：

- 你长期使用这个工具
- 不希望每次 hook 都写很长的 `uvx --from ...`

先安装：

```bash
uv tool install git+https://github.com/<your-user>/Junment.git
```

然后在 `.claude/settings.json` 里直接写：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && JUNMENT_LLM_API_KEY=\"$OPENROUTER_API_KEY\" junment-context-agent",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

#### 怎么选

- 开发/调试 `Junment` 本身：优先 `uv run`
- 临时试用、希望直接走 GitHub：优先 `uvx --from git+https://...`
- 长期稳定使用：优先 `uv tool install` 后直接调用 `junment-context-agent`

## 输入约定

Claude Code 官方 `UserPromptSubmit` hook 输入里，常见字段包括：

- `session_id`
- `transcript_path`
- `cwd`
- `permission_mode`
- `hook_event_name`
- `prompt`

当前 CLI 会从 stdin 读取 JSON，并兼容以下字段别名：

- prompt：`prompt` / `userPrompt` / `input` / `text`
- cwd：`cwd` / `workspace`
- event：`hook_event_name` / `hookEventName` / `event`
- session：`session_id` / `sessionId`

另外需要注意：

- `--input` 参数接收的是 **JSON 文件路径**
- 不是把 JSON 字符串直接塞给 `--input`

## 输出约定

CLI 成功时会向 stdout 输出 JSON，核心格式如下：

```json
{
  "continue": true,
  "suppressOutput": false,
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "..."
  }
}
```

说明：

- `additionalContext` 会被 Claude Code 追加到当前轮上下文
- 当前实现不主动 block 用户 prompt
- 如果 gate 判断不需要上下文，会返回空的 `additionalContext`
- 如果 provider 或 model 配置不完整，也会直接返回空的 `additionalContext`

## 本地调试

### 直接向 CLI 发送最小 payload

```bash
printf '%s' '{"prompt":"请分析 python-mcp-agent-architecture.md 的设计","cwd":"/path/to/repo","hook_event_name":"UserPromptSubmit"}' \
  | uv run python -m context_agent.cli
```

### 使用脚本入口

```bash
printf '%s' '{"prompt":"请分析 README.md 的用途","cwd":"/path/to/repo"}' \
  | uv run junment-context-agent
```

### 使用文件输入

```bash
uv run python -m context_agent.cli --input sample-hook-input.json
```

### 使用环境变量调试真实 provider

```bash
export JUNMENT_LLM_API_KEY="<your-key>"

printf '%s' '{"prompt":"请解释 Planner.create_plan 的职责","cwd":"/path/to/repo","hook_event_name":"UserPromptSubmit"}' \
  | uv run python -m context_agent.cli

# 如果你要覆盖默认 provider / model，再额外传：
#   --llm-base-url ...
#   --llm-model ...
#   --gate-model ...
#   --judge-model ...
#   --summary-model ...
```

### 关于 `uv run` 和 PyPI

- `uv run python -m context_agent.cli` 会直接运行当前仓库里的模块
- `uv run junment-context-agent` 会直接使用当前仓库 `pyproject.toml` 里的脚本入口
- 这两种本地运行方式都**不需要先发布到 PyPI**
- 只有你要把这个工具发布给别人安装时，才需要考虑打包和发布

### 通过 GitHub + `uv` 使用

如果这个仓库已经发布到 GitHub，即使没有发布到 PyPI，也可以直接通过 Git URL 使用。

临时运行：

```bash
uvx --from git+https://github.com/<your-user>/Junment.git junment-context-agent --help
```

安装为本地工具：

```bash
uv tool install git+https://github.com/<your-user>/Junment.git
```

作为其他项目依赖：

```bash
uv add git+https://github.com/<your-user>/Junment.git
```

当前 `basedpyright` 已经是正式运行时依赖，因此通过 GitHub + `uvx` / `uv tool install` 安装后，Python 的 `LSP symbol` discovery 所需 `basedpyright-langserver` 会随对应的 `uv` 工具环境一起可用，不需要用户预先全局安装。TS/JS 则会在本机已安装 `typescript-language-server`，且环境中可用 `typescript`（通常来自项目本地依赖或全局安装）时自动启用；未满足时会静默降级，不影响整体流程。

### 查看 Claude Code hook 调试日志

```bash
claude --debug
```

## 接入注意事项

- hook 的 `stdout` 必须保持为纯净 JSON
- `stderr` 最好保持安静，避免把无关日志带进调试输出
- 如果 shell profile 里有无条件 `echo`，可能会污染 hook JSON
- 不建议重复注入 `CLAUDE.md` 或 `.claude/rules` 已经提供的上下文
- 当前 CLI 已显式清理 `mcp-agent` 的日志后台任务，避免输出 JSON 后进程挂住

## 当前推荐用法

推荐把这个项目作为 Claude Code 的前置上下文编排器使用：

1. Claude Code 触发 `UserPromptSubmit`
2. hook 调用 `context_agent.cli`
3. gate 判断当前问题是否需要上下文
4. 本地 deterministic discovery 收集候选
5. 并行 LLM rerank 逐候选评分
6. summarize 压缩 top k
7. 返回 `additionalContext`
8. Claude 在带上下文的前提下继续回答

## 当前已知边界

- `planner` 目前仍是本地轻量提取，不是远端 LLM planner
- 真实 provider 的端到端效果依赖所选模型质量与稳定性
- 当前默认目标是“给 Claude Code 补充更高价值的上下文”，而不是替代 Claude Code 自身的仓库理解能力