# 按需导入计算状态

工作台将研究阶段、计算运行状态与结果采用情况分别记录。运行成功只说明某次计算的状态，不能自动把结果升级为可用于文章。

`examples/import_run_snapshot.py` 接收一份本地 JSON 快照。它不登录服务器、不扫描进程、不执行命令，也不读取大型分析数据。可以让现有流程在检查运行状态后生成快照，再按需复制到本地导入。`source` 应写实际观察来源，例如调度系统导出的记录、具体日志或人工检查说明。

## 快照格式

```json
{
  "schema_version": 1,
  "project_id": "rnaseq",
  "run_status": "succeeded",
  "observed_at": "2026-11-25T16:00:00+08:00",
  "source": "run-123/status.json; exported by the analysis workflow",
  "run_id": "123"
}
```

`project_id` 必须对应已登记项目；状态为 `unknown`、`queued`、`running`、`succeeded`、`failed`、`cancelled` 之一。时间必须包含时区，填写实际观察时刻，不能用导入时刻代替。`run_id` 可省略。快照最多 64 KiB。

## 预览和导入

```bash
python examples/import_run_snapshot.py --config ../ai4s-workspace/workspace.json --snapshot run-status.json
```

默认只展示前后差异与 `expected_revision`。检查项目和来源后，将输出版本号填入下一条命令：

```bash
python examples/import_run_snapshot.py --config ../ai4s-workspace/workspace.json --snapshot run-status.json --apply --expected-revision 3
```

版本号 `3` 仅为示例。项目登记已发生变化时会拒绝写入，需重新预览。比现有观察更旧的快照、同一时刻相互矛盾的状态、没有时区或明显来自未来的时间均会拒绝。相同快照重复导入不产生新的修改。

只更新 `run_status`、`run_observed_at`、`run_source`；研究概述、研究阶段、结果版本、结果采用情况和日程保持原值。导入通过与 MCP 相同的服务操作写入，因此进入项目变更历史。核心不会默认定期运行这个脚本。

## 常见来源的解释

- 调度器记录应带实际作业 ID；队列中找不到作业不等于运行成功。
- 普通命令行分析应依据明确的退出状态或完成记录；日志文件存在不等于成功。
- 无法访问服务器、没有完成记录或来源不清楚时，登记 `unknown`，保留原因与来源。
- 一个项目可能有多次运行。此快照只表示项目当前关注的那次运行；历史运行的参数、结果和复核说明应分别登记到结果版本中。
