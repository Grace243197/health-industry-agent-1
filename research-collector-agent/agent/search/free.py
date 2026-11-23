# -*- coding: utf-8 -*-
"""
search/free.py · 免费学术/百科检索（零 key、零费用）

四个来源：
  PubMed E-utilities  —— 生物医学论文，A/B 级证据的主来源
  Europe PMC REST     —— 补充摘要与开放获取信息
  OpenAlex            —— 跨学科文献元数据（含 DOI）
  Wikipedia (zh)      —— 行业背景与术语解释，只能当 B/C 级线索

任何一路失败都不影响其它路：错误进 errors，由上层打印出来，绝不静默。
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request

USER_AGENT = "sleep-research-agent/3.0 (+student project; low-rate)"
ACADEMIC_QUERIES = ("pubmed", "europepmc", "openalex", "wikipedia")


def _get_json(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _short(text, limit=200):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit]


# ------------------------------------------------------------ 各来源
def _pubmed(query, top_k, timeout):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    q = urllib.parse.quote(query)
    found = _get_json("{0}/esearch.fcgi?db=pubmed&retmode=json&retmax={1}&term={2}".format(
        base, top_k, q), timeout)
    ids = ((found.get("esearchresult") or {}).get("idlist") or [])[:top_k]
    if not ids:
        return [], None

    summary = _get_json("{0}/esummary.fcgi?db=pubmed&retmode=json&id={1}".format(
        base, ",".join(ids)), timeout)
    result = summary.get("result") or {}
    items = []
    for uid in ids:
        record = result.get(uid) or {}
        if not record.get("title"):
            continue
        items.append({
            "title": _short(record.get("title")),
            "url": "https://pubmed.ncbi.nlm.nih.gov/{0}/".format(uid),
            "snippet": _short("；".join(x for x in (record.get("fulljournalname"),
                                                    record.get("pubdate")) if x)),
            "date": record.get("pubdate", ""),
            "api": "pubmed",
        })
    return items, None


def _europepmc(query, top_k, timeout):
    q = urllib.parse.quote(query)
    data = _get_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        "?query={0}&format=json&pageSize={1}&resultType=core".format(q, top_k), timeout)
    items = []
    for record in ((data.get("resultList") or {}).get("result") or [])[:top_k]:
        pmid = record.get("pmid")
        doi = record.get("doi")
        url = ("https://europepmc.org/article/MED/" + pmid) if pmid else (
            "https://doi.org/" + doi if doi else "")
        if not url:
            continue
        items.append({
            "title": _short(record.get("title")),
            "url": url,
            "snippet": _short(record.get("abstractText") or record.get("journalTitle") or ""),
            "date": record.get("firstPublicationDate", ""),
            "api": "europepmc",
        })
    return items, None


def _openalex(query, top_k, timeout):
    q = urllib.parse.quote(query)
    data = _get_json(
        "https://api.openalex.org/works?search={0}&per-page={1}".format(q, top_k), timeout)
    items = []
    for work in (data.get("results") or [])[:top_k]:
        url = work.get("doi") or work.get("id") or ""
        if not url:
            continue
        items.append({
            "title": _short(work.get("display_name")),
            "url": url,
            "snippet": "发表年份：{0}".format(work.get("publication_year", "未知")),
            "date": str(work.get("publication_year", "")),
            "api": "openalex",
        })
    return items, None


def _wikipedia(query, top_k, timeout):
    q = urllib.parse.quote(query)
    data = _get_json(
        "https://zh.wikipedia.org/w/api.php?action=query&list=search&format=json"
        "&srlimit={0}&utf8=1&srsearch={1}".format(top_k, q), timeout)
    items = []
    for record in ((data.get("query") or {}).get("search") or [])[:top_k]:
        title = record.get("title", "")
        if not title:
            continue
        items.append({
            "title": title,
            "url": "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            "snippet": _short(html.unescape(re.sub(r"<[^>]+>", "", record.get("snippet", "")))),
            "date": "",
            "api": "wikipedia",
        })
    return items, None


HANDLERS = {
    "pubmed": _pubmed,
    "europepmc": _europepmc,
    "openalex": _openalex,
    "wikipedia": _wikipedia,
}


# ------------------------------------------------------------ 对外入口
def search(query, top_k, timeout):
    """并行度故意不拉满：这是低频调研，宁可慢一点也不要被限流。"""
    if not (query or "").strip():
        return [], ["free: 查询为空"]

    per_source = max(1, int(top_k) // 2)
    items, errors = [], []
    for name in ACADEMIC_QUERIES:
        try:
            found, error = HANDLERS[name](query, per_source, timeout)
        except Exception as exc:                               # noqa: BLE001
            errors.append("{0}: {1}: {2}".format(name, type(exc).__name__, str(exc)[:80]))
            continue
        if error:
            errors.append("{0}: {1}".format(name, error))
        items.extend(found)
    return items, errors