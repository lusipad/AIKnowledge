# AI Coding Knowledge & Memory MVP

这是一个基于 `FastAPI + SQLAlchemy` 的 MVP / 生产化过渡版本实现，用来验证 `AI Coding 团队知识与记忆系统` 的核心链路。当前版本已经打通 `PostgreSQL + Alembic + 原生 pgvector/JWKS IAM/SCIM 目录同步` 主链路，并保留继续扩展到更大规模组织级能力的结构。

## 当前定位

- 当前版本定位为：`多租户请求隔离 + 平台共享/租户私有双层配置 + 原生 pgvector + 外部 IAM/目录同步` 的过渡版
- 当前目标是：稳定验证采集、抽取、审核、检索、反馈、审计与评估闭环
- `X-Tenant-Id`、`X-Team-Id`、`X-User-Id` 已用于会话、知识、提取任务、检索日志、审计和评估的请求级作用域隔离
- `X-User-Role`、`AICODING_DEFAULT_USER_ROLE`、`AICODING_API_KEY_ROLES` 已用于 `viewer / writer / reviewer / admin` 四级权限裁剪
- 服务启动不再隐式建表；首次运行前需要先执行数据库初始化或 Alembic 迁移

## 当前已实现

- 会话创建与查询
- 会话列表与活跃度概览
- 上下文事件上报
- 基于启发式规则的知识信号识别
- 可选 LLM 增强的知识抽取任务创建与查询
- 可选 DB-backed 异步抽取队列与 worker
- 知识审核、更新、下线、查询
- 基础配置中心与版本回滚
- 检索排序、规则去重与上下文包返回
- 检索调试接口
- 检索日志详情与反馈回看
- 知识反馈与上下文包反馈
- 基于迁移 / 下线 / 替换事件的自动失效降级
- 审计日志查询
- 本地 HTTP 客户端与 demo 链路
- 浏览器控制台与一键真实场景演示
- 内建评估框架、可视化自评面板与历史评估记录
- 检索 benchmark / 压测脚本，支持并发、warmup、P50/P95/P99 统计与数据集输入
- 组织级跨仓知识图谱关系与 repo knowledge map 查询
- 检索质量约束：生成知识前排优先、配置规则数量受控、摘要与查询保持相关
- 自动化端到端测试
- Docker 部署文件与 demo 脚本
- PostgreSQL 连接配置
- Alembic 迁移骨架
- 向量检索抽象层、简单向量后端、实时 embedding 后端与持久化数据库向量层
- 可选 API Key 鉴权中间件
- 可配置外部 LLM 验证接口与连通性验证脚本
- GitHub Actions CI 工作流
- 数据库健康检查
- 持续 schema drift 校验
- 按 `tenant/team` 收紧的知识、检索、提取任务与配置访问控制
- 平台共享配置与租户私有 `repo/path` 配置双层数据模型
- SCIM 风格目录用户/组同步与基于目录组的 tenant/team/role 授权补全

## 目录

- `app/main.py`：应用入口与中间件挂载
- `app/settings.py`：环境配置读取
- `app/security.py`：API Key 鉴权中间件
- `app/database.py`：数据库配置与 engine 构造
- `app/client.py`：HTTP 客户端封装
- `app/models.py`：数据库模型
- `app/routers/`：API 路由
- `app/services/extraction.py`：知识抽取与 LLM 回退逻辑
- `app/services/retrieval.py`：检索排序逻辑
- `app/services/vector_store.py`：向量检索抽象层
- `app/services/health.py`：健康检查服务
- `app/services/directory.py`：目录同步与授权补全
- `app/services/graph.py`：知识图谱关系与 repo knowledge map
- `app/services/llm_validation.py`：外部 LLM 连通性验证
- `alembic/`：数据库迁移骨架
- `tests/test_http_e2e.py`：HTTP 级端到端测试
- `tests/test_extraction_service.py`：抽取服务单元测试
- `tests/test_mvp_flow.py`：端到端单元测试
- `tests/test_llm_validation.py`：LLM 验证单元测试
- `tests/test_vector_backend.py`：向量检索单元测试
- `tests/test_security.py`：安全与配置测试
- `scripts/init_db.py`：数据库初始化脚本
- `scripts/demo_flow.py`：本地演示脚本
- `scripts/http_client.py`：HTTP 客户端命令行
- `scripts/verify_llm.py`：LLM 验证脚本
- `scripts/check_schema_drift.py`：数据库 schema drift 校验脚本
- `scripts/run_extract_worker.py`：抽取任务 worker 脚本
- `scripts/evaluate_system.py`：通过 HTTP 触发系统评估并输出 Markdown / JSON 报告
- `scripts/benchmark_retrieval.py`：检索 benchmark / 压测脚本
- `app/static/console/`：浏览器控制台静态前端
- `app/routers/ui.py`：控制台路由与 favicon
- `app/routers/evaluation.py`：评估接口
- `app/services/evaluation.py`：评估执行器、打分规则、评估历史
- `.github/workflows/ci.yml`：CI 工作流
- `docs/`：Proposal、架构、PRD、API、DB、MVP 文档

## 本地启动

首次启动前先初始化数据库：

```bash
make init-db
```

然后启动服务：

```bash
python3 -m uvicorn app.main:app --reload
```

或使用：

```bash
make run
```

## 初始化数据库

```bash
make init-db
```

## 默认配置

默认使用 SQLite：

- `sqlite:///./aicoding_mvp.db`

可通过环境变量覆盖：

```bash
export AICODING_DB_URL='sqlite:///./runtime/dev.db'
export AICODING_VECTOR_BACKEND='simple'
export AICODING_VECTOR_DIMENSIONS='1536'
export AICODING_EXTRACTION_MODE='sync'
export AICODING_EMBEDDING_BASE_URL='https://api.openai.com'
export AICODING_EMBEDDING_API_KEY='replace-with-real-secret'
export AICODING_EMBEDDING_MODEL='text-embedding-3-small'
export AICODING_API_KEY='your-secret'
export AICODING_API_KEY_ROLES='your-secret:admin,readonly-key:viewer'
export AICODING_DEFAULT_USER_ROLE='admin'
export AICODING_IAM_JWKS_URL='https://iam.example.com/.well-known/jwks.json'
export AICODING_IAM_ISSUER='https://iam.example.com/'
export AICODING_IAM_AUDIENCE='aiknowledge'
export AICODING_IAM_ROLE_MAPPING='repo_viewer:viewer,repo_writer:writer,repo_reviewer:reviewer,repo_admin:admin'
export AICODING_API_BASE_URL='http://127.0.0.1:8000'
export AICODING_LLM_BASE_URL='https://api.openai.com'
export AICODING_LLM_API_KEY='replace-with-real-secret'
export AICODING_LLM_MODEL='gpt-5.4-low'
export AICODING_LLM_CHAT_PATH='/v1/chat/completions'
python3 -m uvicorn app.main:app --reload
```

DeepSeek 示例：

```bash
export AICODING_LLM_BASE_URL='https://api.deepseek.com'
export AICODING_LLM_API_KEY='replace-with-real-secret'
export AICODING_LLM_MODEL='deepseek-chat'
python3 scripts/verify_llm.py --prompt "Reply with ok only."
```

启用 `AICODING_API_KEY` 或 `AICODING_IAM_JWKS_*` 后，除 `/`、`/healthz`、`/docs`、`/openapi.json` 外，其余接口都需要认证：

也可使用 `AICODING_API_KEYS='key-a,key-b,key-c'` 配置多个可接受的 API Key。

启用外部 IAM 后，也可直接透传：

- `Authorization: Bearer <jwt>`

以下路径仍保持免鉴权，便于探针和 console 使用：

- `/readyz`
- `/console`
- `/favicon.ico`
- `/static/console/*`

- `X-API-Key: your-secret`
- 或 `Authorization: Bearer your-secret`

## PostgreSQL 示例

```bash
export AICODING_DB_URL='postgresql+psycopg://postgres:postgres@localhost:5432/aicoding_mvp'
export AICODING_VECTOR_BACKEND='pgvector'
export AICODING_VECTOR_DIMENSIONS='1536'
export AICODING_API_KEY='replace-with-real-secret'
python3 -m uvicorn app.main:app --reload
```

说明：当前 `pgvector` / `postgres` 后端会把知识与配置规则的 embedding 持久化到数据库 `vector_index_entry` 表，在 PostgreSQL 上使用原生 `vector(AICODING_VECTOR_DIMENSIONS)` 列和 HNSW cosine 索引，并在检索时直接复用数据库向量排序；如 embedding 网关不可用，会自动回退到简单关键词向量打分。

## Embedding 向量后端

如需启用真实 embedding 检索，可配置：

```bash
export AICODING_VECTOR_BACKEND='embedding'
export AICODING_EMBEDDING_BASE_URL='https://api.openai.com'
export AICODING_EMBEDDING_API_KEY='replace-with-real-secret'
export AICODING_EMBEDDING_MODEL='text-embedding-3-small'
python3 -m uvicorn app.main:app --reload
```

当前实现使用 OpenAI 兼容 `embeddings` 协议，对检索候选进行实时向量打分；如 embedding 网关异常，会自动回退到简单关键词向量打分。若切换到 `pgvector` / `postgres` 后端，则会额外把向量持久化到数据库索引表。

## Alembic 迁移

已提供：

- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/20260324_0001_initial_schema.py`
- `alembic/versions/20260325_0002_add_evaluation_run.py`
- `alembic/versions/20260326_0003_add_team_scope_to_knowledge.py`
- `alembic/versions/20260326_0004_add_vector_index_entry.py`
- `alembic/versions/20260326_0005_add_resource_acl.py`
- `alembic/versions/20260326_0006_add_config_profile_ownership.py`
- `alembic/versions/20260326_0007_enable_native_pgvector.py`
- `alembic/versions/20260326_0008_add_directory_sync_tables.py`
- `alembic/versions/20260326_0009_add_knowledge_relation_graph.py`

执行迁移：

```bash
make migrate
```

## 自动化测试

```bash
make test
```

实际执行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

## Demo 演示

```bash
make demo
```

推荐直接打开浏览器控制台：

- `http://127.0.0.1:8000/console`

控制台支持：

- 一键跑通“订单风控规则接入与回归治理”真实示例
- 手动逐步执行：配置规则、创建会话、上报事件、抽取知识、批量审核、检索、反馈、查看审计
- 运行系统评估：对数据库、上下文透传、抽取质量、规则命中、审计与反馈闭环、时延预算进行打分

控制台会直接调用当前服务 API，并透传：

- `X-Tenant-Id`
- `X-Team-Id`
- `X-User-Id`
- `X-Client-Type`

如果服务已经启动，也可以走真实 HTTP 链路：

```bash
make client-demo
```

或直接使用命令行客户端：

```bash
python3 scripts/http_client.py demo
python3 scripts/http_client.py create-session --repo-id demo-repo --branch-name feature/demo
python3 scripts/http_client.py list-sessions --repo-id demo-repo --page 1 --page-size 10
python3 scripts/http_client.py retrieve --session-id sess_xxx --query "为订单风控增加渠道黑名单校验" --repo-id demo-repo --file-path src/order/risk/check.ts
python3 scripts/http_client.py list-retrieval-logs --repo-id demo-repo --query-type feature_impl --limit 5
python3 scripts/http_client.py get-retrieval-log --request-id ret_xxx
```

## 系统评估

如果服务已启动，可以直接执行：

```bash
make evaluate
```

或：

```bash
python3 scripts/evaluate_system.py --format markdown
python3 scripts/evaluate_system.py --format json --output runtime/evaluation.json
```

评估框架会执行内建真实场景，并输出：

- readiness score
- 分类得分：availability / extraction / retrieval / governance / latency
- 检索质量指标：生成知识前排命中、摘要 query 相关性、配置规则占比
- 关键失败项
- 评估过程中产生的 `session_id`、`knowledge_id`、`request_id`
- 最近一次评估历史，可在控制台和 API 中查看

也可以通过浏览器控制台中的“运行系统评估”按钮触发。

## 检索 Benchmark

如果服务已启动，可以直接执行：

```bash
make benchmark
```

或：

```bash
python3 scripts/benchmark_retrieval.py \
  --repo-id demo-repo \
  --branch-name feature/benchmark \
  --query "为订单风控增加渠道黑名单校验与回归检查" \
  --file-path src/order/risk/check.ts \
  --iterations 10 \
  --warmup 2 \
  --concurrency 4 \
  --format markdown
```

也支持通过数据集文件批量执行：

```bash
python3 scripts/benchmark_retrieval.py --dataset runtime/retrieval-benchmark.json --format json --output runtime/benchmark.json
```

输出内容包括：

- benchmark 请求总数、成功率、吞吐
- `avg / p50 / p95 / p99 / max` 时延
- 每个 case 的独立统计
- 每次请求的成功/失败明细

## Docker 启动

```bash
docker compose up --build
```

默认会启动：

- `postgres`
- `ai-coding-memory`

启动后访问：

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/console`

## 健康检查

- `GET /healthz`
- `GET /readyz`

返回内容包括：

- 数据库连通性
- schema 是否与 Alembic head 一致
- 当前向量后端
- `pgvector` 原生向量存储状态、extension 安装状态与向量维度
- 是否启用 API Key
- 是否已配置外部 LLM 验证
- 当前版本

## LLM 验证

配置 `AICODING_LLM_*` 环境变量后，可执行：

```bash
make verify-llm
```

或直接运行：

```bash
python3 scripts/verify_llm.py --prompt "Reply with ok only."
```

也可调用接口：

- `GET /api/v1/llm/config`
- `POST /api/v1/llm/verify`

## Schema Drift 校验

可直接执行：

```bash
make check-schema
```

或：

```bash
python3 scripts/check_schema_drift.py
```

返回内容包括：

- 当前数据库是否与 Alembic head 一致
- `current_heads` 与 `expected_heads`
- metadata diff 明细

`/healthz` 与 `/readyz` 也会返回 `schema.ok` 和 drift 明细，便于探针、发布前检查和 CI 判定。

## 异步抽取 Worker

默认抽取模式为 `sync`，便于本地 demo 和测试直接跑通。

如需启用 DB-backed 异步抽取队列：

```bash
export AICODING_EXTRACTION_MODE='async'
python3 -m uvicorn app.main:app --reload
```

然后运行 worker：

```bash
make run-extract-worker
```

或：

```bash
python3 scripts/run_extract_worker.py --loop --poll-sec 2
```

在 `async` 模式下，`POST /api/v1/knowledge/extract` 会先返回 `pending` 任务，再由 worker 消费并更新为 `success`。

## 已实现核心接口

- `POST /api/v1/sessions`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `POST /api/v1/context/events`
- `GET /api/v1/signals`
- `POST /api/v1/knowledge/extract`
- `GET /api/v1/knowledge/extract/{task_id}`
- `POST /api/v1/knowledge/review`
- `GET /api/v1/knowledge`
- `GET /api/v1/knowledge/{knowledge_id}`
- `PATCH /api/v1/knowledge/{knowledge_id}`
- `POST /api/v1/knowledge/{knowledge_id}/deprecate`
- `GET /api/v1/knowledge/{knowledge_id}/reviews`
- `GET /api/v1/llm/config`
- `POST /api/v1/llm/verify`
- `POST /api/v1/retrieval/query`
- `POST /api/v1/retrieval/debug`
- `GET /api/v1/retrieval/logs`
- `GET /api/v1/retrieval/logs/{request_id}`
- `GET /api/v1/config/profile`
- `GET /api/v1/config/profile/{profile_id}`
- `PUT /api/v1/config/profile/{profile_id}`
- `POST /api/v1/config/profile/{profile_id}/rollback`
- `POST /api/v1/feedback/knowledge`
- `POST /api/v1/feedback/context-pack`
- `GET /api/v1/audit/logs`
- `GET /api/v1/auth/identity`
- `POST /api/v1/graph/relations`
- `GET /api/v1/graph/knowledge/{knowledge_id}`
- `GET /api/v1/graph/repos/{repo_id}/knowledge-map`
- `GET /api/v1/iam/directory/users`
- `PUT /api/v1/iam/scim/users/{user_id}`
- `GET /api/v1/iam/directory/groups`
- `PUT /api/v1/iam/scim/groups/{group_id}`
- `POST /api/v1/iam/directory/sync`
- `GET /api/v1/evaluation/scenarios`
- `POST /api/v1/evaluation/run`
- `GET /api/v1/evaluation/runs`
- `GET /api/v1/evaluation/runs/{run_id}`
- `GET /console`
- `GET /readyz`

## 请求上下文

服务端会读取并透传这些请求头：

- `X-Request-Id`
- `X-Tenant-Id`
- `X-Team-Id`
- `X-User-Id`
- `X-User-Role`
- `X-Client-Type`

其中：

- `X-Request-Id` 会写入响应头，并出现在大部分响应体的 `request_id`
- `X-Tenant-Id`、`X-Team-Id`、`X-User-Id`、`X-User-Role`、`X-Client-Type` 会进入会话元数据和审计日志
- 当前版本已对 `sessions / knowledge / retrieval / retrieval logs / extract task / audit / evaluation / config profile` 等核心读写路径按 `tenant/team` 做作用域裁剪
- `PUT /config/profile/{profile_id}` 与 `POST /config/profile/{profile_id}/rollback` 已对资源归属做校验：
- 平台上下文可管理平台共享 `global / repo / path`
- 租户上下文可管理本租户 `tenant` 与租户私有 `repo / path`
- 团队上下文可额外管理本团队 `team` 与团队私有 `repo / path`
- `PUT /config/profile/{profile_id}` 支持显式传入 `ownership_mode=shared|tenant|team` 控制 `repo/path` 配置归属
- 启用 IAM Bearer JWT 后，`tenant/team/user/role` 可直接从外部 token claim 同步，并支持对 `X-Tenant-Id`、`X-Team-Id` 做授权范围校验
- 目录同步接口可写入 `directory_user / directory_group / directory_group_membership`，并把目录组映射补充到 Bearer JWT 的 `allowed_tenant_ids / allowed_team_ids / user_role`
- 图谱接口可写入 `knowledge_relation`，支持跨仓 `repo_id -> related_repo_id` 关系与 repo knowledge map 查询
- 当前内置角色能力为：`viewer` 只读、`writer` 可写会话/检索/反馈、`reviewer` 可审核知识与查看信号、`admin` 可变更配置/知识与执行评估

## 配套文件

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `Makefile`
- `.gitignore`
- `alembic.ini`
- `alembic/`
- `.github/workflows/ci.yml`

## 当前限制

- 外部 LLM 验证默认按 OpenAI 兼容 `chat/completions` 协议调用，非兼容网关需调整路径或请求格式
- 服务启动前需要先执行 `make init-db` 或 `make migrate`，否则应用会在启动阶段 fail-fast
