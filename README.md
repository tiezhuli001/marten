# youmeng-gateway

个人多 Agent 平台的网关与骨架仓库。

## Current Scope

当前仓库先实现 `Phase 1` 平台骨架：

- FastAPI Gateway 最小入口
- LangGraph 主图骨架
- 最小规则意图路由
- token ledger 占位
- 状态文档读取入口

## Quick Start

```bash
conda create -n youmeng-gateway python=3.12
conda activate youmeng-gateway
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

推荐使用 `Python 3.11` 或 `3.12`。当前 LangGraph / LangChain 相关依赖在 `Python 3.14` 上仍有兼容性警告，不建议作为正式开发环境。

## Configuration

项目通过 `.env` 加载配置，模板见 `.env.example`。

关键配置项：

- `APP_ENV`: 运行环境标识
- `APP_PORT`: FastAPI 服务端口
- `APP_DATA_DIR`: 项目运行时数据目录，默认是项目根目录下的 `data/`
- `DATABASE_URL`: 当前默认使用 SQLite，例如 `sqlite:///data/youmeng_gateway.db`
- `LANGSMITH_TRACING`: 是否开启 LangSmith tracing
- `LANGSMITH_PROJECT`: LangSmith 项目名
- `LANGSMITH_API_KEY`: LangSmith API Key
- `GITHUB_TOKEN`: 后续 GitHub 自动化使用

默认情况下，运行时文件会写入项目内的 `data/`。如果当前环境对项目目录没有写权限，代码会临时回退到系统临时目录，避免服务直接启动失败。

启动后可用接口：

- `GET /health`
- `POST /gateway/message`
- `GET /status/current`
