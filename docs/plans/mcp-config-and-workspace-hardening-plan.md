# MCP 配置与 Agent Workspace 收敛计划

> 更新时间：2026-03-17
> 目标：把当前 `youmeng-gateway` 的 MCP 配置方式与 agent/skill workspace 文案，从“能跑的 MVP”收敛为“更接近长期多 Agent 平台”的形态。

## 一、背景

当前项目已经具备：

- `Shared Runtime`
- `GitHub MCP adapter`
- `Main Agent / Ralph / Code Review Agent`
- `AGENTS.md / TOOLS.md / SKILL.md` 最小骨架

但当前仍有两个明显问题：

1. MCP 连接配置过多暴露在 `.env`
2. agent / skill 文案更像临时 prompt，而不像真正的 workspace 配置

## 二、改造目标

本轮只做两件事：

1. 设计并落一版 `mcp.json` 方案
2. 重写当前 3 个 agent 的 `AGENTS.md / TOOLS.md` 与核心 `SKILL.md`

## 三、执行原则

### 3.1 MCP 配置原则

- `.env` 只保留平台级配置
- MCP server 定义优先放入 `mcp.json`
- 运行时负责：
  - 读取配置
  - 建立连接
  - 注册 adapter
- agent 只关心：
  - 可使用哪些 MCP server
  - 可用哪些工具

### 3.2 兼容性原则

- 保留现有环境变量方式作为 fallback
- 没有 `mcp.json` 时不破坏现有测试和代码路径
- 新方案优先级高于 legacy env

### 3.3 Workspace 文案原则

- `AGENTS.md` 负责角色、边界、输入输出、交接条件
- `TOOLS.md` 负责工具优先级、限制、fallback、禁止事项
- `SKILL.md` 负责任务模板、结构化输出契约、失败条件
- 文案风格参考 OpenClaw / OpenCode，但不复制它们的产品耦合语义

## 四、实施步骤

### Step 1：MCP 配置模型

新增：

- `mcp.json.example`
- `MCP_CONFIG_PATH`
- runtime 对 `mcp.json` 的加载逻辑

推荐格式：

```json
{
  "servers": {
    "github": {
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "github-mcp-server", "stdio"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      },
      "cwd": null,
      "timeout_seconds": 30,
      "adapter": "github"
    }
  }
}
```

### Step 2：运行时接入

修改：

- `app/core/config.py`
- `app/runtime/mcp.py`
- `app/services/diagnostics.py`

目标：

- 运行时优先读取 `mcp.json`
- 自动解析 `${ENV_VAR}`
- 继续兼容 legacy `MCP_GITHUB_*`

### Step 3：配置样例与文档

修改：

- `.env.example`
- 配置手册
- 当前状态文档

目标：

- 把 `.env.example` 收敛成平台级配置
- MCP 细节转移到 `mcp.json.example`

### Step 4：Agent Workspace 收敛

重写：

- `agents/main-agent/AGENTS.md`
- `agents/main-agent/TOOLS.md`
- `agents/ralph/AGENTS.md`
- `agents/ralph/TOOLS.md`
- `agents/code-review-agent/AGENTS.md`
- `agents/code-review-agent/TOOLS.md`

### Step 5：核心 Skill 收敛

重写：

- `skills/issue-writer/SKILL.md`
- `skills/coding-planner/SKILL.md`
- `skills/coding-executor/SKILL.md`
- `skills/code-review/SKILL.md`

目标：

- 明确输入输出契约
- 明确 escalation / ambiguity / no-op 条件

### Step 6：测试与验证

最少补充：

- `mcp.json` 读取测试
- env fallback 测试
- diagnostics 行为测试
- AgentRuntime prompt 中 workspace/skills/MCP tools 仍能正确注入

## 五、验收标准

本轮完成后，应满足：

1. 项目支持 `mcp.json` 作为 MCP 主配置入口
2. `.env.example` 不再承担过多 MCP 细节
3. 没有 `mcp.json` 时，legacy env 仍可用
4. 三个 agent 的 workspace 文案具备角色、边界、交接、限制
5. 核心 skills 具备清晰输出契约和失败处理约定
6. 测试通过，且不破坏现有多 Agent MVP 主链路

## 六、非目标

本轮不做：

1. 新增更多 MCP server
2. 引入完整 permission matrix
3. 引入长期 memory 系统
4. 重构整个 control plane

本轮只做：

> MCP 配置入口收敛 + agent workspace 语义收敛
