# AI Coding 团队知识与记忆系统数据库设计文档

- 文档版本：`v1.0`
- 文档状态：`Draft`
- 编写日期：`2026-03-24`
- 关联文档：`docs/Design-Arch.md`、`docs/API-Spec.md`

## 1. 设计目标

数据库设计用于支撑以下核心能力：

- 会话与事件采集
- 知识候选与抽取任务管理
- 知识对象的结构化存储
- 检索、审核、反馈、审计与配置管理

本设计以关系型数据库为主，配合向量索引、搜索索引和对象存储形成完整存储体系。

## 2. 存储分工

### 2.1 `PostgreSQL`

负责：

- 主业务表
- 元数据表
- 关系表
- 权限与作用域表
- 配置与审计表

### 2.2 `Vector Store`

负责：

- 知识 embedding
- chunk embedding
- 案例摘要 embedding

### 2.3 `Search Index`

负责：

- 标题检索
- 关键字检索
- 标签检索
- 路径与错误码检索

### 2.4 `Object Storage`

负责：

- 大文本原文
- 工具调用快照
- 抽取中间结果

## 3. 逻辑实体

核心实体包括：

- 租户与作用域
- 会话与事件
- 信号与候选
- 知识与来源
- 检索与反馈
- 审核与配置
- 审计与任务

## 4. 表结构设计

## 4.1 作用域基础表

### `tenant`

| 字段 | 类型 | 说明 |
|---|---|---|
| `tenant_id` | varchar(64) PK | 租户 ID |
| `tenant_name` | varchar(128) | 租户名称 |
| `status` | varchar(16) | 状态 |
| `created_at` | timestamptz | 创建时间 |

### `scope_binding`

| 字段 | 类型 | 说明 |
|---|---|---|
| `binding_id` | bigserial PK | 主键 |
| `tenant_id` | varchar(64) | 租户 ID |
| `scope_type` | varchar(32) | team/project/repo/path |
| `scope_id` | varchar(128) | 作用域 ID |
| `parent_scope_type` | varchar(32) | 父作用域类型 |
| `parent_scope_id` | varchar(128) | 父作用域 ID |
| `created_at` | timestamptz | 创建时间 |

索引建议：

- `idx_scope_binding_scope(scope_type, scope_id)`

## 4.2 会话与事件表

### `conversation_session`

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | varchar(64) PK | 会话 ID |
| `tenant_id` | varchar(64) | 租户 ID |
| `team_id` | varchar(64) | 团队 ID |
| `user_id` | varchar(64) | 用户 ID |
| `repo_id` | varchar(128) | 仓库 ID |
| `branch_name` | varchar(256) | 分支名 |
| `task_id` | varchar(128) | 任务 ID |
| `client_type` | varchar(32) | ide/cli/agent |
| `status` | varchar(16) | active/closed |
| `started_at` | timestamptz | 开始时间 |
| `ended_at` | timestamptz | 结束时间 |

索引建议：

- `idx_session_repo(repo_id, started_at desc)`
- `idx_session_user(user_id, started_at desc)`
- `idx_session_task(task_id)`

### `session_event`

| 字段 | 类型 | 说明 |
|---|---|---|
| `event_id` | bigserial PK | 事件 ID |
| `session_id` | varchar(64) | 会话 ID |
| `event_type` | varchar(32) | prompt/tool_call/test_result 等 |
| `event_subtype` | varchar(64) | 子类型 |
| `summary` | text | 摘要 |
| `content_ref` | varchar(256) | 原文引用地址 |
| `tool_name` | varchar(64) | 工具名 |
| `file_paths` | jsonb | 文件路径数组 |
| `symbol_names` | jsonb | 符号数组 |
| `event_time` | timestamptz | 事件时间 |
| `created_at` | timestamptz | 写入时间 |

索引建议：

- `idx_event_session(session_id, event_time)`
- `idx_event_type(event_type, event_time desc)`
- `gin_event_files(file_paths)`

## 4.3 信号与候选表

### `knowledge_signal`

| 字段 | 类型 | 说明 |
|---|---|---|
| `signal_id` | varchar(64) PK | 信号 ID |
| `session_id` | varchar(64) | 来源会话 |
| `signal_type` | varchar(32) | rule/case/procedure/fix_pattern |
| `confidence` | numeric(5,4) | 置信度 |
| `priority` | int | 优先级 |
| `status` | varchar(16) | pending/processed/rejected |
| `source_refs` | jsonb | 来源引用 |
| `created_at` | timestamptz | 创建时间 |

### `knowledge_candidate`

| 字段 | 类型 | 说明 |
|---|---|---|
| `candidate_id` | varchar(64) PK | 候选 ID |
| `signal_id` | varchar(64) | 信号 ID |
| `candidate_type` | varchar(32) | rule/case/procedure |
| `summary` | text | 候选摘要 |
| `scope_hint` | jsonb | 作用域建议 |
| `quality_score` | numeric(5,4) | 质量分 |
| `extract_prompt_version` | varchar(32) | 抽取模板版本 |
| `status` | varchar(16) | pending/extracting/reviewing/published |
| `created_at` | timestamptz | 创建时间 |

## 4.4 知识主表

### `knowledge_item`

| 字段 | 类型 | 说明 |
|---|---|---|
| `knowledge_id` | varchar(64) PK | 知识 ID |
| `tenant_id` | varchar(64) | 租户 ID |
| `scope_type` | varchar(32) | global/team/project/repo/path |
| `scope_id` | varchar(128) | 作用域 ID |
| `knowledge_type` | varchar(32) | rule/case/procedure |
| `memory_type` | varchar(32) | semantic/episodic/procedural |
| `title` | varchar(256) | 标题 |
| `content` | jsonb | 结构化内容 |
| `status` | varchar(16) | draft/active/deprecated/archived |
| `quality_score` | numeric(5,4) | 质量分 |
| `confidence_score` | numeric(5,4) | 置信度 |
| `freshness_score` | numeric(5,4) | 新鲜度 |
| `version` | int | 版本 |
| `effective_from` | timestamptz | 生效时间 |
| `effective_to` | timestamptz | 失效时间 |
| `created_by` | varchar(64) | 创建人/系统 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

索引建议：

- `idx_knowledge_scope(scope_type, scope_id, status)`
- `idx_knowledge_type(knowledge_type, memory_type, status)`
- `idx_knowledge_fresh(updated_at desc)`

### `knowledge_source_ref`

| 字段 | 类型 | 说明 |
|---|---|---|
| `ref_id` | bigserial PK | 主键 |
| `knowledge_id` | varchar(64) | 知识 ID |
| `ref_type` | varchar(32) | session/file/commit/pr/issue/doc |
| `ref_target_id` | varchar(128) | 来源对象 ID |
| `ref_path` | varchar(512) | 文件路径 |
| `ref_commit` | varchar(64) | commit |
| `ref_pr` | varchar(64) | PR |
| `ref_issue` | varchar(64) | Issue |
| `excerpt_summary` | text | 来源摘要 |

### `knowledge_relation`

| 字段 | 类型 | 说明 |
|---|---|---|
| `relation_id` | bigserial PK | 主键 |
| `knowledge_id` | varchar(64) | 左知识 |
| `related_knowledge_id` | varchar(64) | 右知识 |
| `relation_type` | varchar(32) | similar/depends_on/supersedes |
| `weight` | numeric(5,4) | 权重 |

### `knowledge_tag`

| 字段 | 类型 | 说明 |
|---|---|---|
| `knowledge_id` | varchar(64) | 知识 ID |
| `tag_key` | varchar(64) | 标签键 |
| `tag_value` | varchar(128) | 标签值 |

主键建议：

- `(knowledge_id, tag_key, tag_value)`

## 4.5 抽取与审核表

### `extract_task`

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | varchar(64) PK | 任务 ID |
| `candidate_id` | varchar(64) | 候选 ID |
| `status` | varchar(16) | pending/running/success/failed |
| `model_name` | varchar(64) | 模型名 |
| `prompt_version` | varchar(32) | 提示词版本 |
| `result_ref` | varchar(256) | 结果引用 |
| `error_message` | text | 错误信息 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

### `knowledge_review`

| 字段 | 类型 | 说明 |
|---|---|---|
| `review_id` | bigserial PK | 主键 |
| `knowledge_id` | varchar(64) | 知识 ID |
| `reviewer_id` | varchar(64) | 审核者 |
| `decision` | varchar(16) | approve/reject/revise |
| `comment` | text | 备注 |
| `created_at` | timestamptz | 创建时间 |

## 4.6 检索与反馈表

### `retrieval_request`

| 字段 | 类型 | 说明 |
|---|---|---|
| `request_id` | varchar(64) PK | 请求 ID |
| `session_id` | varchar(64) | 会话 ID |
| `query_text` | text | 查询文本 |
| `query_type` | varchar(32) | feature_impl/bug_fix/explain 等 |
| `repo_id` | varchar(128) | 仓库 ID |
| `branch_name` | varchar(256) | 分支 |
| `file_paths` | jsonb | 文件路径 |
| `token_budget` | int | token 预算 |
| `requested_at` | timestamptz | 请求时间 |

### `retrieval_result`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | bigserial PK | 主键 |
| `request_id` | varchar(64) | 请求 ID |
| `knowledge_id` | varchar(64) | 知识 ID |
| `recall_channel` | varchar(32) | bm25/dense/path_boost 等 |
| `recall_score` | numeric(8,6) | 召回分 |
| `rerank_score` | numeric(8,6) | 重排分 |
| `selected` | boolean | 是否入选上下文包 |
| `selected_rank` | int | 最终排名 |

### `knowledge_feedback`

| 字段 | 类型 | 说明 |
|---|---|---|
| `feedback_id` | bigserial PK | 主键 |
| `knowledge_id` | varchar(64) | 知识 ID |
| `request_id` | varchar(64) | 检索请求 ID |
| `feedback_type` | varchar(32) | accepted/ignored/wrong/stale |
| `feedback_score` | int | 分值 |
| `feedback_text` | text | 文本反馈 |
| `created_by` | varchar(64) | 反馈人 |
| `created_at` | timestamptz | 创建时间 |

## 4.7 配置与审计表

### `config_profile`

| 字段 | 类型 | 说明 |
|---|---|---|
| `profile_id` | varchar(64) PK | 配置 ID |
| `scope_type` | varchar(32) | team/project/repo/path |
| `scope_id` | varchar(128) | 范围 ID |
| `profile_type` | varchar(32) | prompt/retrieval/policy |
| `content` | jsonb | 配置内容 |
| `version` | int | 版本 |
| `status` | varchar(16) | active/inactive |
| `updated_at` | timestamptz | 更新时间 |

### `audit_log`

| 字段 | 类型 | 说明 |
|---|---|---|
| `audit_id` | bigserial PK | 主键 |
| `actor_id` | varchar(64) | 操作人 |
| `action` | varchar(64) | 操作类型 |
| `resource_type` | varchar(32) | knowledge/config/retrieval |
| `resource_id` | varchar(64) | 资源 ID |
| `scope_type` | varchar(32) | 作用域 |
| `scope_id` | varchar(128) | 作用域 ID |
| `detail` | jsonb | 详情 |
| `created_at` | timestamptz | 创建时间 |

## 5. 关系说明

- 一个 `conversation_session` 对应多个 `session_event`
- 一个 `conversation_session` 可产生多个 `knowledge_signal`
- 一个 `knowledge_signal` 对应一个或多个 `knowledge_candidate`
- 一个 `knowledge_candidate` 可生成一个或多个 `knowledge_item`
- 一个 `knowledge_item` 对应多个 `knowledge_source_ref`
- 一个 `retrieval_request` 对应多个 `retrieval_result`
- 一个 `knowledge_item` 对应多个 `knowledge_feedback` 和 `knowledge_review`

## 6. 分区与归档建议

### 6.1 热表

- `session_event`
- `retrieval_request`
- `retrieval_result`
- `audit_log`

建议按月分区。

### 6.2 冷热分离

- 超过 `90` 天的原始事件可归档到对象存储或冷库。
- 摘要与索引保留在线。

## 7. 数据一致性建议

- 检索与日志允许最终一致。
- 知识发布与状态流转需强一致。
- 审核动作需事务提交。

## 8. 数据安全建议

- 敏感字段单独脱敏。
- 原始内容引用采用对象存储地址，不直接写大文本入主表。
- 审计表不可物理删除，只允许归档。

## 9. 向量与搜索索引映射建议

### 9.1 向量主键

- 使用 `knowledge_id + version`
- chunk 级可使用 `knowledge_id + chunk_no`

### 9.2 搜索索引字段

- `title`
- `keywords`
- `tags`
- `scope_type`
- `scope_id`
- `memory_type`
- `knowledge_type`
- `paths`
- `error_codes`

## 10. 初始化建表顺序建议

1. `tenant`
2. `scope_binding`
3. `conversation_session`
4. `session_event`
5. `knowledge_signal`
6. `knowledge_candidate`
7. `knowledge_item`
8. `knowledge_source_ref`
9. `knowledge_relation`
10. `knowledge_tag`
11. `extract_task`
12. `knowledge_review`
13. `retrieval_request`
14. `retrieval_result`
15. `knowledge_feedback`
16. `config_profile`
17. `audit_log`

