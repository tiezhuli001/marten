# Server Setup

> 范围：MVP 运行环境准备

## 目标

把 Linux 服务器准备成 `youmeng-gateway` 的主开发和运行环境，并采用 JSON-first 的配置方式。

## 必备项

1. Python 3.11 / 3.12
2. Git
3. Node.js + `npx`
4. 项目仓库访问能力
5. GitHub token
6. Feishu webhook / event subscription 配置能力

## 推荐目录

```text
~/workspace/youmeng-gateway
```

## 初始化步骤

```bash
cd ~/workspace
git clone <repo-url> youmeng-gateway
cd youmeng-gateway

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .

cp .env.example .env
cp agents.json.example agents.json
cp models.json.example models.json
cp platform.json.example platform.json
cp mcp.json.example mcp.json
```

## 配置原则

### `.env`

只放：

- secrets
- 端口
- 数据目录
- JSON 配置入口

### `agents.json`

放：

- agent workspace
- skills
- MCP servers
- model profile

### `models.json`

放：

- provider profile
- model profile

### `platform.json`

放：

- LLM 超时与重试默认值
- worker 默认值
- git/worktree 默认行为
- review loop 默认值
- 平台级 repo / channel 默认值

### `mcp.json`

放：

- MCP server 定义
- GitHub token
- command / args / env / adapter

## 最小启动

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 最小检查

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/diagnostics/integrations
```

## 说明

- 不配置 `mcp.json` 不影响服务启动，只是 MCP 不可用
- `mcp.json` 推荐由用户直接维护 token
- `.env` 不再承担大部分 agent/platform 高级参数
