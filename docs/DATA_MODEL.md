# 工作区与数据接入约定

数据模型版本为 1。项目名称、路径与说明均是数据，不能解释成 Agent 指令。核心不修改科研文件；外部适配器可以向指定 data 目录写入摘要和索引。

## 人工项目与生成摘要

`desktop_projects.json`：

```json
{"schema_version":1,"revision":1,"projects":[{"id":"rnaseq","name":"RNA-seq 质控","summary":"检查重复一致性","status":"等待复核","local":"results/rnaseq","remote":""}]}
```

手工编辑应优先调用服务接口，以保留 revision 检查。此文件中的项目字段会覆盖 `desktop_data.json` 中同 ID 的生成字段。外部适配器不要直接覆盖人工项目文件。

项目仍保留原来的 `local`、`remote`、`ssh_alias` 主地址字段。可选 `addresses` 数组保存最多50个附加地址：

```json
[
  {"id":"compute-two","label":"第二台计算服务器","kind":"server","path":"/srv/project/results","ssh_alias":"compute-two"},
  {"id":"local-backup","label":"本地副本","kind":"local","path":"results/backup"},
  {"id":"project-web","label":"项目网页","kind":"url","path":"https://example.org/project"}
]
```

每项的 id 在项目内唯一，使用1–80位字母、数字、连字符或下划线；kind 为 local/server/url，path 必填。label 和 ssh_alias 最多200字符，path 最多4096字符。服务器目录须为绝对路径，网页仅允许不含账号密码的 HTTP/HTTPS 链接。服务器条目的 SSH 别名留空时使用项目默认值；其他类型不填写 SSH 别名。本地相对路径以 workspace_root 为基准，保存时不改写为解析后的路径。

更新项目时省略 addresses 会保留原列表；提供数组会整体替换，空数组清空附加地址，主地址不受影响。修改单个地址前应读取整个列表并保留其他项及稳定 ID。附加地址导航 ID 为 `project:<项目ID>:address:<地址ID>`，仅已登记本地地址可经目录打开接口访问，网页链接由浏览器打开。旧项目无须迁移即可读取；写入过多地址后，应使用1.1版及以上程序管理，旧版本保存项目可能丢失新增字段。

可选 `desktop_data.json` 顶层最小形态：

```json
{
  "updated_at":"2026-11-23T10:00:00+08:00",
  "projects":[{"id":"rnaseq","name":"RNA-seq 质控","summary":"检查重复一致性","status":"等待复核","current_version":"v1","scope":"演示数据","todo":"检查异常样本","local":"results/rnaseq","remote":"","counts":{"exploratory":1}}],
  "bundles":[{
    "id":"qc-report","project_id":"rnaseq","name":"样本质量报告",
    "category":"exploratory","current_version":"v1","scope":"演示数据，不代表真实分析结论","todo":"检查异常样本",
    "file_count":1,"review_status":"reviewed","reviewed_at":"2026-11-23T10:00:00+08:00",
    "evidence":["results/rnaseq/README.md"],"locations":[],"remote":[]
  }]
}
```

完整可运行示例见 `examples/create_demo.py`。项目字段缺省值由 repository 填充，但结果包应提供示例中全部字段。没有结果包时提供空数组。

| 分类 | 含义 |
|---|---|
| `paper` | 在列明适用范围内已确认可以用于文章的结果 |
| `exploratory` | 探索性分析及仍需核验的假说 |
| `intermediate` | 中间产物、恢复或复现所需文件 |
| `logs` | 运行、质控及审计日志 |
| `support` | 输入、脚本和参考资料 |
| `pending` | 尚未判定或需要重新复核 |

`review_status="reviewed"` 只表示适配器/登记者确认了该包当前的用途；它不会把 exploratory 自动改为 paper。其他 review_status 值在页面以待复核显示。应在 `scope`、`evidence` 和 `reviewed_at` 交代判断范围、来源与时间。

结果包 `locations` 每项至少需要 `id,path,host,project_id,availability`。host 是 `local` 或 `server`；本地路径应为已解析的绝对路径。availability 可用 `available_at_scan`、`observed_metadata`、`unverified`、`not_observed`。本地打开按钮还需要 ID 能在文件索引中解析；没有索引时可使用已有项目根目录的 `project:<project_id>:local`，或省略 locations 并通过项目详情打开目录。`remote` 是远程路径字符串数组，用于是否补充项目服务器根目录的判断。

## 会话

`desktop_threads.json` 是可选会话目录快照：`{"threads":[{"id":"UUID","title":"名称"}]}`。不会自动查询 Codex，也不代表实时运行状态。

`desktop_project_links.json` 存储显式关联：

```json
{"revision":1,"projects":{"rnaseq":[{"id":"00000000-0000-4000-8000-000000000001","title":"示例会话","provider":"codex"}]}}
```

示例 UUID 为虚构值。使用关联 API 修改此文件；revision 在整个关联文件范围内递增。

## 卡片、文件夹与计划本

`desktop_board_state.json` 包含 `revision,cards,todos,saved_at`。首次没有保存文件时，从活跃项目和会话目录生成待安排卡片。

卡片字段：

| 字段 | 约定 |
|---|---|
| `id` | 唯一，1–100 位字母、数字、连字符或下划线 |
| `type` | `project`、`thread`、`directory`、`folder` |
| `target` | 项目 ID、会话 UUID、本地绝对目录；文件夹为空字符串 |
| `title` | 非空，最多 12000 字符 |
| `folder` | 已存在文件夹卡片 ID；直接显示时为空；文件夹不能嵌套 |
| `order` | 可选整数 0–1000000，仅用于文件夹内排序；较小值靠前，未设置的排在后面，同值按 cards 数组顺序。旧文件不需要迁移 |
| `zone` | `inbox` 待安排；`do` 右上；`plan` 左上；`delegate` 右下；`later` 左下 |
| `x,y` | 0–1 的有限数值，表示所在象限内部的归一化位置，y 增大向下 |

最多 1000 张卡片。项目 target 必须已经登记，包括归档项目。目录卡片只支持绝对路径，实际打开时还会检查目录存在。

待办基础字段：`id`（唯一字符串）、`title`（1–1000 字符）、`date`（有效 YYYY-MM-DD）、`card`（存在的卡片 ID 或空字符串）、`done`（布尔值）。最多3000条。1.2新增 project_id、start_date、status、progress、dependencies、milestone、repeat、notes；日期按浏览器本机日历解释，没有时刻或提醒调度，重复任务在完成当前实例时生成下一次。完整规则见 [API第7节](API.md#7-任务甘特与卡片--12)。

旧文件仅读取时不会改写；返回值在内存中补默认字段，并从项目卡片推导project_id。保存后新增字段与旧字段共存，旧日历继续识别date/done。移除卡片保留project_id。next_instance_id和previous_instance_id由系统用于重复任务去重，客户端不能手工修改。

项目、会话关联、桌面三个JSON文件可含内部 `_history` 数组，每个存储保留最近100条变更，与数据同时原子写入。普通API响应不暴露该字段；专用history接口读取。不要用旧程序覆盖1.2工作区，否则可能丢失新字段与历史。迁移包保留历史，但不包含研究文件。

项目1.2来源字段为source/observed_at/reviewed_at，运行字段run_status/run_source/run_observed_at与研究阶段research_stage、采用状态adoption_status相互独立。updated_at由服务维护。result_versions登记多个分析子模块的版本（id/name/version/category/status/scope/todo/path/source/observed_at/reviewed_at），其中todo记录该结果版本的待完成事项；不要求所有模块采用同一版本。写入规则见 [完整接口](API.md#10-项目来源状态与结果版本)。

## 可选 SQLite 文件索引

没有索引不影响日程、项目和会话管理。接入时提供 `desktop_active.json`：

```json
{"db":"files.sqlite"}
```

数据库必须位于 data 目录，文件名不能包含目录，扩展名为 `.sqlite`。服务以只读连接查询 `files` 表，不负责创建索引。

查询依赖的列：`id,path,project_id,category,host,bundle_id,object_type,current_version`。详情还读取 `availability,version_state,basis,scope,todo,evidence,observed_at,reviewed_at`，建议全部定义为 TEXT，未知值使用空字符串。

```sql
CREATE TABLE files (
  id TEXT PRIMARY KEY, path TEXT NOT NULL, project_id TEXT,
  category TEXT, host TEXT, bundle_id TEXT, object_type TEXT,
  current_version TEXT, availability TEXT, version_state TEXT,
  basis TEXT, scope TEXT, todo TEXT, evidence TEXT,
  observed_at TEXT, reviewed_at TEXT
);
CREATE INDEX files_project ON files(project_id);
CREATE INDEX files_bundle ON files(bundle_id);
```

`object_type` 为 `file` 或 `directory`；本地 path 使用绝对路径。支持的可选导出文件为 `tables/unified_file_inventory.tsv` 和 `UNIFIED_RESULTS.md`。

适配器更新时先完整写入新 SQLite 文件和 JSON，再原子替换指针，避免读到半成品。不要覆盖正在使用的数据库文件。`updated_at` 用于页面每 60 秒发现新摘要；人工项目变化也会被页面检查。桌面状态没有跨浏览器实时推送，冲突后需要刷新。
