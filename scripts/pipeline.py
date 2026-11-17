#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流水线包装：可观测性 + 多供应商翻译 + 更稳的收录逻辑

任何异常都会写进 docs/status.json（含 traceback 尾部），保证失败可诊断。
"""

import html
import importlib.util
import json
import os
import re
import sys
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timedelta

spec = importlib.util.spec_from_file_location("bf", "scripts/build_feed.py")
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)

STATUS = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "feeds": {}, "translate": {},
          "translate_provider": None, "sources": {}, "error": None}

# VOA 官方 RSS 在数据中心 IP 上常被拦截，强制走 Google News 兜底
bf.NEWS_SOURCES["VOA"]["google"] = True

_orig_fetch = bf.fetch


def fetch(url, timeout=25, retries=2):
    raw = _orig_fetch(url, timeout=timeout, retries=retries)
    info = {"ok": bool(raw), "bytes": len(raw or b"")}
    if raw:
        try:
            root = ET.fromstring(raw)
            nodes = root.findall(".//item") or root.findall(
                ".//{http://www.w3.org/2005/Atom}entry")
            info["entries"] = len(nodes)
        except Exception as exc:  # noqa: BLE001
            info["xml_error"] = str(exc)[:80]
    STATUS["feeds"][url] = info
    return raw


def _get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", "ignore")


def p_gtx(text):
    url = ("https://translate.googleapis.com/translate_a/single"
           "?client=gtx&sl=en&tl=zh-CN&dt=t&q=" + urllib.parse.quote(text[:420]))
    data = json.loads(_get(url))
    if isinstance(data, list):
        return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
    raise ValueError("unexpected shape")


def p_clients5(text):
    url = ("https://clients5.google.com/translate_a/t?client=dict-chrome-ex"
           "&sl=en&tl=zh-CN&q=" + urllib.parse.quote(text[:420]))
    data = json.loads(_get(url))
    if isinstance(data, list):
        if data and isinstance(data[0], list):
            return "".join(x for x in data[0] if isinstance(x, str)).strip()
        if data and isinstance(data[0], str):
            return data[0].strip()
    raise ValueError("unexpected shape")


def p_mymemory(text):
    url = ("https://api.mymemory.translated.net/get?q="
           + urllib.parse.quote(text[:420]) + "&langpair=en|zh-CN")
    data = json.loads(_get(url))
    out = ((data.get("responseData") or {}).get("translatedText") or "").strip()
    if not out:
        raise ValueError("empty translatedText")
    return out


PROVIDERS = [("google-clients5", p_clients5), ("google-gtx", p_gtx), ("mymemory", p_mymemory)]
_tr = {}


def translate(text):
    text = (text or "").strip()
    if not text or os.environ.get("NO_TRANSLATE", "0") == "1":
        return text
    if text in _tr:
        return _tr[text]
    for name, fn in PROVIDERS:
        rec = STATUS["translate"].setdefault(name, {"ok": 0, "fail": 0, "last_error": ""})
        try:
            out = fn(text)
            if out and out != text:
                rec["ok"] += 1
                STATUS["translate_provider"] = name
                _tr[text] = out
                return out
            raise ValueError("empty or unchanged output")
        except Exception as exc:  # noqa: BLE001
            rec["fail"] += 1
            rec["last_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
    _tr[text] = text
    return text


JUNK_HOSTS = ("fool.com", "lendingtree.com", "nerdwallet.com", "bankrate.com", "capitalone.com",
             "wellsfargo.com", "ascent", "doubleclick", "outbrain", "taboola",
             "splitterid=", "csource=", "utm_source=cnn")
JUNK_TITLE = ("intro apr", "credit card", "click here", "sign up", "episode", "podcast",
              "newsletter", "watch:", "listen:", "how to watch", "live updates",
              "bbc parliament", "questions,")
SOURCE_SUFFIX = re.compile(
    r"\s*[-–|]\s*(BBC News|BBC|CNN News|CNN|NBC News|NBC|VOA News|VOA|Voice of America English News"
    r"|Voice of America|Anthropic Alignment Science blog|Anthropic)\s*$", re.I)


def clean_title(title):
    return SOURCE_SUFFIX.sub("", (title or "").strip()).strip()


def is_junk(item):
    link = (item.get("link") or "").lower()
    if any(h in link for h in JUNK_HOSTS):
        return True
    title = (item.get("title") or "").lower()
    return any(p in title for p in JUNK_TITLE)


def collect(now, sources, window_h, keywords, per_source_cap):
    """直连 feed -> 窗口内不足时补 Google News -> 仍不足才用无日期条目"""
    cutoff = now - timedelta(hours=window_h)
    pool, counts = [], {}
    for source, cfg in sources.items():
        raw_items = bf.parse_feed(fetch(cfg["feeds"][0]), source) if cfg["feeds"] else []
        for feed in cfg["feeds"][1:]:
            if len(raw_items) >= 3:
                break
            raw_items += bf.parse_feed(fetch(feed), source)
        inwin = [i for i in raw_items if i["published"] and i["published"] >= cutoff]
        from_google = 0
        if len(inwin) < 3 and cfg.get("google"):
            extra = bf.parse_feed(fetch(bf.GOOGLE % cfg["domain"]), source)
            extra = [i for i in extra if i["published"] and i["published"] >= cutoff]
            from_google = len(extra)
            raw_items += extra
            inwin = [i for i in raw_items if i["published"] and i["published"] >= cutoff]
        raw_items = [i for i in raw_items if not is_junk(i)]
        for item in raw_items:
            item["title"] = clean_title(item["title"])
        inwin = [i for i in raw_items if i["published"] and i["published"] >= cutoff]
        undated = [i for i in raw_items if not i["published"]][:4]
        used = inwin if len(inwin) >= 3 else inwin + undated
        for item in undated:
            item["published"] = now  # 无日期条目多为 feed 头部最新稿，按当前时间计分
        counts[source] = len(used)
        STATUS["sources"][source] = {"raw": len(raw_items), "in_window": len(inwin),
                                     "from_google": from_google, "undated": len(undated),
                                     "used": len(used)}
        pool += used

    seen_t, seen_u, unique = set(), set(), []
    for item in pool:
        key_t, key_u = bf.norm(item["title"]), item["link"].split("?")[0]
        if key_t in seen_t or key_u in seen_u:
            continue
        seen_t.add(key_t)
        seen_u.add(key_u)
        item["score"] = bf.score_item(item, now, keywords)
        unique.append(item)

    unique.sort(key=lambda x: x["score"], reverse=True)
    chosen, used_count = [], {}
    for item in unique:
        src = item["source"]
        if used_count.get(src, 0) >= per_source_cap:
            continue
        chosen.append(item)
        used_count[src] = used_count.get(src, 0) + 1

    # 覆盖保底：有候选却没进榜的来源，用它的最佳一条替换超额来源里最弱的一条
    have = {i["source"] for i in chosen}
    floor_items = []
    for source in sources:
        if source in have:
            continue
        best = next((i for i in unique if i["source"] == source), None)
        if best is None:
            continue
        for item in reversed(chosen):
            if sum(1 for c in chosen if c["source"] == item["source"]) > 1:
                chosen.remove(item)
                break
        chosen.append(best)
        floor_items.append(best)

    # 保底条目必须活过下游“取前 N”的切片，因此输出恰好 N 条
    top_n = int(os.environ.get("NEWS_TOP_N" if "BBC News" in sources else "AI_TOP_N", "8"))
    if floor_items:
        keep = [i for i in chosen if i not in floor_items]
        slots = max(top_n - len(floor_items), 0)
        chosen = keep[:slots] + floor_items
    chosen = chosen[:top_n]

    chosen.sort(key=lambda x: x["score"], reverse=True)
    return chosen, counts


bf.fetch = fetch
bf.translate = translate
bf.collect = collect

# 产品名统一为「每日新闻」（覆盖 build_feed 里写死的中文标题）
PRODUCT_NAME = "每日新闻"
_orig_rss, _orig_md = bf.build_rss, bf.build_md


def build_md(blocks, now, today, stats):
    return _orig_md(blocks, now, today, stats).replace("每日国际要闻", PRODUCT_NAME)


def build_rss(blocks, now):
    """每期只出一条 <item>：当天全部要闻 + AI 摘要打包在同一条描述里"""
    day = now.strftime("%Y-%m-%d")
    body = []
    for block in blocks:
        items = block["items"]
        if not items:
            continue
        body.append('<h3 style="margin:22px 0 6px;font-size:15px;color:#1d4ed8">%s</h3>'
                    % html.escape(block["label"]))
        if block.get("desc"):
            body.append('<p style="color:#6b7280;font-size:12px;margin:0 0 10px">%s</p>'
                        % html.escape(block["desc"]))
        for idx, item in enumerate(items, 1):
            body.append('<h4 style="margin:16px 0 6px;font-size:16px;line-height:1.5">%d. %s</h4>'
                        % (idx, html.escape(item.get("title_zh") or item["title"])))
            if item["image"]:
                body.append('<p style="margin:0 0 8px"><img src="%s" alt="" '
                            'style="max-width:100%%;border-radius:6px"/></p>'
                            % html.escape(item["image"], quote=True))
            summary = item.get("summary_zh") or item["summary"] or ""
            if summary:
                body.append('<p style="line-height:1.75;margin:0 0 6px">%s</p>'
                            % html.escape(summary))
            body.append('<p style="color:#9ca3af;font-size:12px;margin:0 0 4px">来源：%s · %s</p>'
                        % (html.escape(item["source"]), html.escape(item["title"])))
            body.append('<p style="margin:0 0 4px"><a href="%s">阅读原文 / Read original</a></p>'
                        % html.escape(item["link"], quote=True))

    first_img = ""
    for block in blocks:
        for item in block["items"]:
            if item["image"]:
                first_img = item["image"]
                break
        if first_img:
            break

    total = sum(len(b["items"]) for b in blocks)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
           'xmlns:media="http://search.yahoo.com/mrss/" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/">',
           "<channel>",
           "<title>INTENT Daily CN · %s</title>" % html.escape(PRODUCT_NAME),
           "<link>%s</link>" % html.escape(bf.SITE),
           '<atom:link href="%s" rel="self" type="application/rss+xml"/>' % html.escape(bf.FEED_URL),
           "<description><![CDATA[每日北京时间 07:35 自动更新，每期一条，内含当天国际要闻"
           "（BBC News / CNN / VOA / NBC）与 AI 研究动态（OpenAI Research / Google DeepMind / "
           "Anthropic / arXiv）的中文摘要。]]></description>",
           "<language>zh-CN</language>",
           "<lastBuildDate>%s</lastBuildDate>" % bf.format_datetime(now),
           "<generator>INTENT Daily CN</generator>", "<ttl>60</ttl>",
           "<item>",
           "<title>%s · %s｜%d 条要闻</title>" % (html.escape(PRODUCT_NAME), day, total),
           "<link>%s</link>" % html.escape(bf.FEED_URL),
           '<guid isPermaLink="false">%s#%s</guid>' % (html.escape(bf.FEED_URL), day),
           "<description>%s</description>" % bf.cdata("\n".join(body)),
           "<pubDate>%s</pubDate>" % bf.format_datetime(now),
           "<dc:source>BBC News / CNN / VOA / NBC</dc:source>",
           "<category>%s</category>" % html.escape(PRODUCT_NAME)]
    if first_img:
        out += ['<media:content url="%s" medium="image"/>' % html.escape(first_img, quote=True),
                '<media:thumbnail url="%s"/>' % html.escape(first_img, quote=True)]
    out += ["</item>", "</channel>", "</rss>"]
    return "\n".join(out)


bf.build_rss, bf.build_md = build_rss, build_md

rc = 1
try:
    rc = bf.main() or 0
except Exception:  # noqa: BLE001
    STATUS["error"] = traceback.format_exc()[-1200:]
    rc = 3
finally:
    STATUS["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        os.makedirs("docs", exist_ok=True)
        with open("docs/status.json", "w", encoding="utf-8") as fh:
            json.dump(STATUS, fh, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        print("[pipeline] status write fail: %s" % exc, file=sys.stderr)

sys.exit(rc)
