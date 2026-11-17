#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""流水线包装：可观测性 + 多供应商翻译链

任何异常都会写进 docs/status.json（含 traceback 尾部），保证失败可诊断。
"""

import importlib.util
import json
import os
import sys
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("bf", "scripts/build_feed.py")
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)

STATUS = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "feeds": {}, "translate": {},
          "translate_provider": None, "error": None}

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
    body = _get(url)
    data = json.loads(body)
    if isinstance(data, list):
        return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
    raise ValueError("unexpected shape: %s" % body[:80])


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
        raise ValueError("empty translatedText %s"
                         % str(data.get("responseStatus"))[:40])
    return out


PROVIDERS = [("google-gtx", p_gtx), ("google-clients5", p_clients5), ("mymemory", p_mymemory)]
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


bf.fetch = fetch
bf.translate = translate

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
