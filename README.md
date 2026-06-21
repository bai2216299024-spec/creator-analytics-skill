# Creator Analytics Skill

用于在 Codex/Agent 环境中一键采集并复盘小红书、抖音、微信公众号创作者账号前一天发布的图文、视频或文章数据，并根据账号历史表现诊断好差原因、提升动作和下一期成稿思路。

## 包含内容

- `creator-analytics/SKILL.md`：skill 使用说明和操作流程。
- `creator-analytics/scripts/`：三平台采集、历史库、分析引擎、报告生成、一键运行和 Windows 每日任务安装脚本。
- `creator-analytics/references/`：平台页面和排错说明。
- `creator-analytics/config/`：对标账号配置示例。
- `creator-analytics/tests/`：核心分析和历史库测试。
- `creator-analytics/agents/openai.yaml`：Agent UI 元数据。

## 隐私边界

仓库不包含登录态、Cookie、浏览器 Profile、历史库、历史报告或个人运行日志。运行时数据默认会写入 `creator-analytics/data/`，该目录已通过 `.gitignore` 排除敏感文件。

如需在其他机器或其他 Agent 使用，建议通过 `--data-dir` 指定独立运行目录，并在目标环境中重新登录平台账号。

## 每日自动任务

通过 Windows 任务计划程序设置每日自动复盘（默认凌晨 12 点执行）：

```powershell
powershell -ExecutionPolicy Bypass -File creator-analytics\scripts\install_windows_task.ps1 -At 00:00
```

可选参数：

```powershell
powershell -ExecutionPolicy Bypass -File creator-analytics\scripts\install_windows_task.ps1 `
    -TaskName CreatorAnalyticsDailyReview -At 00:00 `
    -PythonExe C:\Path\to\python.exe -DataDir D:\creator-analytics-data
```

任务默认走生产模式（实际采集数据），如仅测试请手动传入 `--dry-run`。
