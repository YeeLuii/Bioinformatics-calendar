# 完整接口说明 · v1.2.1

1.2.1 新增卡片 `order` 字段，规则见[文件夹整理](FOLDER_ORGANIZATION.md)。

本服务管理科研项目、日程和分析结果的引用。默认 HTTP 基址为 `http://127.0.0.1:8828`，实际端口以工作区配置为准。MCP 使用本地 stdio，不通过 HTTP。

[OpenAPI 3.1](../openapi.json) 描述稳定的 `/api/v1/` 项目、任务、卡片、变更历史和迁移接口；[Agent 指南](../AGENT_API.md) 描述调用流程。本文同时记录网页内部接口。内部接口不承诺跨版本兼容。

## 1. 公共约定

HTTP 请求与响应为 UTF-8 JSON。字段名称区分大小写，v1 请求拒绝未知字段。写入方法不支持用 GET 替代。JSON 请求最大 2 MiB。

- 所有 HTTP 请求的 Host 必须是当前端口的 `127.0.0.1` 或 `localhost`。
- 写入前调用 `GET /api/overview` 获取 `token`，再发送 `X-Desk-Token: <token>`。
- 浏览器写入的 Origin 必须是同端口的本机地址；非浏览器调用可以不发送 Origin。
- token 随服务进程重新启动而改变。它用于限制本机网页跨来源操作，不是多用户登录凭据。
- 没有远程认证、CORS 开放访问、任意命令执行或通用文件下载接口。

### revision 与并发

项目元数据、项目会话关联、桌面安排各自有一个**整个存储级别**的 revision，不是每个项目独立计数。读取后提交当前 revision；任何成功写入都会递增。过期写入返回冲突，不覆盖其他客户端的改动。

项目操作读取 `projects_list` / `project_get` 的 revision；会话操作读取 `project_threads_get` 的 revision；桌面整体保存读取 `/api/board-state` 的 revision。三者不能互换。

HTTP 成功一般返回 200；刷新请求返回 202。错误体为 `{"error":"错误说明"}`：

| 状态码 | 含义 | 处理方式 |
|---|---|---|
| 400 | 字段、数据格式、文件访问或参数无效 | 核对输入和路径 |
| 403 | Host、Origin 或 token 不匹配 | 使用正确本机地址，重新取 token |
| 404 | v1 项目、路由、登记条目或导出文件不存在 | 重新查询 ID / 可用能力 |
| 409 | revision 过期 | 重新读取，比较差异后提交 |

会话关联接口遇到不存在的项目目前由关联验证返回 400；`project_get/update/archive/restore/summarize` 返回 404。不得把所有 400 自动重试为写入。

## 2. 项目字段

| 字段 | 类型 / 限制 | 含义 |
|---|---|---|
| `id` | 1–80 位英文字母、数字、`_`、`-` | 稳定项目编号；新建可省略并自动生成，更新不可改 |
| `name` | 非空字符串，最多 12000 字符 | 名称；新建必需 |
| `summary` | 字符串，最多 12000 字符 | 研究问题与项目概述 |
| `status` | 同上 | 自由文本进度；并非实时任务监视值 |
| `current_version` | 同上 | 当前采用的分析或结果版本 |
| `scope` | 同上 | 适用范围、限制及确认程度 |
| `todo` | 同上 | 下一步事项；与日历中逐项待办不同 |
| `local` | 同上 | 本机目录，支持工作区相对路径 |
| `remote` | 同上 | 服务器文件系统路径；留空不显示服务器入口 |
| `ssh_alias` | 字母、数字、`_ . @ : -`，不能以 `-` 开头 | 已配置的 SSH 别名或主机；不存密码 |

更新是局部 patch，未提供字段不变，空字符串清空字段（`name` 不允许清空）。输入首尾空白会去除。读出的项目还包含 `archived`（如已登记）、`counts`、`local_id`、`remote_id` 等投影字段，不要将整个读取结果原样作为 patch。

读出 `local/remote` 是应用路径映射后的地址。`project_update` 仅提交想修改的字段，避免误把迁移后的显示路径写回原始登记。

## 3. 稳定 HTTP API 与 MCP 对应表

下表中的 `id` 对应 URL 参数 `project_id`。HTTP 请求体省略 `project_id`；MCP 调用需放在 arguments 中。

| MCP 工具 | HTTP 方法和路径 | 参数 | 成功结果 |
|---|---|---|---|
| `projects_list` | GET `/api/v1/projects` | 查询参数 `include_archived=true/false`，默认 false | `{revision, projects[]}` |
| `project_get` | GET `/api/v1/projects/{id}` | 无请求体 | `{revision, project, threads[]}` |
| `project_create` | POST `/api/v1/projects` | `{project, expected_revision}` | `{revision, project, threads[]}` |
| `project_update` | PATCH `/api/v1/projects/{id}` | `{patch, expected_revision}` | 同上 |
| `project_archive` | POST `/api/v1/projects/{id}/archive` | `{expected_revision}` | 同上，`archived=true` |
| `project_restore` | POST `/api/v1/projects/{id}/restore` | `{expected_revision}` | 同上，`archived=false` |
| `project_summarize` | GET `/api/v1/projects/{id}/summary` | 无请求体 | 项目详情 + `summary, basis, results[]` |
| `project_threads_get` | GET `/api/v1/projects/{id}/threads` | 无请求体 | `{revision, project_id, threads[]}` |
| `project_threads_set` | PUT `/api/v1/projects/{id}/threads` | `{threads, expected_revision}` | 同上，使用会话存储 revision |
| `workspace_status` | GET `/api/v1/workspace` | 无请求体 | 工作区路径、能力、Schema 和协议版本 |

归档仅隐藏活跃列表中的项目、结果包和项目卡片。文件、原会话、卡片位置和待办保留。恢复后原有卡片位置重新显示。没有永久删除研究数据的项目接口。

### 会话关联

```json
{
  "expected_revision": 0,
  "threads": [
    {"id":"00000000-0000-4000-8000-000000000001","title":"示例会话","provider":"codex"}
  ]
}
```

UUID 是虚构示例，实际使用时替换为已有会话。`title` 必填，`provider` 可省略，目前只支持 `codex`。每次替换该项目的完整关联列表，最多 100 条；不应遗漏需要保留的关联。空数组解除全部关联，不会关闭或删除真实会话。

### 汇总

`summary` 是已登记名称、概述、进度、版本、范围和待办拼接成的文字。`results` 是该项目结果包的编号、名称、分类、范围和版本。`basis` 给出：

```json
{
  "type":"registered_metadata",
  "index_observed_at":"2026-11-23T10:00:00+08:00",
  "generated_at":"2026-11-23T10:30:00+08:00",
  "note":"汇总已登记信息，未重新读取研究结果或验证科学结论。"
}
```

未接入结果索引时 `index_observed_at` 可为空。汇总不调用模型、不读取全部研究文件、不重新确认结论；Agent 可基于返回值撰写说明，再按用户指令更新概述。

## 4. 可执行 HTTP 示例

`examples/http_client.py` 只使用 Python 标准库。以下新建操作会在你指定的工作区写入一个演示项目：

```bash
python examples/http_client.py --base http://127.0.0.1:8828 list
python examples/http_client.py --base http://127.0.0.1:8828 create-example
python examples/http_client.py --base http://127.0.0.1:8828 summary --project-id api-example
```

等价的 Python 代码：

```python
import json
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8828"
def call(path, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Desk-Token"] = token
    data = None if body is None else json.dumps(body).encode("utf-8")
    with urlopen(Request(base + path, data=data, headers=headers, method=method)) as r:
        return json.load(r)

token = call("/api/overview")["token"]
revision = call("/api/v1/projects")["revision"]
created = call("/api/v1/projects", "POST", {
    "expected_revision": revision,
    "project": {"name": "样本质控", "summary": "检查样本质量与重复一致性"}
}, token)
project_id = created["project"]["id"]
call("/api/v1/projects/" + project_id, "PATCH", {
    "expected_revision": created["revision"],
    "patch": {"status": "质控完成", "todo": "复核异常样本"}
}, token)
```

实际程序应捕获 HTTP 409，读取最新内容后再合并，不要自动覆盖。

## 5. MCP 协议与部署

入口：`python -B /absolute/path/desktop_mcp.py --config /absolute/path/workspace.json`。Codex 使用 [部署脚本](DEPLOYMENT.md) 通过官方 CLI 注册，不手工追加 TOML。其他客户端的参考配置可通过 `desktop_manage.py mcp-config` 生成，JSON 输出使用 `mcpServers.ai4s`。

传输为一行一个 UTF-8 JSON-RPC 消息。stdout 仅输出协议消息，日志写 stderr。支持协商版本：`2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05`。客户端先 initialize，再发 `notifications/initialized`。

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"example","version":"1"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"projects_list","arguments":{}}}
```

成功结果包含 `content: [{type:"text",text:"JSON 结果"}]` 和 `isError:false`。协商 2025-06-18/2025-11-25 时，还包含 `structuredContent`，`tools/list` 提供 `outputSchema`。

工具错误为 `isError:true`，text 中 JSON 为 `{error, message}`；错误标识有 `revision_conflict`、`not_found`、`invalid_request`。协议错误使用 JSON-RPC code：`-32700` JSON 解析失败、`-32600` 请求无效、`-32601` 方法不存在、`-32602` 参数无效、`-32002` 会话未初始化等、`-32603` 内部错误。

资源接口：

| URI | MIME | 内容 |
|---|---|---|
| `ai4s://docs/openapi` | application/json | 实时生成的 OpenAPI 与工具契约 |
| `ai4s://docs/agent` | text/markdown | Agent 使用说明 |

另支持 `ping`、`resources/list` 和 `resources/read`。没有远程 HTTP MCP、订阅、prompts、sampling、任意 shell 工具或代发聊天功能。

## 6. 网页内部接口

接口1.1新增可选项目字段 `addresses`，HTTP 与 MCP 的项目新建、读取和更新使用同一 Schema，原 `/api/v1` 路由保持兼容。数组元素为 `{id,kind,path,label?,ssh_alias?}`；约束、局部修改时的保留规则及完整示例见 [数据模型](DATA_MODEL.md)。`/api/item?id=project:<项目ID>:address:<地址ID>` 返回已登记附加位置；目录打开接口仍只允许本机目录，服务器入口提供对应 SSH 命令，网页在浏览器中打开。

以下用于内置网页，非稳定 v1 API。所有写入同样要求 token 和当前来源；不应把导航接口当作任意路径或命令执行工具。

| 方法 | 路径 | 请求 / 响应与用途 |
|---|---|---|
| GET | `/api/overview` | 合并项目、结果包、分类、计数、时间、`capabilities`、token、`refresh_running` |
| GET | `/api/deploy-health` | 部署自检：`application,pid,app_dir,data_dir,workspace_root,deployment_id`；同样限制 Host |
| POST | `/api/deploy-stop` | 部署启停：`{deployment_id}`，要求 token、合法来源和匹配的非空实例标识；成功返回 `{stopping:true}` 后关闭 HTTP；标识不符为 403，刷新运行中为 409 |
| GET | `/api/openapi.json` | 实时 OpenAPI 文档 |
| GET | `/api/agent-guide` | Agent Markdown 文档 |
| GET | `/api/projects` | 原始人工覆盖存储 `{schema_version,revision,projects[]}` |
| POST | `/api/projects` | `{revision,project}`，网页新建或完整字段编辑；优先使用 v1 接口 |
| GET | `/api/threads` | 已登记会话目录快照 `{threads[]}`，不是当前运行状态 |
| GET | `/api/project-links?project_id=...` | 关联列表及关联 revision |
| POST | `/api/project-links` | `{revision,project_id,threads[]}`，替换关联列表 |
| GET | `/api/board-state` | `{revision,cards[],todos[],saved_at}` |
| POST | `/api/board-state` | 完整 `{revision,cards[],todos[]}`；保存后返回新状态；冲突 409 |
| GET | `/api/files` | 可选筛选 `project_id,category,host,bundle_id,object_type,q,page`；每页 50 条；返回 `{rows,total,page,pages}` |
| GET | `/api/item?id=...` | 已登记的文件、目录或项目根目录元数据 |
| GET | `/api/folder?id=...` | 已登记本地条目所在目录 `{folder}`，不打开 |
| GET | `/api/preview?id=...` | 仅已登记本地 md/txt/json/tsv/csv；最多 64 KiB，返回 `{path,text,truncated}` |
| POST | `/api/open-folder` | `{id}`；打开已登记本地目录，返回 `{opened}` |
| POST | `/api/open-card` | `{id}`；打开已保存的会话或目录卡片，返回 `{opened}` |
| POST | `/api/open-thread` | `{project_id,thread_id}`；仅打开该项目已关联的 Codex 会话，返回 `{opened}` |
| POST | `/api/refresh` | `{}`；启动预先配置的适配器，返回 202 `{running:true}`；运行中不重复启动 |
| GET | `/api/refresh-status` | `{running,exit_code,status}`；status 来自适配器可选 `refresh_status.json` |
| GET | `/export/files.tsv` | 可选逐文件清单下载，未提供时 404 |
| GET | `/export/summary.md` | 可选结果摘要下载，未提供时 404 |

`capabilities` 中 `file_index`、`refresh`、`export_files`、`export_summary` 决定相应功能是否可用。没有文件索引时 `/api/files` 返回空结果，其他项目和日程功能正常使用。`opened` 表示已向操作系统提交打开请求，不保证目标应用已成功加载。

### 日历和布局整体保存示例

先读取当前状态，保留所有 cards 和 todos，仅增改目标项。下例中 `p-rnaseq` 必须是当前存在的卡片 ID：

```json
{
  "revision": 3,
  "cards": [
    {"id":"p-rnaseq","type":"project","target":"rnaseq","title":"RNA-seq 质控","folder":"","zone":"do","x":0.2,"y":0.2}
  ],
  "todos": [
    {"id":"todo-qc","title":"检查重复一致性","date":"2026-11-24","card":"p-rnaseq","done":false}
  ]
}
```

此接口替换整个安排，不是局部 patch。不要直接把上面的单卡示例提交到已有工作区。新集成优先使用下面的逐项任务和卡片接口。卡片、待办、文件索引的完整字段限制见 [数据模型](DATA_MODEL.md)。

## 7. 任务、甘特与卡片 · 1.2

日历与甘特图共享 `desktop_board_state.json` 中的 todos；没有第二份任务数据库。所有任务和卡片写入共用该文件的 revision，读取 `tasks_list` 或 `cards_list` 的 revision 后写入。网页、HTTP 和 MCP 使用同一校验与业务操作。

| MCP | HTTP | 请求 | 响应 |
|---|---|---|---|
| `tasks_list` | GET `/api/v1/tasks` | 可选查询 `project_id` | `{revision,tasks,warnings}` |
| `task_create` | POST `/api/v1/tasks` | `{expected_revision,task}` | `{revision,task,tasks,warnings}` |
| `task_update` | PATCH `/api/v1/tasks/{task_id}` | `{expected_revision,patch}` | 同上 |
| `task_remove` | POST `/api/v1/tasks/{task_id}/remove` | `{expected_revision}` | `{revision,tasks,warnings}` |
| `cards_list` | GET `/api/v1/cards` | 无 | `{revision,cards}` |
| `card_create` | POST `/api/v1/cards` | `{expected_revision,card}` | `{revision,card,cards}` |
| `card_update` | PATCH `/api/v1/cards/{card_id}` | `{expected_revision,patch}` | 同上 |
| `card_remove` | POST `/api/v1/cards/{card_id}/remove` | `{expected_revision}` | `{revision,cards}` |

任务最小创建字段为 title 和 date；建议调用方提供稳定 id，便于断线重试。同 ID 且提交字段与现有项一致的创建返回现有内容、不增加 revision；同 ID 不同内容返回 409，绝不静默覆盖。项目创建也遵循该约定。服务器分配 ID 的请求不能仅靠原请求自动去重。

```json
{
  "expected_revision": 4,
  "task": {
    "id": "review-expression-v3",
    "title": "复核重复样本一致性",
    "project_id": "rnaseq",
    "start_date": "2026-11-25",
    "date": "2026-11-27",
    "status": "todo",
    "progress": 0,
    "dependencies": [],
    "milestone": false,
    "repeat": "none",
    "notes": "检查样本相关性与异常样本依据"
  }
}
```

任务字段与规则：

- id：1–100 位字母、数字、连字符或下划线；title：1–1000 字符；notes：最多12000字符。
- project_id：已登记项目 ID 或空字符串，关联项目可归档。card：兼容旧卡片 ID，可省略。移除卡片不解除已有项目关联。
- start_date/date：有效 YYYY-MM-DD，分别为开始、截止日期，开始不得晚于截止。省略 start_date 时等于 date。里程碑 milestone=true 时两者必须相同。
- status：todo、doing、blocked、done；progress 为0–100整数。done 与 status 同步；完成任务为100%，重新打开任务会将原100%重置为0%。progress 是任务工作进度，不是科研结论可信度。
- dependencies：最多100个现有任务 ID，无重复，不得自依赖或成环。删除仍被依赖的任务会被拒绝。前置任务未完成、排期重叠会返回 warnings；不会自动改其他任务的日期。
- repeat：none、daily、weekly、monthly。由未完成变为完成时，仅创建一条下次任务；完成时间不会让系统补生无数过期任务。下次日期按本次计划日期推进，月末截到下月有效日；重复取消完成/再完成不会重复创建。后续实例可单独改期。
- 为兼容旧数据，读任务时补足默认字段；仅读取不改写文件。旧卡片关联可推导 project_id。旧版客户端整体保存不会清空同 ID 任务未提供的新字段。

卡片字段沿用第6节与数据模型。type/title必需；target/folder默认为空，zone默认inbox，x/y默认0。文件夹是 `type=folder` 的卡片；移除文件夹后其子卡片返回待安排区。所有操作只改元数据。

## 8. 变更记录与安全撤销

| MCP | HTTP | 约定 |
|---|---|---|
| `history_list` | GET `/api/v1/history` | `{revision,entries}` |
| `history_undo` | POST `/api/v1/history/{entry_id}/undo` | `{expected_revision}` -> `{revision,undone,entry}` |

历史 revision 是项目、关联、桌面三个存储 revision 之和，只使用 history_list 返回的值。每条 entry 包含 id、store、at、label、changes；changes 元素为 `{collection,key,before,after}`。已撤销项有 undone_by，撤销动作自身记录 undo_of。

每个存储最多保留100条有内容的变更。记录嵌入对应元数据文件，和业务数据一起原子写入，普通项目/桌面响应不携带历史。撤销检查本次修改涉及的字段：无关的后续字段保留；同一字段发生后续修改则409拒绝。系统更新时间不作为覆盖冲突。创建撤销不能留下引用已不存在项目的卡片或任务；此时应归档项目。已被依赖的任务不能因撤销而变成孤立引用。迁移映射使用配置备份，不属于这三类历史。

## 9. 诊断、路径迁移与导出

| MCP | HTTP | 请求与返回 |
|---|---|---|
| `workspace_diagnostics` | GET `/api/v1/diagnostics` | `{checked_at,checks,locations,path_mappings,config_revision}` |
| `path_mappings_preview` | POST `/api/v1/path-mappings/preview` | `{mappings}` -> `{locations,changes,config_revision}` |
| `path_mappings_set` | PUT `/api/v1/path-mappings` | `{mappings,expected_revision}` -> 新诊断结果 |
| `workspace_export` | GET `/api/v1/export` | 必需format=markdown/ics/json，可选project_id -> `{format,filename,content}` |

所有 HTTP POST/PUT/PATCH 均需令牌，包括只读预览。诊断 locations 元素为 project_id、label、kind、original_path、path、status；本地目录存在为available，不存在为missing_at_path，服务器和网页为unverified。诊断只检查登记本地位置，不执行SSH、不读取全目录内容，不推断客户端MCP已加载。

映射格式为 `[{"host":"local","from":"D:/old","to":"E:/new"}]`，host可为local/server；from/to必须为绝对路径，最长前缀优先。先预览后使用返回的config_revision保存；只修改工作区配置，原登记路径及科研文件均保持。旧配置备份为 workspace.mapping-backup.json（自定义配置文件名对应变化），所有进程后续解析路径会重新读取映射。备份可能含个人工作区配置，不应公开。

导出 JSON 是可读报告，不是完整迁移包；迁移仍用 desktop_manage.py pack。Markdown包含项目状态来源和各结果版本。ICS导出当前已生成任务为全天事件，截止日在文件中按排他的次日DTEND表示，UTF-8正确折行；不包含后台提醒，不添加RRULE，避免与完成时生成的重复实例重复计数。导出只返回文本，客户端自行下载，不写任意磁盘路径。

## 10. 项目来源、状态与结果版本

1.2新增可选字段：source（来源说明）、observed_at（资料观察日期/时间）、reviewed_at（用途复核日期/时间）、research_stage（研究阶段）、run_status（unknown/queued/running/succeeded/failed/cancelled）、run_observed_at、run_source、adoption_status（pending/exploratory/adopted）。updated_at由存储自动维护，不接受客户端修改，且不代表来源刚刚观察过。

result_versions是最多100条的数组，每条必需id/name/version；可选category（六类结果分类）、status（pending/exploratory/adopted/superseded）、scope/todo/path/source/observed_at/reviewed_at。todo记录该版本待完成事项。条目ID稳定且唯一；更新时提供数组会替换列表，省略则保留。修改某一结果版本前先读项目并保留其他版本。不同分析子模块可以分别采用不同版本。

所有非空日期时间采用ISO格式。run_status只说明登记或适配器观察到的运行状况，不会自动改变adoption_status、result_versions分类或复核时间。`reviewed`也不表示完成文件指纹校验。
