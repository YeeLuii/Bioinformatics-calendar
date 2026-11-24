---
name: ai4s
description: "管理 ai4s项目桌面中的科研项目、结果进度、会话关联、桌面文件夹及日程。用户提及项目工作台、项目桌面、科研日程管理、AI4S工作台或 ai4s，并要求查看、添加、修改、归档、总结项目或安排待办时使用。普通科研分析或其他日历应用请求不因此触发。"
---

# ai4s项目桌面

显式调用为 `$ai4s`，MCP 服务标识为 `ai4s`。“项目工作台”“项目桌面”“科研日程管理”“AI4S工作台”和“ai4s”都是同一工作台的自然语言名称，不创建重复服务。

## 确认工作区与接口

发现 ai4s MCP 工具，先调用 `workspace_status` 和 `projects_list`，核对工作区与已登记项目。通过 MCP 资源 `ai4s://docs/agent`、`ai4s://docs/openapi` 或部署目录中的 AGENT_API.md、openapi.json、docs/API.md 读取本次需要的接口契约。

若当前会话没有加载 MCP，检查客户端注册并提示重载；配置存在不代表工具已加载。已有 HTTP 服务可作为备用，但先通过 `/api/v1/workspace` 确认它与用户目标工作区一致。地址以部署输出、工作区配置或部署记录为准，不假设始终使用默认端口。普通管理请求不重新部署、不修改 Codex 配置。

## 项目与会话

- 查询、添加、局部更新、归档恢复分别使用 `projects_list`、`project_get`、`project_create`、`project_update`、`project_archive`、`project_restore`。
- 先读取对应 revision 再提交。发生冲突时重新读取并合并本次修改，保留其他编辑；项目、会话关联和桌面各自使用独立 revision。
- 关联会话前读取 `project_threads_get`，保留已有链接，再通过 `project_threads_set` 保存。使用实际查询到的会话 ID 和原始标题，不猜测 ID；关联不会向会话发消息，也不会改变 Codex 项目归属。
- `project_summarize` 仅汇总已登记内容。同步进度时读取用户授权范围内的会话和项目说明，注明来源与观察日期，分别说明已交付、探索性结果和待审核事项，不把推测写成已完成。
- 归档只隐藏登记项目，不移动或删除研究文件，不启动分析。

## 桌面和日程

当前十个 MCP 工具不支持日期待办和桌面布局修改。使用同一工作区的 HTTP `/api/board-state` 前先读 docs/API.md：读取完整 cards/todos，只改用户指定内容，并保留其余条目、位置及关联。新建项目不会自动加入已经保存过的桌面；用户要求“加入工作台”时检查项目卡片是否存在。

HTTP 写入前从 `/api/overview` 获取当前进程 token，放在 `X-Desk-Token` 中，不打印或持久保存。项目 HTTP 路由为 `/api/v1/projects` 及其子路由，请求字段以契约为准。所有写入后读回确认。

日程是工作台中的待办，不等于系统提醒或 Codex 自动任务。需要实际提醒时按用户要求使用相应客户端能力，不能声称工作台会自动通知。

## 部署边界

仅在用户要求部署或迁移时读取仓库 docs/DEPLOYMENT.md，运行对应脚本。Codex MCP 使用官方 `codex mcp add` 和现有备份、验证、恢复流程，不手工追加 TOML。不自动覆盖指向其他工作区的同名注册，不将私人路径、数据或真实会话 ID 写入公开技能。
