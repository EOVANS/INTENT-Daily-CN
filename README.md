# INTENT Daily CN

**每日新闻**的中文 RSS 订阅源：每天北京时间 **07:35** 自动抓取整理，GitHub Actions 全自动构建。

- **RSS 地址**（每天一条，内含当天全部要闻摘要）：`https://raw.githubusercontent.com/EOVANS/INTENT-Daily-CN/main/docs/feed.xml`
- **Markdown 版**：`https://raw.githubusercontent.com/EOVANS/INTENT-Daily-CN/main/docs/latest.md`
- **月度回顾**：`https://raw.githubusercontent.com/EOVANS/INTENT-Daily-CN/main/docs/monthly/latest.md`

## 内容板块

### 下载阅读器 
**INTETN** 是一个由 Ai 赋能的 RSS 阅读器

![Static Badge](https://img.shields.io/badge/build-Ai%20Powered%20RSS%20Reader-brightgreen?style=flat&logo=android&label=INTENT&labelColor=%23E02B2B&color=%23110F00&link=https%3A%2F%2Fintentread.pages.dev%2F)

### 每日更新（07:35）

| 板块 | 来源 | 时间窗 | 条数 |
| --- | --- | --- | --- |
| 一、国际要闻 | BBC News / CNN / VOA / NBC | 过去约 24 小时 | 最多 8 条，按重要性降序 |
| 二、AI 研究动态 | OpenAI Research / Google DeepMind / Anthropic / arXiv cs.AI | 过去约 21 天 | 最多 5 条 |

RSS 每期只出一条：标题为「每日新闻 · 日期｜N 条要闻」，正文里按序号依次给出标题、配图、摘要、来源与原文链接。

国际要闻板块严格限定四家英文媒体（CNN 的 feed 不带日期，按最新稿计分；VOA 官方接口常被拦截，走 Google News 站内检索兜底，仍只取 voanews.com 的文章）。

### 月度回顾（每月 1 号）

每月 1 号生成「上月重大事件回顾」，共 **10 件**，覆盖国际政治、科学与文明突破（诺贝尔奖 / 菲尔兹奖等）、航天突破、娱乐突破四个领域，按实际命中情况取舍，不强行凑满。同一事件多源报道会去重，节目单 / 播客 / 通讯类噪声条目会被过滤。

## 处理流程

1. 抓取各源 RSS（每源多组备用 feed，主 feed 失效自动切换）。
2. 时间窗过滤（国际要闻 26 小时留缓冲、AI 研究 504 小时、月度 32 天）。
3. 按「标题指纹 + 链接」双重去重。
4. 关键词权重 + 时效性 + 是否带图 计算重要性得分，降序排列。
5. 单源条数上限，并对「有候选却未进榜」的来源做覆盖保底，保证 BBC / CNN / VOA / NBC 都有露出。
6. 标题与摘要译为中文（clients5 → gtx → MyMemory 三级回退，全失败则保留英文，流水线不中断）。
7. 打包成单条 RSS item（HTML 描述，含配图）+ Markdown 摘要 + HTML 预览页 + JSON 数据。

## 产物

```
docs/feed.xml              # RSS 订阅源（每天一条，主产物）
docs/latest.md             # 最新一期 Markdown
docs/latest.json           # 结构化数据（含得分、原文标题、配图）
docs/status.json           # 最近一次构建的诊断信息（每源条数、翻译成功率、错误堆栈）
docs/daily/YYYY-MM-DD.md   # 按日归档（Markdown）
docs/monthly/YYYY-MM.md    # 月度重大事件回顾（Markdown）
docs/monthly/latest.md     # 最新一期月度回顾
archive/YYYY-MM-DD.xml     # 按日归档（RSS）
```

## 订阅方式

- **Feedly / Inoreader / NetNewsWire** 等阅读器：直接粘贴 RSS 地址。
- 若想用自定义域名，在 Settings → Pages 选择 `main` 分支 `docs` 目录即可。

## 本地运行

```bash
python3 scripts/pipeline.py                     # 需要能访问外网的网络环境
NO_TRANSLATE=1 python3 scripts/pipeline.py      # 跳过翻译，保留英文标题
python3 scripts/monthly.py                      # 生成本月回顾
```

可调环境变量：`NEWS_WINDOW_HOURS`、`AI_WINDOW_HOURS`、`NEWS_TOP_N`、`AI_TOP_N`、`MONTH_WINDOW_DAYS`、`MONTH_TOP_N`、`MONTH_CAT_CAP`、`NO_TRANSLATE`。

## 定时任务

- `.github/workflows/daily.yml`：`35 23 * * *`（UTC）= 北京时间次日 07:35，支持 `workflow_dispatch`。
- `.github/workflows/monthly.yml`：`35 23 28-31 * *`（UTC），脚本内用 `TZ=Asia/Shanghai date +%d` 闸门，只在每月 1 号真正构建。

两个工作流都在 `scripts/**` 变更时触发一次重建，便于调试。

## 目录结构

```
.
├── .github/workflows/daily.yml
├── .github/workflows/monthly.yml
├── scripts/
│   ├── build_feed.py
│   ├── pipeline.py
│   └── monthly.py
├── docs/
└── archive/
```

> 生成文件由 Actions 自动提交，请勿手工编辑 `docs/`、`archive/`。
