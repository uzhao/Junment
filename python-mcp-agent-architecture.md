## Python + mcp-agent 目录骨架设计（选项 A）

### 1. 设计判断

当前更合适的做法不是“完全不用 agent 框架，手工把文件内容程序化发给 LLM”，而是：

- 用 `mcp-agent` 作为运行时、工作流和模型调用骨架
- 用程序化的确定性流程控制候选发现与扩展
- 用专门的评分 agent 对候选文件逐个独立判断

这样可以避免两种极端：

- 过度手工：最后退化成一堆 prompt 拼接脚本
- 过度自治：让一个大 agent 在整个仓库里自由游走，结果不可控

因此这里的 `mcp-agent` 定位是：

> 作为上下文增强系统的编排框架，而不是让它替代我们的检索设计。

### 2. 本方案里怎么使用 mcp-agent

第一版即使不重度使用 MCP server，也仍然适合从 `mcp-agent` 开始，因为它至少提供：

- 统一的 app/runtime 入口
- agent 与 LLM 的组织方式
- 结构化 workflow 编排空间
- 后续接 tracing / memory / MCP 的升级路径

第一版里不强依赖的能力：

- 不要求先把所有工具都封装成 MCP server
- 不要求做多 agent 自由协作
- 不要求做持久化记忆

第一版里真正需要的能力：

- 用一个 planner 负责理解 prompt 和生成搜索计划
- 用程序化服务层执行 LSP / grep / 文件读取
- 用一个 judge 逐候选独立评分
- 用一个 summarizer 整理最终 context pack

### 3. 总体分层

建议分成五层：

1. **Hook 适配层**
2. **Workflow 编排层**
3. **Agent 层**
4. **确定性服务层**
5. **工具适配层**

职责边界如下：

- Hook 适配层：接 Claude Code 输入并输出 `additionalContext`
- Workflow 编排层：定义处理步骤和阶段顺序
- Agent 层：做 prompt 理解、候选评分、摘要整理
- 确定性服务层：执行候选发现、扩展、聚合
- 工具适配层：真正调用 LSP、grep、文件系统、文档读取

### 4. 推荐目录骨架

```text
context_agent/
  app.py
  cli.py
  config.py
  logging_config.py
  adapters/
    claude_hook.py
    openai_compatible.py
  workflows/
    build_context.py
  agents/
    planner.py
    judge.py
    summarizer.py
  services/
    candidate_discovery.py
    candidate_expansion.py
    score_selection.py
    context_pack_builder.py
  tools/
    lsp_client.py
    grep_search.py
    file_reader.py
    doc_locator.py
  prompts/
    planner.md
    judge.md
    summarizer.md
  schemas/
    hook_io.py
    search_plan.py
    candidate.py
    score.py
    context_pack.py
tests/
  test_search_plan.py
  test_score_selection.py
  test_context_pack_builder.py
```

### 5. 各模块职责

#### 5.1 `context_agent/app.py`

职责：

- 创建 `mcp-agent` 应用实例
- 统一装配配置、日志、模型提供器
- 为 workflow 和 agents 提供共享上下文

它应该是系统内部入口，不直接处理 Claude hook 原始输入。

#### 5.2 `context_agent/cli.py`

职责：

- 作为命令行入口
- 读取标准输入或文件输入
- 调用主 workflow
- 输出 Claude Code hook 需要的 JSON

这里要尽量薄，不要把业务逻辑堆进去。

#### 5.3 `context_agent/adapters/claude_hook.py`

职责：

- 解析 Claude Code `UserPromptSubmit` 输入
- 抽取原始 prompt、cwd、元信息
- 将内部 `ContextPack` 转成 hook 输出格式

这层只处理协议适配，不参与检索判断。

#### 5.4 `context_agent/adapters/openai_compatible.py`

职责：

- 统一封装 OpenAI-compatible 模型调用配置
- 支持 base URL、model、api key、超时等参数
- 给 planner / judge / summarizer 提供一致的调用入口

这样后续换本地兼容服务时，不会影响上层逻辑。

#### 5.5 `context_agent/workflows/build_context.py`

职责：

- 定义一轮上下文构造的主流程
- 串起 planner、候选发现、评分、筛选、摘要整理
- 控制阶段顺序和停止条件

这是系统最核心的编排文件。

#### 5.6 `context_agent/agents/planner.py`

职责：

- 读取完整原始 prompt
- 输出任务类型、搜索意图、候选方向
- 生成结构化 `SearchPlan`

它不直接读全仓文件，也不直接决定最终上下文。

#### 5.7 `context_agent/agents/judge.py`

职责：

- 对每个候选文件在独立上下文中评分
- 输出分数、关联类型、推荐代码范围、扩展建议

它必须保持“单候选隔离”，避免多个文件互相污染判断。

#### 5.8 `context_agent/agents/summarizer.py`

职责：

- 根据高分候选和文档段落生成最终摘要
- 构造结构化的 `ContextPack`
- 控制注入内容的密度和噪声

#### 5.9 `context_agent/services/candidate_discovery.py`

职责：

- 根据 `SearchPlan` 调用 LSP / grep / 文档工具
- 形成第一批候选文件或候选块
- 标记候选来源和命中原因

这层是确定性逻辑，不依赖 LLM 自由发挥。

#### 5.10 `context_agent/services/candidate_expansion.py`

职责：

- 仅对高分候选做有限扩展
- 查相邻 symbol、邻近测试、直接 references、README 段落
- 防止搜索树无限膨胀

#### 5.11 `context_agent/services/score_selection.py`

职责：

- 聚合 judge 的评分结果
- 做阈值过滤、Top-K、去重、排序
- 选出进入最终上下文的项目

#### 5.12 `context_agent/services/context_pack_builder.py`

职责：

- 将高分结果整理成统一输出结构
- 生成文件列表、原因说明、推荐范围、文档摘要
- 控制最终 token 预算

#### 5.13 `context_agent/tools/*`

职责：

- `lsp_client.py`：对接 workspace symbols / definition / references
- `grep_search.py`：关键词、路径、错误文本辅助搜索
- `file_reader.py`：读取代码文件与片段
- `doc_locator.py`：定位 README、docs、设计文档

第一版先做本地 Python 适配，不强制包装成 MCP server。

#### 5.14 `context_agent/prompts/*`

职责：

- 管理 planner / judge / summarizer 的提示词模板
- 让“检索逻辑”和“提示词内容”分离
- 便于后续单独调试评分 prompt

#### 5.15 `context_agent/schemas/*`

职责：

- 定义所有核心结构化对象
- 约束阶段间输入输出格式
- 降低 workflow 与 agents 之间的耦合

### 6. 核心数据对象

第一版建议先固定这几个 schema：

- `HookInput`
- `SearchPlan`
- `CandidateItem`
- `CandidateScore`
- `ContextPack`
- `HookOutput`

其中：

- `SearchPlan` 负责表达“往哪里找”
- `CandidateItem` 负责表达“找到了什么”
- `CandidateScore` 负责表达“这个候选值不值得保留”
- `ContextPack` 负责表达“最终注入 Claude 的内容”

### 7. 一轮请求的数据流

推荐的一轮处理流程如下：

1. `cli.py` 读取 Claude hook 输入
2. `claude_hook.py` 解析出 `HookInput`
3. `build_context.py` 调用 `planner.py` 生成 `SearchPlan`
4. `candidate_discovery.py` 调工具拿第一批候选
5. `judge.py` 对候选逐个独立评分
6. `score_selection.py` 选出高分候选
7. `candidate_expansion.py` 对高分项做有限扩展
8. `summarizer.py` 与 `context_pack_builder.py` 生成 `ContextPack`
9. `claude_hook.py` 转成 `HookOutput`
10. CLI 输出 JSON 给 Claude Code

### 8. 为什么这比“纯程序化发文件给 LLM”更合适

因为我们不是只要一个“把文件喂给模型”的脚本，而是要一个可增长的上下文构造系统。

用 `mcp-agent` 起步的好处是：

- 上层 agent 角色清晰
- workflow 边界清晰
- 以后要加 tracing、memory、MCP 接入时不用推倒重来

同时保留确定性服务层的好处是：

- 不把仓库搜索完全交给自由 agent
- LSP / grep / 文件读取依然可控、可测试
- 评分与发现可以独立调试

### 9. MVP 必做模块

第一批实现时，只需要先做这些：

- `app.py`
- `cli.py`
- `adapters/claude_hook.py`
- `workflows/build_context.py`
- `agents/planner.py`
- `agents/judge.py`
- `services/candidate_discovery.py`
- `services/score_selection.py`
- `services/context_pack_builder.py`
- `tools/grep_search.py`
- `tools/file_reader.py`
- `tools/doc_locator.py`
- `schemas/*`

`lsp_client.py` 可以第一批就接，也可以先留一个简化版本。

### 10. 当前不急着实现的预留模块

可以先占位但不急着做深：

- `candidate_expansion.py`
- `agents/summarizer.py`
- tracing
- session memory
- MCP server 化工具层

### 11. 下一步实现顺序

从 A 进入 B 时，建议按这个顺序落地：

1. 先把 schema 定义好
2. 再把 CLI 与 Claude hook 输入输出接好
3. 再实现 planner
4. 再实现候选发现
5. 再实现 judge 的逐候选评分
6. 最后实现 context pack 输出

这样能最快跑通一个最小闭环。