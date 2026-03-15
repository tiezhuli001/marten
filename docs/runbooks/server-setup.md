# Server Setup

> 范围：Phase 0 前置环境

## 目标

把 Linux 服务器准备成项目主开发和运行环境。

## 必备项

1. conda
2. Python 3.11
3. Git
4. OpenCode
5. OpenClaw
6. GitHub MCP
7. 项目仓库访问能力

## 建议环境

### conda 环境

建议环境名：

```bash
conda create -n youmeng-gateway python=3.11 -y
conda activate youmeng-gateway
```

## GitHub 访问

需要两类能力：

1. `git clone / pull / push`
2. GitHub MCP API 访问

### 建议

- 使用 SSH key 处理 git 仓库读写
- 使用 GitHub Token / OAuth 处理 GitHub MCP

## 项目目录

建议服务器主目录下使用：

```text
~/workspace/youmeng-gateway
```

## 环境变量加载

项目默认从仓库根目录的 `.env` 读取配置，建议从 `.env.example` 复制一份：

```bash
cp .env.example .env
```

当前第一阶段会用到的配置项：

```dotenv
APP_ENV=development
APP_PORT=8000
APP_DATA_DIR=data
DATABASE_URL=sqlite:///data/youmeng_gateway.db
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=youmeng-gateway
LANGSMITH_API_KEY=
GITHUB_TOKEN=
```

说明：

- `APP_DATA_DIR=data` 表示运行时数据默认写入项目根目录下的 `data/`
- `DATABASE_URL=sqlite:///data/youmeng_gateway.db` 表示 SQLite 文件也放在项目内
- 如果后续切 PostgreSQL，再替换 `DATABASE_URL` 即可

## Phase 1 最小启动

```bash
conda activate youmeng-gateway
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

验证接口：

```bash
curl http://127.0.0.1:8000/health
```

## 后续还要补的内容

- OpenCode 安装步骤
- OpenClaw 安装步骤
- GitHub MCP 配置步骤
- 飞书 Channel 配置步骤
- FastAPI 服务启动方式
- systemd / supervisor 守护方式
