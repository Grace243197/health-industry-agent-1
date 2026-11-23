# -*- coding: utf-8 -*-
"""
web_ui.py · 本地网页窗口：提问 → 答案 → 下载 PDF 报告

为什么用标准库：
  这个页面只是把 `ask_report` 包一层，不需要框架。`http.server` 足够，
  也不用为了演示再装 FastAPI/Flask。

启动：
  python tools/web_ui.py                     # http://127.0.0.1:8000
  python tools/web_ui.py --port 8080
  python tools/web_ui.py --no-llm            # 只做本地汇总，不调模型

安全边界：
  - 默认只监听 127.0.0.1，不给同网段访问；
  - /download/ 只放行 `output/` 下形如 `<时间戳>_report.pdf|md` 的文件，
    其余路径一律 404，避免被拿来读任意文件。
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ask_report import OUTPUT, answer_question

FILE_PATTERN = re.compile(r"^\d{8}-\d{6}_report\.(pdf|md)$")

STYLE = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; padding: 32px 20px; font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
       background: #f6f7f9; color: #1f2328; line-height: 1.7; }
main { max-width: 860px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 6px; }
.sub { color: #6b7280; font-size: 13px; margin-bottom: 22px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px 22px; margin-bottom: 18px; }
form { display: flex; gap: 10px; flex-wrap: wrap; }
input[type=text] { flex: 1 1 420px; min-width: 240px; padding: 12px 14px; font-size: 15px;
                   border: 1px solid #d1d5db; border-radius: 8px; }
button { padding: 12px 20px; font-size: 15px; border: 0; border-radius: 8px;
         background: #2563eb; color: #fff; cursor: pointer; }
button:hover { background: #1d4ed8; }
.answer { white-space: pre-wrap; font-size: 15px; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px;
       background: #eef2ff; color: #3730a3; margin-right: 6px; }
.tag.C { background: #fef3c7; color: #92400e; }
.tag.B { background: #dbeafe; color: #1e40af; }
.tag.A { background: #dcfce7; color: #166534; }
table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }
th, td { border-bottom: 1px solid #eceff3; padding: 8px 6px; text-align: left; vertical-align: top; }
th { color: #6b7280; font-weight: 600; }
.btn { display: inline-block; margin: 14px 10px 0 0; padding: 11px 18px; border-radius: 8px;
       background: #059669; color: #fff; text-decoration: none; font-size: 15px; }
.btn:hover { background: #047857; }
.btn.ghost { background: #eef2f7; color: #334155; }
.btn.ghost:hover { background: #e2e8f0; }
.empty { color: #9ca3af; font-size: 13px; }
ul.recent { margin: 6px 0 0; padding-left: 18px; font-size: 13px; }
ul.recent a { color: #2563eb; text-decoration: none; }
footer { color: #9ca3af; font-size: 12px; margin-top: 28px; text-align: center; }
"""


def page(title: str, body: str) -> bytes:
    return ("""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{0}</title><style>{1}</style></head>
<body><main>{2}
<footer>成人睡眠监测 · 多 Agent 调研体系 ｜ 本地运行，不对外网开放</footer>
</main></body></html>""").format(html.escape(title), STYLE, body).encode("utf-8")


def recent_reports(limit: int = 8) -> str:
    if not OUTPUT.is_dir():
        return '<p class="empty">还没有生成过报告。</p>'
    files = sorted(OUTPUT.glob("*_report.pdf"), reverse=True)[:limit]
    if not files:
        return '<p class="empty">还没有生成过报告。</p>'
    items = "\n".join(
        '<li><a href="/download/{0}">{0}</a></li>'.format(html.escape(f.name)) for f in files)
    return '<ul class="recent">{0}</ul>'.format(items)


def home(error: str = "") -> bytes:
    error_html = '<p style="color:#b91c1c;font-size:13px">{0}</p>'.format(html.escape(error)) if error else ""
    body = """
<h1>问一个问题，拿一份带证据的报告</h1>
<p class="sub">在本地知识库里检索原文 → 生成答案 → 导出 PDF 下载。检索不联网；未配置模型密钥时只做原文汇总。</p>
<div class="card">
  {error}
  <form method="post" action="/ask">
    <input type="text" name="q" placeholder="例如：CPAP 依从性对疗效有什么影响" autofocus>
    <button type="submit">生成报告</button>
  </form>
  <p class="empty" style="margin:12px 0 0">首次使用：把 PDF 放进 <code>inbox/pdfs/</code>，先跑 <code>python tools/ingest.py --run-id demo</code>。</p>
</div>
<div class="card">
  <strong style="font-size:14px">最近的报告</strong>
  {recent}
</div>""".format(error=error_html, recent=recent_reports())
    return page("睡眠监测调研 · 提问与报告", body)


def result_page(result: dict) -> bytes:
    evidence_rows = []
    for index, item in enumerate(result["evidence"], 1):
        snippet = html.escape(item["text"])
        if len(snippet) > 220:
            snippet = snippet[:220] + "…"
        evidence_rows.append(
            "<tr><td>{0}</td><td>{1}<br><span class='empty'>{2}</span></td>"
            "<td><span class='tag {3}'>{3}</span></td><td>{4}</td></tr>".format(
                index, html.escape(item["source_id"]),
                html.escape(item["title"][:40]), html.escape(item["evidence_level"]), snippet))

    table = ""
    if evidence_rows:
        table = ('<table><thead><tr><th>#</th><th>来源</th><th>等级</th><th>原文片段</th>'
                 '</tr></thead><tbody>{0}</tbody></table>').format("".join(evidence_rows))
    else:
        table = '<p class="empty">没有命中任何原文。请先入库资料，或换一组关键词。</p>'

    pdf_name = Path(result["pdf_path"]).name if result["pdf_path"] else ""
    md_name = Path(result["md_path"]).name
    download = ""
    if pdf_name:
        download = '<a class="btn" href="/download/{0}">下载 PDF 报告</a>'.format(
            html.escape(pdf_name))
    download += '<a class="btn ghost" href="/download/{0}">查看 Markdown</a>'.format(
        html.escape(md_name))
    download += '<a class="btn ghost" href="/">再问一个</a>'

    mode = "模型组织（仅限证据）" if result["used_llm"] else "本地汇总（未调用模型）"
    body = """
<h1>{q}</h1>
<p class="sub">命中 {n} 条来源 ｜ {mode}</p>
<div class="card">
  <div class="answer">{answer}</div>
  {download}
</div>
<div class="card">
  <strong style="font-size:14px">证据清单</strong>
  {table}
</div>""".format(
        q=html.escape(result["question"]),
        n=len(result["evidence"]),
        mode=html.escape(mode),
        answer=html.escape(result["answer"]),
        download=download,
        table=table,
    )
    return page("调研结果 · " + result["question"][:30], body)


class Handler(BaseHTTPRequestHandler):
    server_version = "SleepResearchUI/3.0"
    use_llm = True

    def log_message(self, fmt, *args):        # 只打一行简短访问日志
        sys.stderr.write("[web] " + fmt % args + "\n")

    def _send(self, data: bytes, status: int = 200, content_type: str = "text/html; charset=utf-8",
              extra_headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    # ---------------------------------------------------------- GET
    def do_GET(self):                                        # noqa: N802
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            return self._send(home())

        if parsed.path == "/health":
            return self._send(b'{"status":"ok"}', content_type="application/json")

        if parsed.path.startswith("/download/"):
            return self._serve_file(parsed.path[len("/download/"):])

        if parsed.path == "/favicon.ico":
            return self._send(b"", status=204)

        return self._send(page("404", "<h1>404</h1><p>没有这个页面。</p>"), status=404)

    def _serve_file(self, raw_name: str):
        name = urllib.parse.unquote(raw_name)
        if not FILE_PATTERN.match(name):
            return self._send(page("404", "<h1>404</h1><p>文件不存在。</p>"), status=404)

        path = (OUTPUT / name).resolve()
        # 双保险：正则已经限制了文件名，这里再确认最终路径没逃出 output/
        if not str(path).startswith(str(OUTPUT.resolve())) or not path.is_file():
            return self._send(page("404", "<h1>404</h1><p>文件不存在。</p>"), status=404)

        content_type = "application/pdf" if path.suffix == ".pdf" else "text/markdown; charset=utf-8"
        disposition = "attachment" if path.suffix == ".pdf" else "inline"
        return self._send(
            path.read_bytes(),
            content_type=content_type,
            extra_headers={"Content-Disposition": '{0}; filename="{1}"'.format(disposition, name)},
        )

    # ---------------------------------------------------------- POST
    def do_POST(self):                                       # noqa: N802
        if urllib.parse.urlparse(self.path).path != "/ask":
            return self._send(page("404", "<h1>404</h1>"), status=404)

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        question = (urllib.parse.parse_qs(raw).get("q") or [""])[0].strip()

        if not question:
            return self._send(home("请先输入一个问题。"), status=400)

        try:
            result = answer_question(question, top_k=6, use_llm=self.use_llm, make_pdf=True)
        except Exception as exc:                             # noqa: BLE001
            return self._send(
                page("出错了", "<h1>生成失败</h1><p>{0}: {1}</p><p><a href='/'>返回</a></p>".format(
                    html.escape(type(exc).__name__), html.escape(str(exc)))),
                status=500,
            )

        return self._send(result_page(result))


def main() -> int:
    ap = argparse.ArgumentParser(description="本地网页窗口：提问并下载 PDF 报告")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-llm", action="store_true", help="不调用模型，只做本地原文汇总")
    args = ap.parse_args()

    Handler.use_llm = not args.no_llm
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("已启动：http://{0}:{1}/".format(args.host, args.port))
    print("模型组织答案：{0}".format("开启（需 DASHSCOPE_API_KEY）" if Handler.use_llm else "关闭"))
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())