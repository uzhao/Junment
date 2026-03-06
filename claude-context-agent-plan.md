## Claude Code 上下文增强方案（MVP 计划）

### 1. 目标

目标是在 Claude Code 中通过 `UserPromptSubmit` hook，在 prompt 真正发送给 Claude 前，自动注入与当前问题高度相关的代码、文档和结构化说明，尽量接近 Augment 的“上下文构造”体验。

这个方案的重点不是传统 RAG，也不是 embedding + 向量库，而是：

- 由本地小模型理解原始 prompt
- 由本地 agent 主导搜索计划
- 借助 LSP / grep / 文件读取发现候选
- 对候选文件逐个独立评分
- 只把高价值内容整理成最终 context pack 注入 Claude

### 2. MVP 设计原则

#### 2.1 做什么

- 只以 `UserPromptSubmit` 作为主入口
- hook 只负责调用本地 `context-agent`
- 本地小模型负责问题理解、搜索规划、候选评分
- LSP / grep / 文件读取只作为工具层
- 重点处理 `README` / docs / 代码文件
- 最终产出结构化 `additionalContext`

#### 2.2 不做什么

- 不依赖 embedding / 向量数据库
- 不做全仓逐文件通读
- 不把 `PreToolUse` 作为第一版主线
- 不重复注入 `CLAUDE.md` / `.claude/rules`
- 不一开始做复杂会话记忆或图谱系统

### 3. 总体架构

```text
Claude Code UserPromptSubmit
  -> hook command
  -> local context-agent
      -> local LLM 读取原始 prompt
      -> 生成搜索计划
      -> 调用 LSP / grep / 文件读取 / docs 读取
      -> 形成候选文件列表
      -> 对候选逐个独立评分
      -> 提取高分文件的关键块与文档段落
      -> 生成 context pack
  -> hook 返回 additionalContext
  -> Claude 正式处理用户原始 prompt
```

### 4. 模块职责

#### 4.1 Hook 层

职责很薄，只做以下事情：

- 接收 Claude Code 的 `UserPromptSubmit` 输入
- 收集当前工作目录、用户原始 prompt、可用元信息
- 调用本地 `context-agent`
- 将 agent 输出写入 `additionalContext`

Hook 层不直接承担检索逻辑，不直接写死 regexp 规则，也不负责复杂决策。

#### 4.2 Context-Agent 层

这是整个系统的核心。

输入：

- 原始 prompt
- 当前工作目录
- 可选的会话元信息

输出：

- 任务分类
- 搜索轨迹摘要
- 高相关文件与文档段落
- 最终 context pack

#### 4.3 工具层

可调用工具包括：

- LSP：workspace symbols / definition / references
- grep：关键词、路径、错误栈、符号名辅助搜索
- 文件读取：代码与文档正文
- README / docs 读取：补充项目语义背景
- 可选：git diff / git log（后续再加）

### 5. 检索与评分流程

#### 5.1 第一步：问题理解

本地小模型读取完整原始 prompt，先输出一个较轻量的搜索计划，例如：

- 当前任务类型：debug / explain / modify / implement / refactor
- 高概率相关模块
- 可能相关的 symbol / 文件路径 / 目录
- 是否优先查 README / docs
- 是否存在错误栈、日志、路径、行号等强线索

这一阶段的目标不是一次命中，而是给出“下一步往哪里找”。

#### 5.2 第二步：候选发现

根据搜索计划调用工具，形成候选集合：

- 如果 prompt 中有路径、行号、错误栈，直接高优先级处理
- 如果有可能的 symbol，用 LSP workspace symbols / definition / references
- 如果线索较弱，用 grep 搜路径名、关键词、错误文本
- 同时按需纳入 README、设计文档、RFC、模块说明

输出是一批候选文件或候选块，而不是直接拼上下文。

#### 5.3 第三步：逐候选独立评分

这是 MVP 的关键步骤。

对于每个候选文件，开启一个新的、独立的小上下文，让本地模型判断：

- 与当前问题是否相关
- 相关性分数（0-100）
- 关联类型
- 主要相关原因
- 建议抽取的代码范围或文档段落
- 是否需要扩展到相邻文件 / 引用 / 测试

建议关联类型至少包括：

- error origin
- core implementation
- interface / entrypoint
- config / rule
- test
- documentation
- weakly related

这样做的优点：

- 单次上下文小，适合本地模型
- 文件之间互不污染
- 结果天然可排序
- 后续容易并行化

#### 5.4 第四步：高分候选扩展

只对高分候选做有限扩展，例如：

- 文件内更精确的 symbol / span
- 邻近测试文件
- 直接引用链
- 同目录 README 段落

不要对所有候选都扩展，避免搜索树失控。

#### 5.5 第五步：生成最终 context pack

最终注入给 Claude 的内容应该是结构化材料，而不是简单拼接原文。

建议至少包含：

- 当前任务类型
- 高相关文件列表
- 每个文件为何相关
- 推荐关注的代码块 / 文档段落
- 相关 README / docs 摘要
- 当前仍不确定的点

### 6. 文档处理策略

#### 6.1 `CLAUDE.md` / `.claude/rules`

这类内容通常已经会被 Claude Code 纳入上下文，因此：

- 本地 agent 可以读取它们辅助决策
- 但原则上不要重复注入给 Claude

#### 6.2 `README` / docs / RFC

这类内容是重点：

- Claude 不一定自然吃到相关段落
- 即使读到，也未必能准确定位有用部分

因此应由本地 agent：

- 找到相关文档
- 提取相关段落
- 压缩成任务相关摘要
- 再注入 Claude

### 7. MVP 边界

第一版只做：

- `UserPromptSubmit`
- 本地 `context-agent`
- prompt 理解
- 候选发现
- 逐候选评分
- 高分内容整理
- `additionalContext` 注入

第一版明确不做：

- `PreToolUse` 纠偏
- `PostToolUse` 动态补充
- 向量库
- 全仓扫描
- 复杂多轮会话记忆
- 自动改写 Claude 工具输入

### 8. 后续扩展方向

等 MVP 稳定后，再考虑：

- `PostToolUse` / `PostToolUseFailure` 结果补充
- 当前 diff / 最近改动优先级
- 会话内工作记忆
- 更细粒度的函数 / 方法级评分
- 缓存项目画像与模块摘要

### 9. 推荐落地顺序

#### 阶段一：跑通闭环

- hook 能调用本地 agent
- agent 能读取 prompt
- agent 能调用基础搜索工具
- agent 能输出可注入的 context pack

#### 阶段二：提升质量

- 引入 LSP 搜索计划
- 引入逐文件独立评分
- 引入 README / docs 摘要整理

#### 阶段三：增强动态性

- 视效果再增加 `PostToolUse`
- 再考虑记忆、缓存和 diff 感知

### 10. 一句话定义

这个系统可以定义为：

> 一个挂在 Claude Code `UserPromptSubmit` 前的本地上下文增强 agent。

它不是传统向量检索系统，而是“本地小模型负责理解与规划，确定性工具负责搜索与验证，最终只把高价值上下文整理后注入 Claude”的工程化方案。