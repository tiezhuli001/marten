# Phase 3 Implementation Plan

> 更新时间：2026-03-16
> 阶段：Phase 3 Code Review
> 说明：本文件是编码前的实现计划，供回溯和多 agent 协作使用。

## 一、需求澄清

Phase 3 的 `code review agent` 与 `sleep coding` 是两个分开的能力：

1. `code review agent` 可以独立 review：
- GitHub PR 链接
- GitLab MR/PR 链接
- 本地代码目录或本地分支 diff

2. `sleep coding` 的 PR 也可以触发 `code review agent`
- 这是触发关系
- 不是从属关系

3. `docs/code-review/` 不作为 agent 运行产物目录
- 该目录继续保留给外部模型 / 人工 review 归档
- agent 运行产物单独放入 `docs/review-runs/`

## 二、编码目标

本轮编码只实现最小可运行版：

1. 独立 review 入口
2. 调用现有 `code-review skill`
3. 归档 review 结果到 `docs/review-runs/`
4. 有 GitHub / GitLab 链接时尝试评论回写
5. 为 sleep coding 集成提供触发接口
6. 持久化最小 review 状态

## 三、实现拆解

### Step 1 最小状态扩展

在现有 task 或 review 记录上增加：

- `review_status`
- `review_decision`
- `reviewed_at`
- `review_artifact_path`
- `review_comment_url`
- `review_source_type`

原则：

- 不建 findings 明细表
- 不做重型 review schema

### Step 2 独立 ReviewService

新增 `app/services/review.py`：

- 统一接收 review 请求
- 识别输入来源类型
- 组织 skill 输入
- 保存 artifact
- 调用评论回写
- 更新 review 状态

### Step 3 输入来源识别

支持三类 source：

- `github_pr`
- `gitlab_mr`
- `local_code`

对于 local code：

- 先支持本地路径 + 可选分支
- 不要求一开始就支持所有复杂 git 场景

### Step 4 Skill 调用封装

第一版不重写 review 逻辑，只做：

- skill 输入模板生成
- 执行封装
- markdown 结果接收
- 失败时记录 dry-run / error 状态

### Step 5 运行产物归档

输出目录：

- `docs/review-runs/`

命名建议：

- `github-pr-<number>-review.md`
- `gitlab-mr-<number>-review.md`
- `local-review-<timestamp>.md`

### Step 6 评论回写

平台侧只做“如果源是 GitHub / GitLab，则尝试回写 comment”：

- GitHub: 走现有 service 扩展
- GitLab: 第一版可先保留接口或 dry-run 占位

### Step 7 与 Sleep Coding 集成

sleep coding 的集成只做：

- PR 创建后可触发 review agent
- `request_changes` 时把结果回流到 coding

不把 review agent 限制为 sleep coding 私有模块。

## 四、推荐编码顺序

1. review 状态字段与持久化
2. `ReviewService`
3. source type 识别
4. skill 调用封装
5. `docs/review-runs/` artifact 归档
6. GitHub / GitLab 评论回写
7. sleep coding 集成
8. API 与测试

## 五、验收口径

- 可独立发起一次 code review
- review 结果能存到 `docs/review-runs/`
- GitHub / GitLab 至少一类链接可完成评论回写或 dry-run 留痕
- sleep coding PR 可触发同一 review agent
- review 决策状态可查询
