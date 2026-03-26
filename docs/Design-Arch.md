# AI Coding 团队知识与记忆系统设计文档（Architecture Design）

- 文档版本：`v1.0`
- 文档状态：`Design(Arch)`
- 编写日期：`2026-03-24`
- 关联文档：`docs/Proposal.md`
- 目标读者：`架构师 / 技术负责人 / 平台研发 / AI 工程师 / 客户端研发`

## 1. 设计目标

本设计文档用于定义面向 AI Coding 场景的团队知识与记忆系统的目标架构、模块边界、数据模型、关键流程、接口设计和实施路径。

核心目标包括：

- 为 AI 提供稳定、可治理、可持续演进的上下文供给能力。
- 支持运行时近场上下文、热知识、长期记忆和全局推理的分层协同。
- 支持高价值知识的自动沉淀、版本管理、权限隔离和失效治理。
- 通过统一的检索与注入服务，让不同客户端和 Agent 在同一治理框架下使用知识。
- 为后续评估、优化、多 Agent 协作和组织级扩展保留架构空间。

## 2. 设计原则

### 2.1 近场上下文优先

大多数 AI Coding 问题首先依赖当前任务和当前代码局部上下文，因此系统必须优先保障：

- 当前文件与相邻模块理解。
- 当前任务与分支关联。
- 最近 diff、命令输出、测试结果和错误日志摘要。
- 仓库级、路径级、任务级指令。

### 2.2 分层记忆而非统一知识池

系统应将上下文分为运行时上下文、热知识、长期记忆和全局推理索引，避免所有问题都走同一条检索链路。

### 2.3 混合检索与动态路由

检索过程应是“过滤 → 召回 → 重排 → 压缩 → 注入”的流水线，并根据问题类型动态选择路径。

### 2.4 来源可追溯

任何知识条目、检索结果和注入内容都必须保留来源引用，支撑审计、失效、回滚和质量评估。

### 2.5 低侵入与可扩展

采集与检索必须尽量减少对开发者工作流和 IDE 性能的干扰，架构上支持后续平滑扩展。

## 3. 总体架构

系统整体采用分层架构，逻辑上由以下部分组成：

1. `Client & Agent Access Layer`
2. `Context Collection Layer`
3. `Signal & Extraction Layer`
4. `Knowledge Governance Layer`
5. `Storage & Index Layer`
6. `Retrieval & Injection Layer`
7. `Config / Policy / Security Layer`
8. `Observability & Evaluation Layer`

### 3.1 架构文字图

```text
IDE / CLI / Agent / MCP Client
            |
            v
   Access Gateway / MCP Server
            |
            +--------------------------+
            |                          |
            v                          v
 Runtime Context Service       Retrieval Orchestrator
            |                          |
            v                          v
 Context Collector            Query Router / Reranker
            |                          |
            v                          v
 Signal Detector              Knowledge Index Services
            |                          |
            v                          v
 Extraction Orchestrator --> Governance Pipeline
                                      |
                                      v
                  Relational DB / Vector Index / Search Index / Object Store
                                      |
                                      v
                      Metrics / Trace / Audit / Feedback / Eval
```

## 4. 核心分层设计

## 4.1 Runtime Context Layer

运行时上下文层面向当前任务和当前会话，主要服务于短时间窗口内的高频请求。

### 4.1.1 数据组成

- 当前仓库、分支、工作区。
- 当前编辑文件与符号。
- 最近修改文件及 diff 摘要。
- 当前任务单、PR、Issue 摘要。
- 终端命令结果与测试失败摘要。
- 仓库级与路径级指令。
- 当前会话工作集（working set）。

### 4.1.2 设计要求

- 毫秒级或亚秒级获取。
- 优先本地或近端缓存。
- 支持按文件、路径、模块增量更新。
- 支持长度压缩与摘要化。

### 4.1.3 典型用途

- 局部代码解释。
- 关联文件补全。
- 代码修改建议。
- 基于测试错误的修复建议。

## 4.2 Hot Memory Layer

热记忆层存放当前活跃项目中高频使用、更新较快、适合作为稳定前缀上下文的知识。

### 4.2.1 数据组成

- 当前迭代需求背景。
- 项目规则与禁忌项。
- 高频模块约束。
- 本阶段特殊业务规则。
- 团队常用工作流与 checklists。

### 4.2.2 设计要求

- 支持按团队 / 项目 / 仓库维度缓存。
- 支持 prompt cache 或服务端上下文缓存。
- 支持快速失效与重建。

### 4.2.3 适用策略

- 热知识条目数量相对较少，优先直接注入长上下文。
- 适合与项目级系统提示词合并。

## 4.3 Long-term Memory Layer

长期记忆层用于沉淀结构化、可复用、可治理的组织知识。

### 4.3.1 记忆类型

#### `Semantic Memory`

表示稳定事实与规则，例如：

- 业务术语定义。
- 字段语义。
- 接口契约。
- 服务边界。
- 编码约束。

#### `Episodic Memory`

表示具体案例与任务经验，例如：

- 某次故障排查过程。
- 某次迁移改造的关键步骤。
- 某次修复成功的补丁模式。
- 某次回归遗漏和补救方法。

#### `Procedural Memory`

表示流程与方法，例如：

- 发版流程。
- 故障处理 SOP。
- 评审检查清单。
- 新模块接入流程。

### 4.3.2 设计要求

- 结构化存储。
- 支持审核、版本、有效期和降权。
- 支持与源码、PR、Issue、服务版本关联。

## 4.4 Global Reasoning Layer

全局推理层不是默认路径，仅用于复杂跨域问题，例如：

- 多仓接口关系与影响范围分析。
- 跨团队知识关联。
- 决策演进链路分析。
- 全局主题型问答。

### 4.4.1 设计建议

- 第一阶段不做重型全量图谱。
- 优先使用轻量图关系或 `LazyGraphRAG` 思路。
- 仅在需要全局关系推理时启用。

## 5. 模块设计

## 5.1 接入层

### 5.1.1 组成

- IDE 插件接入。
- CLI / Agent 接入。
- `MCP Server`。
- 平台内部 API Gateway。

### 5.1.2 职责

- 统一身份与租户识别。
- 接收上下文采集请求。
- 接收检索请求。
- 对外输出可注入上下文包。

## 5.2 上下文采集模块

### 5.2.1 采集对象

- 用户 prompt。
- 模型回复。
- 工具调用轨迹。
- 文件读写摘要。
- 代码 diff。
- 命令执行结果。
- 测试输出。
- 任务元数据。
- 仓库结构信息。

### 5.2.2 采集原则

- 只采关键事件，不做原始噪声全量存储。
- 允许异步上报。
- 对大体积内容做本地摘要后上报。
- 对敏感内容做本地脱敏或服务端脱敏。

## 5.3 信号识别模块

### 5.3.1 目标

从采集到的会话和开发活动中识别值得沉淀的候选知识。

### 5.3.2 典型信号

- 修复成功并通过验证。
- 需求背景被反复提及。
- 形成稳定规则或明确禁忌。
- 产出复用性强的脚手架或模板。
- 出现重复问题并给出通用解法。
- 形成可执行 SOP 或回归清单。

### 5.3.3 输出字段

- `signal_type`
- `confidence`
- `priority`
- `source_session_id`
- `source_refs`

## 5.4 提取编排模块

### 5.4.1 职责

- 处理待抽取候选。
- 调用 LLM 进行结构化抽取。
- 执行幂等控制、重试与队列调度。

### 5.4.2 提取粒度

建议从“会话总结”升级为“原子知识单元”抽取：

- `claim`
- `decision`
- `constraint`
- `workflow`
- `failure_mode`
- `fix_pattern`
- `verification_result`

### 5.4.3 提取模板

每个知识单元建议至少包含：

- 标题
- 类型
- 背景
- 结论或规则
- 适用范围
- 来源依据
- 置信度
- 失效条件
- 标签

## 5.5 治理模块

### 5.5.1 职责

- 去重与合并。
- 版本化。
- 质量评分。
- 人工审核。
- 发布、下线、失效和降权。

### 5.5.2 治理规则

- 高风险规则必须审核。
- 同一来源近似内容自动聚合。
- 已失效或被推翻的知识自动降权。
- 低采纳率、低相关性条目逐步淘汰。

## 5.6 检索编排模块

### 5.6.1 输入

- 用户任务描述。
- 当前仓库、分支、路径、模块。
- 当前 diff。
- 当前会话工作集。
- 用户身份与权限范围。

### 5.6.2 核心流程

1. 请求分类。
2. 作用域过滤。
3. 路由决策。
4. 多路召回。
5. 重排。
6. 摘要压缩。
7. 生成上下文包。
8. 返回来源引用。

### 5.6.3 路由建议

- `局部代码问题`：Runtime Context + repo search。
- `项目规则问题`：Hot Memory + Semantic Memory。
- `历史经验问题`：Episodic Memory。
- `流程操作问题`：Procedural Memory。
- `跨仓影响分析`：Global Reasoning Layer。

## 5.7 配置与策略中心

### 5.7.1 配置内容

- 系统提示词模板。
- 团队 / 项目 / 仓库 / 路径级指令。
- 检索策略。
- 信号阈值。
- 抽取模板版本。
- 审核策略。
- 失效策略。

### 5.7.2 配置下发方式

- 启动时拉取。
- 定期同步。
- 关键配置灰度发布。
- 版本回滚。

## 5.8 评估与观测模块

### 5.8.1 指标维度

- 检索相关性。
- Groundedness。
- 采纳率。
- 提升效果。
- 知识老化率。
- 错误召回率。
- 上下文成本。

### 5.8.2 数据来源

- 检索日志。
- 用户反馈。
- 代码结果是否被保留。
- PR 合并情况。
- 回滚与返工情况。
- 人工评估集。

## 6. 关键流程设计

## 6.1 会话采集流程

```text
客户端事件发生
  -> 本地轻量清洗/脱敏
  -> 上报事件网关
  -> 写入事件流
  -> 按 session 聚合
  -> 进入信号识别
```

### 6.1.1 关键要求

- 非阻塞。
- 可批量上报。
- 支持断点续传。
- 具备采样与限流能力。

## 6.2 知识抽取流程

```text
候选会话/事件
  -> 信号评分
  -> 入抽取队列
  -> LLM 结构化提取
  -> 原子知识单元生成
  -> 去重与质量评分
  -> 审核/自动发布
  -> 建索引
```

### 6.2.1 去重策略

- 标题近似。
- 来源重叠。
- 语义近似。
- 作用域一致。
- 时间接近。

## 6.3 检索与注入流程

```text
任务请求
  -> 请求分类
  -> 权限校验
  -> 作用域过滤
  -> 路由至对应索引层
  -> 混合召回
  -> Rerank
  -> 摘要压缩
  -> 生成 Context Pack
  -> 注入 Agent
```

### 6.3.1 输出内容

- 最终上下文摘要。
- 规则列表。
- 相关案例。
- 来源清单。
- 置信度与推荐用途。

## 6.4 反馈闭环流程

```text
AI 使用知识
  -> 用户采纳/忽略/修改
  -> 写入反馈日志
  -> 更新知识评分
  -> 影响 rerank / 发布状态 / 失效权重
```

## 7. 数据模型设计

## 7.1 会话与事件模型

### `conversation_session`

- `session_id`
- `tenant_id`
- `team_id`
- `user_id`
- `repo_id`
- `branch_name`
- `task_id`
- `client_type`
- `started_at`
- `ended_at`
- `status`

### `session_event`

- `event_id`
- `session_id`
- `event_type`
- `event_subtype`
- `content_ref`
- `summary`
- `tool_name`
- `file_paths`
- `symbol_names`
- `timestamp`

## 7.2 信号与候选模型

### `knowledge_signal`

- `signal_id`
- `session_id`
- `signal_type`
- `confidence`
- `priority`
- `status`
- `source_refs`
- `created_at`

### `knowledge_candidate`

- `candidate_id`
- `signal_id`
- `candidate_type`
- `summary`
- `scope_hint`
- `quality_score`
- `extract_prompt_version`
- `status`

## 7.3 知识模型

### `knowledge_item`

- `knowledge_id`
- `title`
- `knowledge_type`
- `memory_type`
- `content`
- `scope_type`
- `scope_id`
- `status`
- `quality_score`
- `confidence_score`
- `freshness_score`
- `version`
- `effective_from`
- `effective_to`
- `created_by`
- `created_at`
- `updated_at`

### `knowledge_source_ref`

- `ref_id`
- `knowledge_id`
- `ref_type`
- `ref_target_id`
- `ref_path`
- `ref_commit`
- `ref_pr`
- `ref_issue`
- `excerpt_summary`

### `knowledge_relation`

- `relation_id`
- `knowledge_id`
- `related_knowledge_id`
- `relation_type`
- `weight`

### `knowledge_tag`

- `knowledge_id`
- `tag_key`
- `tag_value`

## 7.4 检索与反馈模型

### `retrieval_request`

- `request_id`
- `session_id`
- `query_text`
- `query_type`
- `repo_id`
- `branch_name`
- `file_paths`
- `requested_at`

### `retrieval_result`

- `request_id`
- `knowledge_id`
- `recall_channel`
- `recall_score`
- `rerank_score`
- `selected`
- `selected_rank`

### `knowledge_feedback`

- `feedback_id`
- `knowledge_id`
- `request_id`
- `feedback_type`
- `feedback_score`
- `feedback_text`
- `created_by`
- `created_at`

## 7.5 配置模型

### `config_profile`

- `profile_id`
- `scope_type`
- `scope_id`
- `profile_type`
- `content`
- `version`
- `status`
- `updated_at`

## 8. 索引与存储设计

## 8.1 存储分层

### 8.1.1 关系型数据库

存储：

- 元数据。
- 关系。
- 权限信息。
- 审核与反馈记录。
- 配置。

建议：`PostgreSQL`

### 8.1.2 向量索引

存储：

- 知识内容 embedding。
- 案例摘要 embedding。
- 上下文化 chunk embedding。

建议：`pgvector`、`Milvus` 或 `OpenSearch Vector`

当前实现说明：

- PostgreSQL 路径已落地 `pgvector` 原生 `vector` 列。
- 检索排序使用数据库侧 cosine distance 与 HNSW 索引。
- SQLite / 非 PostgreSQL 环境保留 JSON 向量回退路径，便于本地 demo 与单测。

### 8.1.3 搜索索引

存储：

- 标题、标签、术语、错误码、路径、模块名、规则关键字。

建议：`OpenSearch / Elasticsearch`

### 8.1.4 对象存储

存储：

- 原始长文本。
- 工具调用快照。
- 提取中间产物。
- 审核附件。

## 8.2 Chunk 策略

### 8.2.1 原则

- 代码、文档、案例采用不同 chunk 策略。
- 对 chunk 补全文档级、模块级和任务级上下文。
- 保留路径、标题、版本、作用域等元数据。

### 8.2.2 Contextual Chunk

每个 chunk 在索引前补充以下上下文：

- 来源文档标题。
- 所属仓库与模块。
- 所属任务或主题。
- 适用范围。
- 时间与版本信息。

## 9. 检索策略设计

## 9.1 检索分类

### 9.1.1 Local Code Retrieval

适用于：

- 当前文件解释。
- 相邻代码补全。
- 局部 bug 修复。

数据源：

- runtime context
- repo symbols
- file index
- recent diff

### 9.1.2 Rule Retrieval

适用于：

- 编码规范。
- API 使用规范。
- 业务限制。

数据源：

- hot memory
- semantic memory
- config profile

### 9.1.3 Case Retrieval

适用于：

- 相似故障。
- 历史修复方案。
- 改造经验。

数据源：

- episodic memory
- PR / issue / incident ref

### 9.1.4 Procedure Retrieval

适用于：

- 测试流程。
- 发布流程。
- 接入流程。

数据源：

- procedural memory
- checklist library

### 9.1.5 Global Reasoning Retrieval

适用于：

- 跨系统关系。
- 全局影响评估。
- 主题型问答。

数据源：

- graph / global relation index

## 9.2 召回策略

建议采用多路召回：

- `BM25`
- `Dense Retrieval`
- `Metadata Filter`
- `Relationship Expansion`
- `Path / Symbol Boost`

## 9.3 重排策略

重排时考虑以下因素：

- 查询意图相关性。
- 作用域匹配程度。
- 来源可信度。
- 知识质量分。
- 知识新鲜度。
- 历史采纳率。
- 路径/模块匹配度。

## 9.4 注入策略

### 9.4.1 注入位置

- 系统提示词区。
- 任务上下文区。
- few-shot 示例区。
- 执行前提醒区。

### 9.4.2 Token 预算

- 热规则优先。
- 案例摘要其次。
- 超长结果先压缩再注入。
- 默认限制每类知识注入数量。

## 10. 权限与安全设计

## 10.1 权限模型

按以下维度进行权限控制：

- `tenant`
- `team`
- `project`
- `repo`
- `path`
- `role`

## 10.2 安全要求

- 默认最小权限。
- 检索前强制作用域校验。
- 敏感数据脱敏。
- 检索和注入全量审计。
- 对敏感知识支持“可索引不可直接展示”。
- 当前实现已提供 `tenant/team` 请求级隔离、知识/配置资源 ACL，以及基于 JWKS 的外部 IAM Bearer JWT 同步。

## 10.3 风险控制

- 知识污染检测。
- Prompt Injection 防护。
- 恶意会话沉淀拦截。
- 反馈异常检测。

## 11. 失效与版本设计

## 11.1 失效触发条件

- 相关文件发生重大变更。
- 相关接口签名变化。
- 相关规则被 PR / 文档明确推翻。
- 超过有效期。
- 负反馈持续累积。

## 11.2 失效策略

- 自动降权。
- 标记为待复核。
- 自动归档。
- 停止检索注入。

## 11.3 版本关联

知识与以下对象建立版本关联：

- 仓库版本。
- commit 区间。
- 服务版本。
- 配置版本。
- 规则版本。

## 12. 接口设计

## 12.1 事件采集接口

### `POST /api/v1/context/events`

用途：上报会话事件与上下文摘要。

请求字段：

- `session_id`
- `event_type`
- `summary`
- `content_ref`
- `repo_id`
- `branch_name`
- `file_paths`
- `timestamp`

## 12.2 检索接口

### `POST /api/v1/retrieval/query`

用途：根据任务上下文返回可注入 context pack。

请求字段：

- `session_id`
- `query`
- `query_type`
- `repo_id`
- `branch_name`
- `file_paths`
- `task_context`
- `token_budget`

返回字段：

- `context_summary`
- `rules`
- `cases`
- `procedures`
- `sources`

## 12.3 抽取接口

### `POST /api/v1/knowledge/extract`

用途：异步创建抽取任务。

## 12.4 审核接口

### `POST /api/v1/knowledge/review`

用途：审核知识候选。

## 12.5 配置接口

### `GET /api/v1/config/profile`

用途：拉取团队/项目/仓库配置。

## 12.6 反馈接口

### `POST /api/v1/feedback/knowledge`

用途：上报知识采纳、忽略、修正反馈。

## 13. 可观测性设计

## 13.1 指标

- 检索请求量。
- 各链路时延。
- 召回命中率。
- Rerank 提升幅度。
- 知识采纳率。
- 负反馈率。
- 过期知识命中率。
- 上下文 token 成本。

## 13.2 Trace

建议对以下链路做 trace：

- 会话事件采集。
- 信号识别。
- 抽取任务。
- 检索路由。
- 多路召回。
- 重排。
- 注入结果。
- 用户反馈。

## 13.3 审计

审计至少覆盖：

- 谁在什么场景下检索了哪些知识。
- 哪些知识被注入了上下文。
- 注入结果来源于哪些原始对象。
- 是否触达敏感范围。

## 14. 非功能设计

## 14.1 性能目标

- 检索服务 `P95 < 1.5s`
- 热配置拉取 `P95 < 300ms`
- 会话事件上报低感知延迟
- 抽取链路允许最终一致，建议 `10` 分钟内完成

## 14.2 可用性目标

- 检索服务 `99.9%`
- 采集服务 `99.9%`
- 配置中心 `99.95%`

## 14.3 扩展性目标

- 支持新增知识源。
- 支持新增索引后端。
- 支持多客户端接入。
- 支持多模型策略切换。

## 15. 部署建议

## 15.1 服务拆分建议

建议至少拆为以下服务：

- `gateway / mcp service`
- `context ingest service`
- `signal service`
- `extraction worker`
- `governance service`
- `retrieval service`
- `config service`
- `eval & observability service`

## 15.2 中间件建议

- 消息队列：`Kafka` / `RabbitMQ`
- 缓存：`Redis`
- 关系库：`PostgreSQL`
- 搜索：`OpenSearch`
- 向量：`pgvector` / `Milvus`
- 对象存储：兼容 `S3`

## 16. MVP 设计

## 16.1 MVP 范围

原始 MVP 只解决单团队、单项目、单仓库的高价值问题；当前实现已在此基础上扩展到多租户/多团队请求隔离与权限治理：

- 仓库级/路径级指令下发。
- Runtime Context 组装。
- Hybrid Retrieval + Metadata Filter + Rerank。
- 基础知识抽取与审核发布。
- 基础反馈收集。
- `tenant/team` 请求级隔离与资源 ACL。
- 外部 IAM Bearer JWT 与组织/团队作用域同步。

## 16.2 MVP 不做内容

- 组织级多仓图谱。
- 自动复杂失效推理。
- 高级评估平台。
- 全自动知识发布闭环。
- 跨系统 SCIM / 目录服务自动回写。

## 16.3 MVP 成功标准

- 至少在一个核心仓库明显降低重复上下文输入。
- Top5 检索相关性达到可用水平。
- 关键团队规则可稳定召回。
- 至少一类历史修复案例可被重复利用。

## 17. 演进路线

## 17.1 Phase 1

- 完成采集、检索、配置、权限基本闭环。
- 打通 IDE / CLI / Agent 一条接入链路。

## 17.2 Phase 2

- 引入 `Semantic / Episodic / Procedural` 三类记忆。
- 完成审核、质量评分和基本失效。

## 17.3 Phase 3

- 引入 Prompt Cache 和短期上下文压缩。
- 完善反馈学习和自动降权。

## 17.4 Phase 4

- 引入全局关系索引与跨仓影响分析。
- 增强评估与可归因能力。

## 18. 关键开放问题

在进入详细实现前，建议进一步明确以下问题：

- 客户端采集边界如何定义，哪些内容不上报。
- 原子知识单元的 schema 是否需要按场景拆分。
- 审核流由谁承担，哪些知识类型允许自动发布。
- 负反馈和代码结果之间如何建立因果归因。
- 短期上下文压缩由客户端完成还是服务端完成。
- Prompt Cache 的粒度按团队、项目还是仓库管理。

## 19. 结论

该架构的核心不是“再造一个 RAG 系统”，而是构建一套面向 AI Coding 的上下文与记忆基础设施。

其关键成功点在于：

- 先把近场上下文做好。
- 用分层记忆承接长期复用。
- 用动态路由避免过度依赖单一检索机制。
- 用来源追踪、版本和评估保证知识质量。

如果按本设计逐步推进，系统将具备从单仓效率工具演进为组织级 AI 研发底座的潜力。

