# scripts

- `build_feed.py`：核心库。抓取 feed、打分、翻译、生成 XML / Markdown / JSON。
- `pipeline.py`：线上实际入口（daily.yml 调用）。包装 `build_feed`，提供：
  - 可观测 fetch（每个 feed 的 ok / bytes / entries 写入 `docs/status.json`）
  - 多供应商中文翻译（clients5 → gtx → mymemory，按成功率自动切换）
  - 自定义收录逻辑：直连 feed → 窗口内不足补 Google News → 仍不足用无日期条目
  - 四源多样性保底：每个来源的最佳一条加权，保证 BBC / CNN / VOA / NBC 都能进榜
- `monthly.py`：每月 1 号生成「本月重大事件回顾」（10 件，按领域取舍）。
- `diagnose.py`：一次性探测脚本，保留作参考，不被工作流调用。

本地自测（不联网部分）：

```bash
python -m py_compile scripts/*.py
```
