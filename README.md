# AI Coding Knowledge & Memory MVP

这是一个基于 `FastAPI + SQLAlchemy` 的 MVP / 生产化过渡版本实现，用来验证 `AI Coding 团队知识与记忆系统` 的核心链路，并为后续升级到 `PostgreSQL + Alembic + 向量检索` 预留结构。

## 当前已实现

- 会话创建与查询
- 上下文事件上报
- 基于启发式规则的知识信号识别
- 可选 LLM 增强的知识抽取任务创建与查询
- 知识审核、更新、下线、查询
- 基础配置中心与版本回滚
- 基础检索与上下文包返回
- 检索调试接口
- 知识反馈与上下文包反馈
- 审计日志查询
- 本地 HTTP 客户端与 demo 链路
- 自动化端到端测试
- Docker 部署文件与 demo 脚本
- PostgreSQL 连接配置
- Alembic 迁移骨架
- 向量检索抽象层与简单向量后端
- 可选 API Key 鉴权中间件
- 可配置外部 LLM 验证接口与连通性验证脚本
- GitHub Actions CI 工作流
- 数据库健康检查

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
- `.github/workflows/ci.yml`：CI 工作流
- `docs/`：Proposal、架构、PRD、API、DB、MVP 文档

## 本地启动

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
export AICODING_API_KEY='your-secret'
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

启用 `AICODING_API_KEY` 后，除 `/`、`/healthz`、`/docs`、`/openapi.json` 外，其余接口都需要：

- `X-API-Key: your-secret`
- 或 `Authorization: Bearer your-secret`

## PostgreSQL 示例

```bash
export AICODING_DB_URL='postgresql+psycopg://postgres:postgres@localhost:5432/aicoding_mvp'
export AICODING_VECTOR_BACKEND='pgvector'
export AICODING_API_KEY='replace-with-real-secret'
python3 -m uvicorn app.main:app --reload
```

说明：当前 `pgvector` 仍是占位后端，接口层已经抽象好，后续可直接替换为真实 `pgvector` / 外部向量数据库实现。

## Alembic 迁移

已提供：

- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/20260324_0001_initial_schema.py`

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

如果服务已经启动，也可以走真实 HTTP 链路：

```bash
make client-demo
```

或直接使用命令行客户端：

```bash
python3 scripts/http_client.py demo
python3 scripts/http_client.py create-session --repo-id demo-repo --branch-name feature/demo
python3 scripts/http_client.py retrieve --session-id sess_xxx --query "为订单风控增加渠道黑名单校验" --repo-id demo-repo --file-path src/order/risk/check.ts
```

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

## 健康检查

- `GET /healthz`

返回内容包括：

- 数据库连通性
- 当前向量后端
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

## 已实现核心接口

- `POST /api/v1/sessions`
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
- `GET /api/v1/config/profile`
- `GET /api/v1/config/profile/{profile_id}`
- `PUT /api/v1/config/profile/{profile_id}`
- `POST /api/v1/config/profile/{profile_id}/rollback`
- `POST /api/v1/feedback/knowledge`
- `POST /api/v1/feedback/context-pack`
- `GET /api/v1/audit/logs`

## 请求上下文

服务端会读取并透传这些请求头：

- `X-Request-Id`
- `X-Tenant-Id`
- `X-Team-Id`
- `X-User-Id`
- `X-Client-Type`

其中：

- `X-Request-Id` 会写入响应头，并出现在大部分响应体的 `request_id`
- `X-Tenant-Id`、`X-Team-Id`、`X-User-Id`、`X-Client-Type` 会进入会话元数据和审计日志

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

- 向量检索目前是简单关键词向量后端，不是真实 embedding / pgvector 检索
- 抽取链路支持可选 LLM 增强，但当前仍是同步执行，尚未接入队列和异步 worker
- 权限和敏感信息控制仍是基础骨架，当前仅支持单一 API Key
- 外部 LLM 验证默认按 OpenAI 兼容 `chat/completions` 协议调用，非兼容网关需调整路径或请求格式
- 失效策略尚未自动关联代码变更与版本事件
- Alembic 已提供初始迁移，但尚未引入持续迁移流程与 DB schema drift 校验
