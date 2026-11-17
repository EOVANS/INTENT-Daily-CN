#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INTENT Daily CN 构建器

板块一 国际要闻：BBC News / CNN / VOA / NBC（过去 24h，最多 8 条）
板块二 AI 研究：OpenAI Research / Google DeepMind / Anthropic / arXiv cs.AI（过去 21 天，最多 5 条）
产物：docs/feed.xml、docs/latest.md、docs/daily/YYYY-MM-DD.md、docs/latest.json、archive/YYYY-MM-DD.xml
仅标准库。
"""

import html, json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime

CST = timezone(timedelta(hours=8))
NEWS_WINDOW_H = float(os.environ.get("NEWS_WINDOW_HOURS", "26"))
AI_WINDOW_H = float(os.environ.get("AI_WINDOW_HOURS", "504"))
NEWS_TOP_N = int(os.environ.get("NEWS_TOP_N", "8"))
AI_TOP_N = int(os.environ.get("AI_TOP_N", "5"))
NO_TRANSLATE = os.environ.get("NO_TRANSLATE", "0") == "1"

REPO = os.environ.get("GITHUB_REPOSITORY", "EOVANS/INTENT-Daily-CN")
RAW = "https://raw.githubusercontent.com/%s/main" % REPO
FEED_URL = RAW + "/docs/feed.xml"
MD_URL = RAW + "/docs/latest.md"
SITE = "https://github.com/%s" % REPO

UA = {"User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0 Safari/537.36 INTENT-Daily-CN/1.0"),
      "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*"}

NEWS_SOURCES = {
    "BBC News": {"feeds": ["https://feeds.bbci.co.uk/news/world/rss.xml",
                           "http://feeds.bbci.co.uk/news/world/rss.xml"], "domain": "bbc.co.uk"},
    "CNN": {"feeds": ["http://rss.cnn.com/rss/edition_world.rss",
                      "https://rss.cnn.com/rss/edition_world.rss",
                      "http://rss.cnn.com/rss/edition.rss"], "domain": "cnn.com"},
    "VOA": {"feeds": ["https://www.voanews.com/api/zrqoev-qqm",
                      "https://www.voanews.com/rss"], "domain": "voanews.com"},
    "NBC": {"feeds": ["https://feeds.nbcnews.com/nbcnews/public/world",
                      "https://feeds.nbcnews.com/nbcnews/public/news"], "domain": "nbcnews.com"},
}

AI_SOURCES = {
    "OpenAI Research": {"feeds": ["https://openai.com/news/rss.xml",
                                  "https://openai.com/blog/rss.xml"],
                        "domain": "openai.com", "google": True},
    "Google DeepMind": {"feeds": ["https://deepmind.google/blog/rss.xml",
                                  "https://deepmind.com/blog/feed/basic"],
                        "domain": "deepmind.google", "google": True},
    "Anthropic": {"feeds": ["https://www.anthropic.com/rss.xml",
                            "https://www.anthropic.com/news/rss.xml"],
                  "domain": "anthropic.com", "google": True},
    "arXiv cs.AI": {"feeds": ["http://export.arxiv.org/rss/cs.AI",
                              "https://rss.arxiv.org/rss/cs.AI"], "domain": "arxiv.org"},
}

GOOGLE = "https://news.google.com/rss/search?q=site:%s+when:7d&hl=en-US&gl=US&ceid=US:en"

NEWS_KEYWORDS = [
    ("war", 7), ("missile", 6), ("nuclear", 6), ("strike", 5), ("killed", 5), ("dead", 5),
    ("death toll", 6), ("ceasefire", 5), ("invasion", 6), ("earthquake", 6), ("hurricane", 5),
    ("typhoon", 5), ("volcano", 5), ("tsunami", 6), ("explosion", 5), ("shooting", 4),
    ("crash", 4), ("hijack", 5), ("hostage", 5), ("coup", 6), ("election", 5), ("vote", 4),
    ("sanction", 4), ("tariff", 4), ("inflation", 4), ("recession", 5), ("default", 4),
    ("hack", 5), ("cyberattack", 5), ("outbreak", 5), ("pandemic", 5), ("famine", 5),
    ("refugee", 4), ("migrant", 4), ("evacuate", 4), ("impeach", 5), ("protest", 3),
    ("unrest", 4), ("drone", 4), ("strait", 4), ("oil", 3), ("g20", 3), ("nato", 3),
    ("trump", 3), ("putin", 3), ("netanyahu", 3), ("billion", 2), ("collapse", 4),
]

AI_KEYWORDS = [
    ("model", 5), ("release", 4), ("launch", 4), ("benchmark", 5), ("research", 4),
    ("agent", 5), ("reasoning", 5), ("alignment", 5), ("safety", 4), ("scaling", 4),
    ("training", 4), ("inference", 3), ("multimodal", 4), ("robotics", 4),
    ("open source", 4), ("open-weight", 5), ("evaluation", 3), ("hallucination", 4),
    ("transformer", 4), ("reinforcement", 4), ("dataset", 3), ("compute", 3), ("gpu", 3),
    ("regulation", 3), ("breakthrough", 4), ("state-of-the-art", 5),
]

SRC_TIER = {"BBC News": 1.0, "CNN": 1.0, "VOA": 0.9, "NBC": 0.9,
            "OpenAI Research": 1.0, "Google DeepMind": 1.0, "Anthropic": 1.0, "arXiv cs.AI": 0.85}


def log(msg):
    print("[intent] %s" % msg, file=sys.stderr)


def fetch(url, timeout=25, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            log("fetch fail (%d) %s -> %s" % (attempt + 1, url, exc))
            if attempt < retries:
                time.sleep(1.5)
    return None


def strip_html(text):
    if not text:
        return ""
    text = re.sub("<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub("<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub("<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def pick_image(node, desc):
    for tag in ("{http://search.yahoo.com/mrss/}thumbnail",
                "{http://search.yahoo.com/mrss/}content"):
        for el in node.findall(tag):
            for key in ("url", "href"):
                val = el.get(key)
                if val and val.startswith("http"):
                    return val
    for el in node.findall("enclosure"):
        url = el.get("url")
        if url and (el.get("type") or "").startswith("image"):
            return url
    if isinstance(desc, str):
        m = re.search('<img[^>]+src="([^"]+)"', desc, re.I) or \
            re.search("<img[^>]+src='([^']+)'", desc, re.I)
        if m:
            return m.group(1)
    return ""


def node_text(node, names):
    for name in names:
        el = node.find(name)
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    return ""


def parse_feed(raw, source):
    items = []
    if not raw:
        return items
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        log("parse error %s: %s" % (source, exc))
        return items
    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for node in nodes:
        title = node_text(node, ["title", "{http://www.w3.org/2005/Atom}title"])
        link = node_text(node, ["link"])
        if not link:
            for el in node.findall("{http://www.w3.org/2005/Atom}link"):
                if el.get("rel", "alternate") == "alternate":
                    link = el.get("href", "")
                    break
        desc = node_text(node, ["description", "{http://www.w3.org/2005/Atom}summary",
                                "{http://purl.org/rss/1.0/modules/content/}encoded"])
        pub = node_text(node, ["pubDate", "published", "updated",
                               "{http://www.w3.org/2005/Atom}updated"])
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub)
            except Exception:  # noqa: BLE001
                try:
                    published = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    published = None
        if published is not None and published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if not title or not link:
            continue
        items.append({"source": source, "title": strip_html(title), "link": link.strip(),
                      "summary": strip_html(desc)[:900], "published": published,
                      "image": pick_image(node, desc)})
    return items


_tr = {}


def translate(text):
    text = (text or "").strip()
    if not text or NO_TRANSLATE:
        return text
    if text in _tr:
        return _tr[text]
    try:
        url = ("https://translate.googleapis.com/translate_a/single"
               "?client=gtx&sl=en&tl=zh-CN&dt=t&q=" + urllib.parse.quote(text[:420]))
        req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        out = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip() or text
    except Exception as exc:  # noqa: BLE001
        log("translate fail: %s" % exc)
        out = text
    _tr[text] = out
    return out


def norm(title):
    return re.sub("[^0-9a-z]+", "", title.lower())[:80]


def score_item(item, now, keywords):
    title, summary = item["title"].lower(), (item["summary"] or "").lower()
    score = 0.0
    for word, weight in keywords:
        if word in title:
            score += weight
        elif word in summary:
            score += weight * 0.5
    if item["published"]:
        score += max(0.0, 4.0 - (now - item["published"]).total_seconds() / 86400.0)
    else:
        score += 1.0
    score *= SRC_TIER.get(item["source"], 0.85)
    return score + (1.0 if item["image"] else 0.0)


def collect(now, sources, window_h, keywords, per_source_cap):
    cutoff = now - timedelta(hours=window_h)
    pool, counts = [], {}
    for source, cfg in sources.items():
        got = []
        for feed in cfg["feeds"]:
            got = parse_feed(fetch(feed), source)
            got = [i for i in got if i["published"] and i["published"] >= cutoff]
            if len(got) >= 3:
                break
        if len(got) < 3 and cfg.get("google"):
            extra = parse_feed(fetch(GOOGLE % cfg["domain"]), source)
            got += [i for i in extra if i["published"] and i["published"] >= cutoff]
        counts[source] = len(got)
        log("%s: %d in window" % (source, len(got)))
        pool += got

    seen_t, seen_u, unique = set(), set(), []
    for item in pool:
        key_t, key_u = norm(item["title"]), item["link"].split("?")[0]
        if key_t in seen_t or key_u in seen_u:
            continue
        seen_t.add(key_t)
        seen_u.add(key_u)
        item["score"] = score_item(item, now, keywords)
        unique.append(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    chosen, used = [], {}
    for item in unique:
        src = item["source"]
        if used.get(src, 0) >= per_source_cap:
            continue
        chosen.append(item)
        used[src] = used.get(src, 0) + 1
    return chosen, counts


def cdata(text):
    return "<![CDATA[%s]]>" % (text or "").replace("]]>", "]]&gt;")


def build_rss(blocks, now):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
           'xmlns:media="http://search.yahoo.com/mrss/" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/">',
           "<channel>",
           "<title>INTENT Daily CN · 每日国际要闻 + AI 研究动态</title>",
           "<link>%s</link>" % html.escape(SITE),
           '<atom:link href="%s" rel="self" type="application/rss+xml"/>' % html.escape(FEED_URL),
           "<description><![CDATA[每日北京时间 07:35 自动更新。板块一：BBC News / CNN / VOA / NBC "
           "国际要闻；板块二：OpenAI Research / Google DeepMind / Anthropic / arXiv 的 AI 研究动态。]]></description>",
           "<language>zh-CN</language>",
           "<lastBuildDate>%s</lastBuildDate>" % format_datetime(now),
           "<generator>INTENT Daily CN</generator>", "<ttl>60</ttl>"]
    for block in blocks:
        for item in block["items"]:
            title = "【%s】%s" % (item["source"], item.get("title_zh") or item["title"])
            desc = ""
            if item["image"]:
                desc += ('<p><img src="%s" alt="" style="max-width:100%%;border-radius:6px"/></p>'
                         % html.escape(item["image"], quote=True))
            desc += "<p>%s</p>" % html.escape(item.get("summary_zh") or item["summary"] or "")
            desc += ('<p style="color:#9ca3af;font-size:12px">来源：%s · %s</p>'
                     % (html.escape(item["source"]), html.escape(item["title"])))
            desc += '<p><a href="%s">阅读原文 / Read original</a></p>' % html.escape(
                item["link"], quote=True)
            out += ["<item>",
                    "<title>%s</title>" % html.escape(title),
                    "<link>%s</link>" % html.escape(item["link"]),
                    '<guid isPermaLink="true">%s</guid>' % html.escape(item["link"]),
                    "<description>%s</description>" % cdata(desc),
                    "<pubDate>%s</pubDate>" % format_datetime(item["published"] or now),
                    "<dc:source>%s</dc:source>" % html.escape(item["source"]),
                    "<category>%s</category>" % html.escape(block["label"]),
                    "<category>%s</category>" % html.escape(item["source"])]
            if item["image"]:
                out += ['<media:content url="%s" medium="image"/>' % html.escape(item["image"], quote=True),
                        '<media:thumbnail url="%s"/>' % html.escape(item["image"], quote=True)]
            out.append("</item>")
    out += ["</channel>", "</rss>"]
    return "\n".join(out)


def build_md(blocks, now, today, stats):
    lines = ["# INTENT Daily CN · 每日国际要闻", "",
             "> **日期**：%s（北京时间）｜**生成**：%s｜每日 07:35 自动更新"
             % (today, now.strftime("%H:%M")),
             "> **RSS 订阅**：<%s>" % FEED_URL, ""]
    for block in blocks:
        lines += ["## %s" % block["label"], "", "*%s*" % block["desc"], ""]
        if not block["items"]:
            lines += ["_本期该板块无满足条件的内容。_", ""]
            continue
        for idx, item in enumerate(block["items"], 1):
            lines += ["### %d. %s" % (idx, item.get("title_zh") or item["title"]), ""]
            if item["summary"]:
                lines += [item.get("summary_zh") or item["summary"], ""]
            if item["image"]:
                lines += ["![%s](%s)" % (item["source"], item["image"]), ""]
            lines.append("- **来源**：%s" % item["source"])
            lines.append("- **原文标题**：%s" % item["title"])
            if item["published"]:
                lines.append("- **发布时间**：%s"
                             % item["published"].astimezone(CST).strftime("%Y-%m-%d %H:%M"))
            lines += ["- **原文链接**：<%s>" % item["link"], ""]
    lines += ["---", "", "### 抓取概况", "", "| 来源 | 窗口内条数 |", "| --- | --- |"]
    lines += ["| %s | %s |" % (s, c) for s, c in stats.items()]
    lines += ["", "> 由 GitHub Actions 自动生成，请勿手工编辑。", ""]
    return "\n".join(lines)


def main():
    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    log("build start %s" % now.isoformat())

    news, news_counts = collect(now, NEWS_SOURCES, NEWS_WINDOW_H, NEWS_KEYWORDS, 4)
    news = news[:NEWS_TOP_N]
    ai, ai_counts = collect(now, AI_SOURCES, AI_WINDOW_H, AI_KEYWORDS, 2)
    ai = ai[:AI_TOP_N]
    if not news and not ai:
        log("FATAL: no items collected")
        return 2

    for item in news + ai:
        item["title_zh"] = translate(item["title"])
        item["summary_zh"] = translate(item["summary"][:220]) if item["summary"] else ""
        time.sleep(0.1)

    blocks = [{"label": "一、国际要闻（BBC / CNN / VOA / NBC）",
               "desc": "过去 24 小时全球 Breaking News，按重要性降序。", "items": news},
              {"label": "二、AI 研究动态（OpenAI Research 等）",
               "desc": "OpenAI Research、Google DeepMind、Anthropic、arXiv cs.AI 的最新研究与发布。",
               "items": ai}]
    stats = dict(news_counts)
    stats.update(ai_counts)

    os.makedirs("docs/daily", exist_ok=True)
    os.makedirs("archive", exist_ok=True)
    rss = build_rss(blocks, now)
    md = build_md(blocks, now, today, stats)
    for path, content in [("docs/feed.xml", rss), ("archive/%s.xml" % today, rss),
                          ("docs/latest.md", md), ("docs/daily/%s.md" % today, md)]:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    payload = {"date": today, "generated_at": now.isoformat(), "rss": FEED_URL, "markdown": MD_URL,
               "blocks": [{"label": b["label"], "items": [{
                   "rank": i + 1, "source": it["source"], "title_zh": it.get("title_zh"),
                   "title_en": it["title"], "summary_zh": it.get("summary_zh"),
                   "url": it["link"], "image": it["image"],
                   "published": it["published"].isoformat() if it["published"] else None,
                   "score": round(it["score"], 2)} for i, it in enumerate(b["items"])]}
                   for b in blocks], "source_counts": stats}
    with open("docs/latest.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    log("done: news=%d ai=%d" % (len(news), len(ai)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
