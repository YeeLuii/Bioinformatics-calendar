# 自动部署与环境兼容

部署需要 **Python >=3.9,<4.0** 和现代浏览器。程序只使用标准库，不需要 pip 包、数据库服务或前端构建。脚本优先复用已有环境，不下载 Python、不默认创建虚拟环境，也不修改 PATH、Shell 配置或系统执行策略。版本范围表示程序的兼容要求；实际测试的平台和版本以仓库 CI 结果为准。

## 运行入口

下载或克隆仓库后，在仓库目录执行：

Windows（兼容 Windows PowerShell 5.1 和 PowerShell 7）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 --mcp required
```

这里的 ExecutionPolicy 只对本次 PowerShell 进程生效。

macOS / Linux：

```sh
sh ./deploy.sh --mcp required
```

只使用网页、不配置 Codex 时，将 `--mcp required` 改为 `--mcp off`。默认值 `auto` 在没有 Codex CLI 时仍启动网页，并在输出中标记 `cli_unavailable`，不能将这种情况报告为 MCP 已接入。

已知 Python 位置时，可以直接运行：

```sh
python -B deploy.py --mcp required --no-open
```

启动器依次检查当前激活的虚拟环境、仓库已有的 .venv、PATH 上的 Python；Windows 还尝试 `py -3`。仅接受版本范围内且可导入 sqlite3、ssl、http.server、ctypes 的解释器。核心脚本还执行一次内存 SQLite 查询。安装在其他位置而未加入 PATH 的解释器，可用其完整路径运行 deploy.py。没有兼容解释器时停止并说明原因，不强制安装某个小版本。

## 固定部署步骤

1. 检查解释器与标准库。
2. 读取指定工作区；默认复用迁移包中的 workspace.json，否则使用仓库同级 ai4s-workspace。目标为空时创建工作区，非空且没有配置时停止。
3. 启动短暂的 MCP 自检进程，完成初始化、与本版契约逐项匹配的工具发现和工作区读取，然后退出。
4. 按选项注册 Codex MCP；配置不符合要求时停止。
5. 复用同一程序、同一数据目录的服务，或从工作区配置的端口开始检查接下来 100 个端口，选取空闲端口启动服务。不会停止占用端口的其他程序。
6. 验证 HTTP 返回的程序、工作区和部署实例标识，保存部署记录，输出访问地址；默认打开浏览器。

重新执行会保留项目、日程、会话关联及工作区设置，不会自动同步研究资料。更新程序后需要 `--restart` 才能加载新代码。

## 参数、输出与启停

| 参数 | 用途 |
|---|---|
| `start` / `status` / `stop` | 默认启动；也可查询或停止本脚本管理的服务 |
| `--workspace PATH` | 指定工作区目录，可初始化空目录 |
| `--config PATH` | 指定已有 workspace.json，与 --workspace 互斥 |
| `--port N` | 首选端口；占用时顺次检查其他端口 |
| `--mcp required` | 必须完成 Codex 注册，否则部署失败 |
| `--mcp auto` | 默认；CLI 缺失时只部署网页并报告未注册 |
| `--mcp off` | 不访问 Codex 配置 |
| `--codex PATH` | 指定 Codex CLI；Windows npm 启动器解析到 Node 入口后执行 |
| `--replace-mcp` | 明确替换指向其他位置的同名 ai4s 项；其他 MCP 项仍保留 |
| `--restart` | 停止当前部署记录对应的服务，再启动 |
| `--no-open` | 不自动打开浏览器，适合 Agent 或无桌面环境 |

```sh
python -B deploy.py status --workspace ../ai4s-workspace
python -B deploy.py stop --workspace ../ai4s-workspace
python -B deploy.py --workspace ../ai4s-workspace --restart --mcp required
```

退出码 0 表示命令成功，1 表示部署检查或运行失败，2 表示参数错误。成功输出为 JSON；失败的 JSON 写入 stderr。启动结果包含 status、url、workspace、environment、mcp_tools、mcp_registration 和 source_sync。status 的 running / not_running 只表示网页服务；MCP 在客户端中按需独立启动。

运行记录写入工作区 `data/.deployment/state.json`，服务日志为同目录 `server.log`（实际 data 路径以 workspace.json 为准）。实际端口保存在部署记录，不覆盖用户的首选端口。该目录不进入迁移包。

停止前核对当前服务的数据目录、程序目录及实例标识，拒绝停止不属于记录的服务；资料刷新运行期间也拒绝停止。手动启动的旧服务不具有部署标识，仍需在其原终端中退出。脚本不按端口或进程名批量结束程序。

## Codex 配置保护

注册必须通过官方 `codex mcp add ai4s -- ...`，不拼接或追加 TOML 文本。独立 Codex CLI 是此步骤的依赖；仅安装桌面客户端不代表 CLI 一定已在 PATH 上。

脚本先检查现有文件的 UTF-8 编码与换行，拒绝 BOM、孤立 CR 或 CRCRLF，再由 `codex mcp list --json` 验证完整配置。Python 3.11 及以上还用标准库 tomllib 检查。现有配置已经损坏时停止，不擅自“修复”其他设置。

写入前保存原始字节到 Codex 配置目录中的 `config.toml.ai4s-backup-<随机标识>`。写入后再次验证格式、注册路径及其他 MCP 项。CLI 失败或验证失败时恢复原字节；检测到其他程序同时改动配置时停止自动恢复，保留备份供核对。备份可能含私人配置，应留在本机，不提交到 Git。

同名项完全一致时不重写；指向其他工作区时默认停止。成功注册后可能需要重载 Codex 才会发现工具。不要为了绕过脚本失败而让 Agent 手工修改 config.toml。

这不是操作系统级事务：注册后若网页启动失败，已通过检查的 MCP 配置仍然保留，stdio MCP 可以独立使用。启动器不保证解释器或 Codex 自身没有缺陷；失败时应依据输出处理原因。

## 给 Agent 的部署约定

只运行对应平台的入口脚本，并根据退出码和 JSON 报告结果。不要临时编写安装逻辑，不自动下载运行时，不手工写 Codex 配置。需要变更同名 MCP 的目标时，应先说明旧配置对应的工作区，再按用户授权使用 --replace-mcp。

部署成功后询问：“是否要分析当前会话和项目的分析进度并同步到工作台？” 同步是另一个明确授权的操作，范围及调用顺序见 [Agent 接口](../AGENT_API.md)。启动脚本不扫描会话、不导入分析目录，也不推断科研任务完成状态。

## 可选技能与近义词调用

对用户的名称为 **ai4s项目桌面**，底层 MCP 注册名为 `ai4s`。注册后可通过以下只读命令检查：

```sh
codex mcp get ai4s --json
```

应确认 enabled 为 true、transport.type 为 stdio，并核对解释器、desktop_mcp.py 和 --config 指向的工作区。不要公开整份本机配置输出。之后重载客户端，让 Agent 调用 `workspace_status`、`projects_list` 验证真实连接；不能只凭配置记录判断工具已经可用。

仓库提供可选的 [ai4s 技能](https://github.com/YeeLuii/Bioinformatics-calendar/tree/main/skills/ai4s)，显示名为“ai4s项目桌面”，支持显式 `$ai4s` 和“项目工作台、项目桌面、科研日程管理、AI4S工作台、ai4s”等自然语言叫法。自然语言选择取决于上下文；显式调用更明确。

安装时将仓库的整个 `skills/ai4s` 目录复制到 Codex 的技能目录：

- 默认位置：用户目录下的 `.codex/skills/ai4s/`。
- 如果已经设置 CODEX_HOME，则使用其下面的 `skills/ai4s/`，不为安装技能改动该环境变量。
- 保留目录内的 `SKILL.md` 和 `agents/openai.yaml`。若目标已存在，先保留现有技能及个人工作区绑定，再比较更新；不要直接覆盖本机定制内容。
- 重载客户端后，在技能列表查找“ai4s项目桌面”，或输入 `$ai4s`。

通用技能不包含电脑路径、研究项目或真实会话信息，运行时从已注册 MCP 查询工作区。安装技能不会注册 MCP；部署脚本也不会自动复制技能。没有技能时，Agent 仍可使用 MCP 工具管理项目。

例如：“请用科研日程管理整理本周待办，并保留其他安排。”1.2 版的项目、任务、卡片、历史与诊断操作均使用公开契约；旧客户端需重载后发现新增 MCP 工具，具体参数见 [完整接口说明](API.md)。

## 从 1.1 升级

先备份个人工作区，再更新应用代码并通过相同的 `--config` 或 `--workspace` 加 `--restart` 启动。旧日期待办会在读取时补齐任务字段，首次保存才写入新格式；旧卡片位置、项目 ID 和会话关联保持原值。不要在保存新版任务后用 1.1 程序编辑同一个工作区，因为旧版界面不了解任务依赖、重复规则和直接项目关联。

回退时应使用升级前的完整工作区副本及对应旧程序；如果升级后已经新增安排，先导出并核对这些变化，不能直接以旧备份覆盖。新版启动后重载 MCP 客户端，避免旧进程继续使用旧契约。升级不需要安装新的 pip/npm 依赖，也不会停止科研计算进程。
