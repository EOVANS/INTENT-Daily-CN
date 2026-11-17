#!/usr/bin/env python3
"""一次性诊断：在 GitHub Actions 环境探测各 RSS 源与翻译接口的可用性，输出 docs/diagnose.md"""
import importlib.util, json, os, sys, urllib.request, urllib.parse, time
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("bf", "scripts/build_feed.py")
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)


def probe(url):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=bf.UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
        ok, size, note = True, len(raw), ""
        try:
            root = ET.fromstring(raw)
            nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            note = "%d entries" % len(nodes)
            newest = ""
            for n in nodes[:3]:
                d = bf.node_text(n, ["pubDate", "published", "updated",
                                     "{http://www.w3.org/2005/Atom}updated"])
                if d:
                    newest = d[:31]
                    break
            note += " | newest: %s" % newest
        except Exception as exc:  # noqa: BLE001
            note = "not-xml (%s)" % str(exc)[:60]
    except Exception as exc:  # noqa: BLE001
        ok, size, note = False, 0, "ERR %s" % str(exc)[:120]
    return ok, size, note, round(time.time() - t0, 1)


rows = []
for group in ("NEWS_SOURCES", "AI_SOURCES"):
    for name, cfg in getattr(bf, group).items():
        for feed in cfg["feeds"]:
            ok, size, note, sec = probe(feed)
            rows.append((name, feed, "OK" if ok else "FAIL", size, note, sec))
        if cfg.get("google"):
            g = bf.GOOGLE % cfg["domain"]
            ok, size, note, sec = probe(g)
            rows.append((name, g, "OK" if ok else "FAIL", size, note, sec))

tr = []
tests = {
    "google-gtx": "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=hello%20world",
    "google-apis-v2": "https://translation.googleapis.com/language/translate/v2?q=hello&target=zh-CN",
    "mymemory": "https://api.mymemory.translated.net/get?q=hello%20world&langpair=en|zh-CN",
    "bing-free": "https://www.bing.com/ttranslatev3?fromLang=en&to=zh-Hans&text=hello",
}
for name, url in tests.items():
    ok, size, note, sec = probe(url)
    body = ""
    try:
        req = urllib.request.Request(url, headers=bf.UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "ignore")[:160]
    except Exception:  # noqa: BLE001
        pass
    tr.append((name, "OK" if ok else "FAIL", size, note, body.replace("\n", " "))

lines = ["# 构建环境诊断", "", "> 由 diagnose.yml 自动生成，仅用于排查，可随时删除。", "",
         "## RSS 源", "", "| 分组 | 源 | 结果 | 字节 | 说明 | 耗时(s) |", "| --- | --- | --- | --- | --- | --- |"]
for name, url, res, size, note, sec in rows:
    lines.append("| %s | %s | %s | %s | %s | %s |" % (name, url, res, size, note, sec))
lines += ["", "## 翻译接口", "", "| 接口 | 结果 | 字节 | 说明 | 返回片段 |", "| --- | --- | --- | --- | --- |"]
for name, res, size, note, body in tr:
    lines.append("| %s | %s | %s | %s | %s |" % (name, res, size, note, body.replace("|", "/")))

os.makedirs("docs", exist_ok=True)
with open("docs/diagnose.md", "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print("diagnose written")
