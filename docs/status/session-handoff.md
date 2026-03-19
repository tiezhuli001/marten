# Session Handoff

> 更新时间：2026-03-19
> 当前分支：`codex/architecture-deploy-next`

## 1. 当前阶段

- 主链路已经验证到：
  `Feishu inbound -> gateway -> issue -> fix -> pr -> review -> merge`
- 当前下一阶段重点不是补 MVP 功能，而是继续做三类收口：
  - 架构边界继续收紧
  - 项目目录继续调整
  - 部署与开源准备

## 2. 当前仓库真实现状

- 主边界仍然是：
  `channel -> control plane -> runtime -> agent`
- 核心 agent 仍然是：
  - `main-agent`
  - `ralph`
  - `code-review-agent`
- `app/services/*` 已明显减少，当前主要保留：
  - `app/services/automation.py`
  - `app/services/observability.py`
  - `app/services/session_registry.py`
  - `app/services/task_registry.py`
- docs 已收敛到：
  - `docs/architecture/`
  - `docs/evolution/`
  - `docs/status/`

## 3. 真实验证结果

- 已完成一次真实仓库验证：
  - Issue `#56`
  - PR `#57`
  - merge commit `4e7ae48f31cf8cd7bb4fcc25006c844442ec2dfa`
- 参考：
  - `https://github.com/tiezhuli001/youmeng-gateway/issues/56`
  - `https://github.com/tiezhuli001/youmeng-gateway/pull/57`
- 真实链路中发现并修复了一个真实阻塞点：
  - `scripts/run_sleep_coding_validation.py` 曾引用已删除的历史测试，已修正

## 4. `.sleep_coding` 目录说明

- 当前仓库根目录下存在：
  - `.sleep_coding/issue-56.md`
- 它不是运行时临时目录，而是 Ralph 在真实链路里写出的任务 artifact，并且已经被 PR `#57` 合入主分支。
- 从当前仓库定位看，这个目录更像：
  - agent 运行产物
  - trace / artifact
  - 调试与审计材料
- 它不一定适合作为开源仓库主分支长期保留内容。

建议下一位 agent 先做一个明确决策：

1. 如果项目希望保留 agent artifact 作为仓库内证据：
   - 需要补充仓库级约定，说明 `.sleep_coding/` 的用途、保留范围和清理策略
2. 如果项目不希望把运行产物提交到主分支：
   - 应把 `.sleep_coding/` 从主分支移除
   - 并评估加入 `.gitignore`
   - 同时调整 Ralph artifact 策略，只写 worktree 或外部存储，不回写主仓库

当前我的判断是：
- 对开源仓库来说，`.sleep_coding/` 更像应被移出主分支的运行产物
- 但是否删除，应该和后续目录调整一起决定，不建议在没有统一策略前零散处理

## 5. 下一步工作重点

下一位 agent 建议按这个顺序推进：

1. 重新审视目录结构
   - 明确哪些目录属于长期产品结构
   - 明确哪些目录属于运行产物、实验痕迹、部署材料
2. 处理 `.sleep_coding/`、`docs/e2e/` 这类真实链路产物的归属
   - 决定保留、迁移还是移除
3. 梳理部署相关内容
   - 当前仓库缺少适合开源读者的最小部署说明
   - 需要明确本地运行、真实 webhook、MCP、凭据注入、生产部署边界
4. 继续做架构减法
   - 优先审查 `app/services/automation.py`
   - 再审查 `session_registry.py` / `task_registry.py`

## 6. 工作准则

- 不要恢复历史 `plans/`、`requirements/`、`review archive`
- 不要重新把复杂度堆回 `app/services/*`
- 不要在文档中写本地绝对路径
- 不要在对外文档中写当前个人分支、临时 diff、一次性本地状态
- 新增说明要优先面向：
  - GitHub 仓库读者
  - 下一位维护者
  - 部署者

## 7. 交付前最低验证

- `python -m unittest discover -s tests -v`
- `python -m unittest tests.test_sleep_coding tests.test_review tests.test_automation tests.test_mvp_e2e -v`
- 如果继续调整真实链路或 artifact 策略：
  - 必须重新验证 `issue -> fix -> pr -> review -> merge`
