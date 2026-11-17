#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月度重大事件回顾：每月 1 号生成上个月的 10 件大事

数据：四家英文媒体（BBC / CNN / VOA / NBC）+ 本月本地归档
领域：国际政治 / 科学文明突破 / 航天 / 娱乐（按实际命中情况取舍，不强行凑满）
产物：docs/monthly/YYYY-MM.md、docs/monthly/latest.md、docs/monthly/YYYY-MM.json
"""

import glob
import importlib.util
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta

spec = importlib.util.spec_from_file_location("bf", "scripts/build_feed.py")
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)

WINDOW_DAYS = int(os.environ.get("MONTH_WINDOW_DAYS", "32"))
TOP_N = int(os.environ.get("MONTH_TOP_N", "10"))
CAT_CAP = int(os.environ.get("MONTH_CAT_CAP", "4"))

DOMAINS = ["bbc.co.uk", "cnn.com", "voanews.com", "nbcnews.com"]
DOMAIN_NAME = {"bbc.co.uk": "BBC News", "cnn.com": "CNN",
               "voanews.com": "VOA", "nbcnews.com": "NBC"}

CATEGORIES = {
    "国际政治": {
        "terms": ["election", "parliament", "president", "prime minister", "summit",
                  "sanctions", "ceasefire", "war", "treaty", "referendum", "impeach",
                  "coalition", "coup", "diplomatic", "midterm", "congress"],
        "query": "election OR parliament OR president OR summit OR sanctions OR ceasefire OR treaty",
        "weight": 1.0,
    },
    "科学与文明突破": {
        "terms": ["nobel", "fields medal", "breakthrough", "discovery", "scientists",
                  "researchers", "study finds", "cure", "vaccine", "physics", "chemistry",
                  "medicine", "prize", "ancient", "archaeolog"],
        "query": "Nobel Prize OR Fields Medal OR breakthrough OR discovery OR scientists OR researchers",
        "weight": 1.0,
    },
    "航天": {
        "terms": ["nasa", "spacex", "starship", "rocket", "satellite", "telescope",
                  "moon", "mars", "orbit", "launch", "space station", "astronaut",
                  "esa", "asteroid", "jwst"],
        "query": "NASA OR SpaceX OR Starship OR satellite OR telescope OR moon OR orbit",
        "weight": 1.0,
    },
    "娱乐": {
        "terms": ["oscar", "academy award", "grammy", "emmy", "golden globe", "box office",
                  "album", "film", "movie", "actor", "actress", "director", "billboard",
                  "concert", "festival", "netflix"],
        "query": "Oscar OR Academy Awards OR Grammy OR Emmy OR box office OR album",
        "weight": 0.95,
    },
}

GNEWS = ("https://news.google.com/rss/search?q=site:{domain}+({terms})+when:{days}d"
         "&hl=en-US&gl=US&ceid=US:en")

IMPACT_WORDS = [("dead", 4), ("killed", 4), ("first", 3), ("record", 3), ("historic", 3),
                ("landmark", 3), ("wins", 3), ("agreement", 3), ("collapse", 3),
                ("billion", 2), ("major", 2), ("unprecedented", 3), ("warns", 2)]


def log(msg):
    print("[monthly] %s" % msg, file=sys.stderr)


def classify(title, summary):
    text = (title + " " + (summary or "")).lower()
    best, best_hits = None, 0
    for cat, cfg in CATEGORIES.items():
        hits = sum(1 for t in cfg["terms"] if t in text)
        if hits > best_hits:
            best, best_hits = cat, hits
    return best if best_hits else None


def score(item, cat, now):
    text = (item["title"] + " " + (item["summary"] or "")).lower()
    base = CATEGORIES[cat]["weight"] * 5
    hits = sum(w for word, w in IMPACT_WORDS if word in text)
    if item["published"]:
        age = (now - item["published"]).days
        recency = max(0.0, 3.0 - age / 10.0)
    else:
        recency = 0.5
    tier = bf.SRC_TIER.get(item["source"], 0.9)
    return (base + hits + recency) * tier


JUNK_PATTERNS = ["bbc parliament", "questions,", "podcast", "newsletter", "live updates",
                 "episode", "watch:", "listen:", "how to watch", "bbc world service"]


def clean_title(title):
    """去掉 Google News 附加的来源后缀，例如 '... - BBC News'"""
    return re.sub(r"\s*[-–|]\s*(BBC News|BBC|CNN News|CNN|NBC News|NBC|VOA News|VOA)\s*$",
                  "", title.strip(), flags=re.I).strip()


def is_junk(title):
    t = title.lower()
    return any(p in t for p in JUNK_PATTERNS)


def clean_summary(summary, title):
    """Google News 的 description 常是「标题 + 来源」，去掉重复部分"""
    s = (summary or "").strip()
    if s.lower().startswith(title.strip().lower()[:40]):
        s = s[len(title.strip()):].strip()
    s = re.sub(r"\s*(BBC News|CNN|NBC News|VOA News|BBC|VOA)\s*$", "", s, flags=re.I)
    return s if len(s) >= 30 else ""


def tokens(title):
    stop = {"the", "and", "for", "with", "from", "that", "this", "after", "says", "said",
            "amid", "into", "over", "its", "has", "have", "will", "not", "are", "was"}
    return {w for w in re.findall(r"[a-z]{3,}", title.lower()) if w not in stop}


def similar(a, b):
    ta, tb = tokens(clean_title(a)), tokens(clean_title(b))
    if not ta or not tb:
        return False
    return len(ta & tb) / float(min(len(ta), len(tb))) >= 0.5


def load_archives(now, days):
    items = []
    cutoff = now - timedelta(days=days)
    for path in glob.glob("archive/*.xml"):
        try:
            day = datetime.strptime(os.path.basename(path)[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if day.date() < cutoff.date():
            continue
        with open(path, "r", encoding="utf-8") as fh:
            items += bf.parse_feed(fh.read(), "归档")
    return items


def main():
    now = datetime.now(bf.CST)
    target = now.replace(day=1) - timedelta(days=1)
    month_key = target.strftime("%Y-%m")
    log("review month %s" % month_key)

    pool = load_archives(now, WINDOW_DAYS)
    log("archive items: %d" % len(pool))

    cutoff = now - timedelta(days=WINDOW_DAYS)
    for cat, cfg in CATEGORIES.items():
        for domain in DOMAINS:
            url = GNEWS.format(domain=domain,
                               terms=urllib.parse.quote_plus(cfg["query"]),
                               days=WINDOW_DAYS)
            got = bf.parse_feed(bf.fetch(url), DOMAIN_NAME[domain])
            got = [i for i in got if i["published"] and i["published"] >= cutoff]
            log("%s / %s -> %d" % (cat, domain, len(got)))
            pool += got

    cands = []
    seen_titles, seen_urls = [], set()
    for item in pool:
        if not item["published"] or item["published"] < cutoff:
            continue
        if item["link"].split("?")[0] in seen_urls:
            continue
        cat = classify(item["title"], item["summary"])
        if not cat or is_junk(item["title"]):
            continue
        if any(similar(item["title"], t) for t in seen_titles):
            continue
        seen_urls.add(item["link"].split("?")[0])
        seen_titles.append(item["title"])
        item["clean_title"] = clean_title(item["title"])
        item["summary"] = clean_summary(item["summary"], item["clean_title"])
        item["category"] = cat
        item["score"] = score(item, cat, now)
        cands.append(item)

    cands.sort(key=lambda x: x["score"], reverse=True)

    chosen, per_cat = [], {}
    for item in cands:
        if per_cat.get(item["category"], 0) >= CAT_CAP:
            continue
        chosen.append(item)
        per_cat[item["category"]] = per_cat.get(item["category"], 0) + 1
        if len(chosen) >= TOP_N:
            break

    if not chosen:
        log("FATAL: no candidates")
        return 2

    for item in chosen:
        item["title_zh"] = bf.translate(item.get("clean_title") or item["title"])
        item["summary_zh"] = bf.translate(item["summary"][:200]) if item["summary"] else ""

    os.makedirs("docs/monthly", exist_ok=True)
    md = build_md(chosen, now, month_key, len(cands))
    for path in ("docs/monthly/%s.md" % month_key, "docs/monthly/latest.md"):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md)
    with open("docs/monthly/%s.json" % month_key, "w", encoding="utf-8") as fh:
        json.dump({"month": month_key, "generated_at": now.isoformat(), "total": len(chosen),
                   "candidates": len(cands), "by_category": per_cat,
                   "items": [{"rank": i + 1, "category": it["category"], "source": it["source"],
                              "title_zh": it.get("title_zh"), "title_en": it["title"],
                              "summary_zh": it.get("summary_zh"), "url": it["link"],
                              "published": it["published"].isoformat(),
                              "score": round(it["score"], 2)}
                             for i, it in enumerate(chosen)]},
                  fh, ensure_ascii=False, indent=2)
    log("done: %d events" % len(chosen))
    return 0


def build_md(items, now, month_key, cand_total):
    lines = ["# %s 月度重大事件回顾" % month_key, "",
             "> 覆盖：过去约一个月（含本月本地归档）｜生成：%s｜来源：BBC News / CNN / VOA / NBC"
             % now.strftime("%Y-%m-%d %H:%M"),
             "> 领域：国际政治 · 科学文明突破 · 航天 · 娱乐（按实际命中情况取舍，不强行凑满）", "",
             "## 一、概览", "", "| # | 领域 | 事件 |", "| --- | --- | --- |"]
    for i, it in enumerate(items, 1):
        lines.append("| %d | %s | %s |" % (i, it["category"],
                                          (it.get("title_zh") or it["title"])[:46]))

    lines += ["", "## 二、逐条回顾", ""]
    for i, it in enumerate(items, 1):
        lines += ["### %d. %s" % (i, it.get("title_zh") or it["title"]), "",
                  "**领域**：%s　|　**来源**：%s　|　**时间**：%s"
                  % (it["category"], it["source"],
                     it["published"].astimezone(bf.CST).strftime("%Y-%m-%d")), ""]
        if it["summary"]:
            lines += [it.get("summary_zh") or it["summary"], ""]
        lines += ["- 原文标题：%s" % it["title"],
                  "- 原文链接：<%s>" % it["link"], ""]

    lines += ["---", "", "### 统计", "", "- 候选事件：%d 条" % cand_total,
              "- 最终入选：%d 件" % len(items), ""]
    for cat in CATEGORIES:
        n = sum(1 for it in items if it["category"] == cat)
        if n:
            lines.append("- %s：%d 件" % (cat, n))
    lines += ["", "> 由 GitHub Actions 每月 1 号自动生成，请勿手工编辑。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
