# scripts

- `build_feed.py`：核心库。抓取 feed、打分、翻译、生成 XML / Markdown / JSON。
- `pipeline.py`：线上实际入口（daily.yml 调用）。包装 `build_feed`，提供：
  - 可观测 fetch（每个 feed 的 ok / bytes / entries 写入 `docs/status.json`）
  - 多供应商中文翻译（clients5 → gtx → mymemory，按成功率自动切换）
  - 自定义收录：直连 feed → 窗口内不足补 Google News → 仍不足用无日期条目（按最新稿计分）
  - 覆盖保底：有候选但没进榜的来源，用它的最佳一条替换超额来源里最弱的一条，且输出恰好 N 条
- `monthly.py`：每月 1 号生成「月度重大事件回顾」（10 件，按领域取舍，含去重与噪声过滤）。
- `diagnose.py`：一次性探测脚本，保留作参考，不被工作流调用。

本地自测（不联网部分）：

```bash
python -m py_compile scripts/*.py
```
