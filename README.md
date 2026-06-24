# Creator Analytics — 创作者全链路复盘

一键采集小红书、抖音、微信公众号的昨日内容数据，基于历史基准诊断好差原因与分发异常，并生成下一期选题和内容方向。

## 使用场景

- **每日复盘**：统计昨日三平台发布内容的各项指标，对比历史表现
- **诊断分析**：分析为什么数据好或差，是否疑似限流或分发异常
- **选题推荐**：基于最佳表现内容的底层逻辑，生成不重复的新选题和文案方向
- **趋势追踪**：7 日滚动趋势、内容结构诊断、选题疲劳预警

## 前置条件

- Python 3.9+
- Playwright（浏览器自动化采集）
- Pillow（图片处理）
- 各平台创作者账号的扫码登录（首次需 `--headed` 模式）

## 快速开始

```bash
# 安装依赖
pip install playwright pillow
playwright install chromium

# 校验安装
python scripts/validate_skill.py

# 首次采集（会打开浏览器供扫码登录）
python scripts/one_click_review.py --headed

# 日常采集
python scripts/one_click_review.py
```

## 目录结构

```
creator-analytics/
├── SKILL.md                # AI 执行规范（工作流、规则、反例）
├── README.md               # 本文件 — 面向人的介绍
├── CHANGELOG.md            # 版本变更日志
├── test-prompts.json       # 测试提示词
├── scripts/                # 采集、分析、报告生成脚本
│   ├── one_click_review.py # 主入口
│   ├── scrape_xhs.py       # 小红书采集
│   ├── scrape_douyin.py    # 抖音采集
│   ├── scrape_wechat.py    # 公众号采集
│   ├── analysis_engine.py  # 分析引擎
│   ├── generate_report.py  # 报告生成
│   ├── comments_utils.py   # 评论处理
│   ├── history_store.py    # 历史数据存储
│   ├── setup_zones.py      # 同步到创作专区
│   ├── validate_skill.py   # 技能校验
│   └── run_all.py          # 全流程执行
├── config/                 # 配置文件
│   ├── benchmark_accounts.example.json
│   ├── self_accounts.example.json
│   └── wechat_api.example.json
├── references/             # 参考文档（AI 按需读取）
├── data/                   # 运行时数据（已 gitignore）
├── tests/                  # 单元测试
└── agents/                 # 对外 Agent 配置
```

## 安全注意事项

- **凭证保护**：`config/wechat_api.json`、`config/self_accounts.json` 等包含真实凭证的文件已加入 `.gitignore`，不会随代码分发
- **浏览器登录**：首次使用需扫码登录，登录态保存在本地 `data/cookies/` 和 `data/browser/`
- **采集行为**：采集会启动本地浏览器访问各平台创作者后台，在 headed 模式下会实际打开浏览器窗口
- **高副作用操作**：包括自动写入本地文件、同步到创作专区等，AI 在执行前会先询问用户确认

## 平台支持

| 平台 | 采集方式 | 指标 |
|------|---------|------|
| 小红书 | Playwright 浏览器采集 | 曝光、阅读、点赞、收藏、评论 |
| 抖音 | Playwright 浏览器采集 | 播放、点赞、评论、分享 |
| 微信公众号 | API 优先，浏览器备选 | 阅读、点赞、在看、留言 |

## 相关 Skill

- **douyin-publish**：抖音图文自动发布（发布侧，本 skill 只做分析诊断）
- **meihua-creator-hub**：梅花创作系统统一入口（路由创作请求到各平台专区）
