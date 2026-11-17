# INTENT Daily CN

每日国际要闻 + AI 研究动态的中文 RSS 订阅源，由 GitHub Actions 每天北京时间 **07:35** 自动构建。

- **RSS 地址**：`https://raw.githubusercontent.com/EOVANS/INTENT-Daily-CN/main/docs/feed.xml`
- **Markdown 版**：`https://raw.githubusercontent.com/EOVANS/INTENT-Daily-CN/main/docs/latest.md`
- **按日归档 Markdown**：`docs/daily/YYYY-MM-DD.md`

## 内容板块

| 板块 | 来源 | 时间窗 | 条数 |
| --- | --- | --- | --- |
| 一、国际要闻 | BBC News / CNN / VOA / NBC | 过去 24 小时 | 最多 8 条，按重要性降序 |
| 二、AI 研究动态 | OpenAI Research / Google DeepMind / Anthropic / arXiv cs.AI | 过去 21 天 | 最多 5 条 |

国际要闻板块严格限定四家英文媒体；AI 板块专注研究与模型发布，不掺入其他新闻源。

## 处理流程

1. 抓取各源 RSS（每源配置多组备用 feed，主 feed 失效自动切到备用；AI 源另有 Google News 兜底）。
2. 时间窗过滤（国际要闻 26 小时留缓冲，AI 研究 504 小时）。
3. 「标题指纹 + 链接」双重去重。
4. 关键词权重 + 时效性 + 是否带配图 计算重要性得分，降序排列。
5. 单源条数上限（国际要闻 4 条、AI 板块 2 条），保证四家媒体都有露出。
6. 标题与摘要译为中文；翻译接口失败时自动回退英文原文，流水线不中断。
7. 输出 RSS 2.0（含 `media:content` 配图）+ Markdown 摘要 + JSON 数据。

## 产物

```
docs/feed.xml              # RSS 订阅源（主产物）
docs/latest.md             # 最新一期 Markdown 摘要
docs/latest.json           # 结构化数据（得分、原文标题、配图、来源统计）
docs/daily/YYYY-MM-DD.md   # 按日归档（Markdown）
archive/YYYY-MM-DD.xml     # 按日归档（RSS）
```

## 订阅方式

- **Feedly / Inoreader / NetNewsWire / Reeder**：直接粘贴上面的 RSS 地址。
- **Obsidian / Notion / 自建聚合**：可抓取 `docs/latest.md` 做每日动态。
- 想要更好看的域名：Settings → Pages，Source 选 `main` 分支 `/docs`，即可用 `https://eovans.github.io/INTENT-Daily-CN/feed.xml` 订阅。

## 本地运行

```bash
python3 scripts/build_feed.py                    # 需要可访问外网的环境
NO_TRANSLATE=1 python3 scripts/build_feed.py     # 跳过翻译，保留英文标题
```

可调环境变量：`NEWS_WINDOW_HOURS`、`AI_WINDOW_HOURS`、`NEWS_TOP_N`、`AI_TOP_N`、`NO_TRANSLATE`。

## 定时任务

`.github/workflows/daily.yml`

- **Cron**：`35 23 * * *`（UTC）= 北京时间次日 **07:35**
- 支持 `workflow_dispatch` 手动触发
- `scripts/**` 或工作流变更 push 时自动重建一次（已用 `github.actor` 判断避免机器人提交造成的循环触发）

## 目录结构

```
.
├── .github/workflows/daily.yml
├── scripts/build_feed.py
├── docs/
└── archive/
```

> `docs/`、`archive/` 由 Actions 自动提交，请勿手工编辑。
