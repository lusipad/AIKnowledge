# AI Coding 团队知识与记忆系统 API 设计文档

- 文档版本：`v1.0`
- 文档状态：`Draft`
- 编写日期：`2026-03-24`
- 关联文档：`docs/Design-Arch.md`

## 1. 设计说明

本文档定义系统核心 API 接口规范，面向客户端、MCP Server、平台服务和后台管理端。

API 设计目标：

- 保持资源语义清晰。
- 兼容同步请求与异步任务。
- 为检索、抽取、审核、反馈提供统一接口。
- 目标架构支持多租户与多范围权限控制；当前实现已对 `sessions / knowledge / retrieval / extract task / audit / evaluation / config profile` 等核心路径按 `tenant/team` 做作用域裁剪，并提供 `viewer / writer / reviewer / admin` 四级角色授权，以及知识/配置资源级 ACL。

## 2. 通用约定

### 2.1 基础路径

- Base URL：`/api/v1`

### 2.2 认证

- 支持：`Authorization: Bearer <jwt>` 对接外部 IAM / OIDC / 自建 JWKS
- 支持：`X-API-Key` 或 `Authorization: Bearer <api-key>` 作为平台内部 API Key
- 可通过 `AICODING_API_KEY_ROLES` 为 API Key 绑定角色
- 可通过 `AICODING_IAM_ROLE_MAPPING` 把外部 IAM 角色映射到内部 `viewer / writer / reviewer / admin`
- 支持通过 SCIM 风格目录同步接口写入用户/组映射，补充 Bearer JWT 未显式携带的 tenant/team/role 授权范围

### 2.3 公共请求头

- `X-Tenant-Id`
- `X-Team-Id`
- `X-User-Role`
- `X-Client-Type`
- `X-Request-Id`

说明：

- 启用 IAM Bearer JWT 后，`X-Tenant-Id`、`X-Team-Id` 可用于在 token 已授予的组织/团队列表中显式切换当前作用域
- 如果请求头声明了未获 token 授权的 `tenant/team`，接口返回 `403`

### 2.4 通用响应结构

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "request_id": "req_123"
}
```

### 2.5 错误码建议

- `400100`：参数错误
- `401100`：认证失败
- `403100`：权限不足
- `404100`：资源不存在
- `409100`：状态冲突
- `429100`：请求过载
- `500100`：内部错误

### 2.6 角色建议

- `viewer`：只读查询
- `writer`：会话、事件、检索、反馈
- `reviewer`：包含 `writer`，并可审核知识、查看信号
- `admin`：包含 `reviewer`，并可修改知识、配置与执行评估

## 3. 会话与上下文接口

## 3.1 创建会话

### `POST /sessions`

用途：创建 AI Coding 会话。

请求示例：

```json
{
  "repo_id": "repo_order_center",
  "branch_name": "feature/order-risk-check",
  "task_id": "ISSUE-1024",
  "client_type": "ide"
}
```

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "session_id": "sess_001",
    "started_at": "2026-03-24T10:00:00Z"
  }
}
```

## 3.2 上报会话事件

### `POST /context/events`

用途：上报关键上下文事件。

请求体：

```json
{
  "session_id": "sess_001",
  "events": [
    {
      "event_type": "tool_call",
      "event_subtype": "read_file",
      "summary": "读取订单校验模块",
      "file_paths": ["src/order/risk/check.ts"],
      "timestamp": "2026-03-24T10:01:00Z"
    }
  ]
}
```

响应字段：

- `accepted_count`
- `rejected_count`
- `freshness_updates`

## 3.3 查询会话详情

### `GET /sessions/{session_id}`

用途：获取会话基础信息与状态。

## 3.4 查询会话列表

### `GET /sessions`

常用查询参数：

- `repo_id`
- `status`
- `client_type`
- `task_id`
- `page`
- `page_size`

响应字段补充：

- `event_count`
- `signal_count`

## 4. 检索接口

## 4.1 检索上下文包

### `POST /retrieval/query`

用途：根据任务上下文返回 context pack。

请求示例：

```json
{
  "session_id": "sess_001",
  "query": "为订单风控增加渠道黑名单校验",
  "query_type": "feature_impl",
  "repo_id": "repo_order_center",
  "branch_name": "feature/order-risk-check",
  "file_paths": ["src/order/risk/check.ts"],
  "task_context": {
    "issue_id": "ISSUE-1024",
    "language": "typescript"
  },
  "token_budget": 4000
}
```

响应示例：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "context_summary": "该模块已有名单校验能力，新增渠道维度时需复用现有规则引擎。",
    "rules": [
      {
        "knowledge_id": "kn_rule_001",
        "title": "风控规则必须经统一规则引擎调用",
        "content": "禁止直接在 controller 中拼装风控规则。",
        "score": 0.96
      }
    ],
    "cases": [],
    "procedures": [],
    "sources": [
      {
        "knowledge_id": "kn_rule_001",
        "source_type": "pr",
        "source_ref": "PR-441"
      }
    ]
  }
}
```

## 4.2 检索候选解释

### `POST /retrieval/debug`

用途：返回召回链路、过滤条件和排序明细，用于调试和评估。

说明：当 `session_id` 不在当前 `tenant/team` 作用域内时，返回 `404`。

## 5. 知识接口

## 5.1 创建抽取任务

### `POST /knowledge/extract`

用途：基于候选会话或信号创建异步抽取任务。

请求示例：

```json
{
  "signal_ids": ["sig_001", "sig_002"],
  "force": false
}
```

响应字段：

- `task_id`
- `status`
- `knowledge_id`（仅在同步执行完成或异步任务成功后返回）

## 5.2 查询抽取任务

### `GET /knowledge/extract/{task_id}`

用途：查询抽取任务状态与产物。

说明：仅允许访问当前 `tenant/team` 作用域内会话派生出的任务。

## 5.3 查询知识详情

### `GET /knowledge/{knowledge_id}`

用途：获取知识明细、来源、标签、版本、状态。

响应补充：

- `acl`

## 5.4 查询知识列表

### `GET /knowledge`

常用查询参数：

- `scope_type`
- `scope_id`
- `knowledge_type`
- `memory_type`
- `status`
- `keyword`
- `page`
- `page_size`

## 5.5 更新知识

### `PATCH /knowledge/{knowledge_id}`

用途：修改标题、内容、标签、有效期等可编辑字段。

可选字段：

- `acl`

## 5.6 下线知识

### `POST /knowledge/{knowledge_id}/deprecate`

用途：将知识标记为过期、错误或停止检索。

## 6. 审核接口

## 6.1 提交审核

### `POST /knowledge/review`

请求示例：

```json
{
  "knowledge_id": "kn_rule_001",
  "decision": "approve",
  "comment": "规则来源清晰，可发布到仓库级"
}
```

## 6.2 查询审核记录

### `GET /knowledge/{knowledge_id}/reviews`

用途：返回审核历史。

## 7. 配置接口

## 7.1 获取配置

### `GET /config/profile`

查询参数：

- `scope_type`
- `scope_id`
- `profile_type`

## 7.2 更新配置

### `PUT /config/profile/{profile_id}`

用途：更新提示词模板、检索策略、规则配置。

说明：

- 平台上下文可写 `global / repo / path` 共享配置。
- 租户上下文可写入自身的 `tenant` scope 配置，以及租户私有 `repo / path` 配置。
- 带 `X-Team-Id` 的团队上下文可额外写入自身的 `team` scope 配置，以及团队私有 `repo / path` 配置。
- `repo / path` 配置可选传入 `ownership_mode=shared|tenant|team` 显式声明归属；未传时保持按请求上下文推导的兼容行为。
- 可选传入 `acl` 控制 profile 的 owners / editors / reviewers / viewers。

响应补充：

- `tenant_id`
- `team_id`
- `ownership_mode`

## 7.3 回滚配置

### `POST /config/profile/{profile_id}/rollback`

用途：回滚到指定版本。

说明：回滚遵循与配置写入相同的作用域约束。

## 8. 反馈接口

## 8.1 提交知识反馈

### `POST /feedback/knowledge`

请求示例：

```json
{
  "request_id": "ret_001",
  "knowledge_id": "kn_rule_001",
  "feedback_type": "accepted",
  "feedback_score": 5,
  "feedback_text": "规则准确，直接复用了"
}
```

## 8.2 提交上下文包反馈

### `POST /feedback/context-pack`

用途：对整包上下文的相关性、完整性进行反馈。

## 9. 管理接口

## 9.1 查询信号列表

### `GET /signals`

用途：供平台或审核后台查看待处理信号。

## 9.2 查询检索日志

### `GET /retrieval/logs`

用途：供评估与排障查看召回记录。

常用查询参数：

- `session_id`
- `repo_id`
- `query_type`
- `limit`

响应字段补充：

- `context_feedback`
- `knowledge_feedback_count`

## 9.3 查询检索日志详情

### `GET /retrieval/logs/{request_id}`

用途：查看单次检索请求的候选结果、上下文包反馈和关联知识反馈。

## 9.4 查询审计日志

### `GET /audit/logs`

用途：查看谁在什么范围下使用了哪些知识。

## 9.5 查询当前身份

### `GET /auth/identity`

用途：返回当前请求实际生效的认证来源、用户、角色以及 IAM 同步的 tenant/team 范围。

响应补充：

- `directory_group_ids`：当前 Bearer JWT 用户命中的目录组

### `GET /iam/directory/users`

用途：按当前请求 `tenant/team` 作用域列出目录用户快照，仅 `admin` 可访问。

### `PUT /iam/scim/users/{user_id}`

用途：以 SCIM 风格 upsert 单个目录用户；当请求已带 `tenant/team` 作用域时，未显式传入的字段会自动继承当前作用域。

请求示例：

```json
{
  "email": "user@example.com",
  "display_name": "Platform User",
  "active": true,
  "attributes": {
    "department": "platform"
  }
}
```

### `GET /iam/directory/groups`

用途：按当前请求 `tenant/team` 作用域列出目录组与成员，仅 `admin` 可访问。

### `PUT /iam/scim/groups/{group_id}`

用途：以 SCIM 风格 upsert 单个目录组，并用 `member_user_ids` 全量替换组成员。

请求示例：

```json
{
  "display_name": "Platform Reviewers",
  "scope_type": "team",
  "mapped_role": "reviewer",
  "member_user_ids": ["user_001", "user_002"],
  "attributes": {
    "source": "scim"
  }
}
```

说明：

- `scope_type` 支持 `global / tenant / team`
- `mapped_role` 支持 `viewer / writer / reviewer / admin`
- `scope_id` 省略时会按 `scope_type + tenant_id + team_id` 自动推导

### `POST /iam/directory/sync`

用途：批量同步目录用户与目录组，用于外部 IAM / IdP 定时回写。

请求示例：

```json
{
  "users": {
    "user_001": {
      "display_name": "Platform User"
    }
  },
  "groups": {
    "group_platform_admin": {
      "display_name": "Platform Admins",
      "scope_type": "team",
      "mapped_role": "admin",
      "member_user_ids": ["user_001"]
    }
  }
}
```

### `POST /graph/relations`

用途：创建或更新知识图谱关系，支持跨仓 `repo -> related_repo` 映射。

请求示例：

```json
{
  "knowledge_id": "kn_rule_001",
  "related_knowledge_id": "kn_case_002",
  "relation_type": "supersedes",
  "repo_id": "repo-order",
  "related_repo_id": "repo-gateway",
  "weight": 0.9,
  "detail": {
    "reason": "跨仓改造后由公共规则替代旧案例"
  }
}
```

说明：

- `relation_type` 当前支持 `related_to / implements_rule / supersedes / same_incident_family`
- `repo_id`、`related_repo_id` 省略时会优先从 `repo` 作用域知识自动推导
- 需要对两侧知识具备可见性，且当前用户至少为 `reviewer`

### `GET /graph/knowledge/{knowledge_id}`

用途：查看单个知识节点的图谱视图，返回当前知识、关联边以及当前用户可见的相邻节点。

### `GET /graph/repos/{repo_id}/knowledge-map`

用途：查看指定仓库的 knowledge map，返回与该仓库相关的可见节点和边，支持跨仓关系展开。

## 10. MCP 映射建议

若通过 `MCP` 提供能力，建议映射为以下工具：

- `create_session`
- `append_context_events`
- `retrieve_context_pack`
- `submit_knowledge_feedback`
- `get_repo_config`

## 11. 幂等与限流

### 11.1 幂等建议

- 事件上报支持 `idempotency_key`
- 抽取任务创建支持重复提交去重
- 审核提交支持状态检查

### 11.2 限流建议

- 按租户限流
- 按会话限流
- 对调试接口单独限流

## 12. 版本兼容建议

- 所有 API 走 `/api/v1`
- 非兼容变更通过 `/api/v2`
- 可选字段尽量向后兼容

