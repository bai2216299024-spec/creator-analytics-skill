# Creator Analytics Skill

用于在 Codex/Agent 环境中一键采集并复盘小红书、抖音创作者账号前一天发布的图文或视频数据，并根据表现生成下一期选题和文案思路。

## 包含内容

- `creator-analytics/SKILL.md`：skill 使用说明和操作流程。
- `creator-analytics/scripts/`：采集、报告生成、一键运行和 Windows 每日任务安装脚本。
- `creator-analytics/references/`：平台页面和排错说明。
- `creator-analytics/agents/openai.yaml`：Agent UI 元数据。

## 隐私边界

仓库不包含登录态、Cookie、浏览器 Profile、历史报告或个人运行日志。运行时数据默认会写入 `creator-analytics/data/`，该目录已通过 `.gitignore` 排除敏感文件。

如需在其他机器或其他 Agent 使用，建议通过 `--data-dir` 指定独立运行目录，并在目标环境中重新登录平台账号。
