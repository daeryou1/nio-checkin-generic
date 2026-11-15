#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔚来签到 · 本地配置页 (零第三方依赖, 仅监听 127.0.0.1)

    python server.py            打开 http://127.0.0.1:18923

功能:
    - 看板: 各账号签到状态 / 连续天数
    - 添加/更新账号: 粘贴 token、cookie 串或 "Bearer xxx", 自动解析
    - 手动签到: 让某账号立即签一次 (验证凭据是否有效)
    - 书签工具: 在已登录的 www.nio.cn 页面一键提取 token 到剪贴板
    - 日志查看

凭据只写入本目录 accounts.json, 不上传任何地方。
"""

import json
import os
import subprocess
import sys
import threading
import urllib.parse
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkin  # noqa: E402

HOST = "127.0.0.1"
PORT = 18923
BASE = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_PATH = os.path.join(BASE, "accounts.json")

BOOKMARKLET_JS = (
    "(function(){"
    "var m=document.cookie.match(/nio-account-info=([^;]+)/);"
    "if(!m){alert('未找到 nio-account-info, 请先在 www.nio.cn 登录');return;}"
    "var v=decodeURIComponent(m[1]);var t='';"
    "try{var o=JSON.parse(v);t=o.access_token||o.token||'';}catch(e){t=v;}"
    "if(!t){alert('cookie 里没有 access_token');return;}"
    "if(t.indexOf('Bearer ')!==0){t='Bearer '+t;}"
    "try{navigator.clipboard.writeText(t).then("
    "function(){prompt('已复制到剪贴板, 回配置页粘贴:',t);},"
    "function(){prompt('请手动全选复制:',t);});}"
    "catch(e){prompt('请手动全选复制:',t);}"
    "})()"
)


def parse_credential(text):
    """从粘贴内容里提取 token: 支持完整 cookie 串 / nio-account-info / Bearer / 裸 token。"""
    if not text:
        return None
    text = text.strip()
    import re
    m = re.search(r"nio-account-info=([^;\s\"']+)", text)
    if m:
        raw = urllib.parse.unquote(m.group(1))
        try:
            obj = json.loads(raw)
            token = obj.get("access_token") or obj.get("token")
            if token:
                return str(token)
        except ValueError:
            if raw and "." in raw:
                return raw
    m = re.search(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}", text)
    if m:
        return m.group(0)
    m = re.search(r"Bearer\s+([A-Za-z0-9_\-\.]{40,})", text)
    if m:
        return m.group(1)
    m = re.search(r"[A-Za-z0-9_\-]{60,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}", text)
    if m:
        return m.group(0)
    return None


def load_accounts():
    if not os.path.isfile(ACCOUNTS_PATH):
        return []
    try:
        with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("accounts", [])
        return [i for i in items if isinstance(i, dict)]
    except (OSError, ValueError):
        return []


def save_accounts(accounts):
    with open(ACCOUNTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"accounts": accounts}, f, ensure_ascii=False, indent=2)


def render_page():
    cfg = checkin.load_global_config()
    accounts = checkin.load_accounts(cfg)
    rows = []
    for acc in accounts:
        st = checkin.read_state(cfg, acc["alias"])
        status = st.get("status", "new")
        mark = {"success": "✅", "already": "☑️"}.get(status, "⚠️" if status in ("fail", "auth_fail", "rate_limited", "no_token") else "·")
        rows.append(
            "<tr><td>%s</td><td>%s %s</td><td>%s</td><td>连续 %s / 累计 %s</td><td>%s</td>"
            "<td><form method='post' action='/run' class='inline'><input type='hidden' name='alias' value='%s'>"
            "<button type='submit'>立即签到</button></form> "
            "<form method='post' action='/del' class='inline'><input type='hidden' name='alias' value='%s'>"
            "<button type='submit' class='warn'>删除</button></form></td></tr>" % (
                escape(acc["alias"]), mark, escape(status),
                escape(st.get("last_run", "—")),
                escape(str(st.get("streak", "—"))), escape(str(st.get("total", "—"))),
                escape(st.get("day", "—")),
                escape(acc["alias"]), escape(acc["alias"])))
    if not rows:
        rows.append("<tr><td colspan='6'>还没有账号。先登录 www.nio.cn, 然后用书签工具或下方粘贴框添加。</td></tr>")
    bm = "javascript:" + urllib.parse.quote(BOOKMARKLET_JS, safe="()+=:.'%&*#!?[]/, ")
    tail = ""
    log_path = os.path.join(cfg["data_dir"], "checkin.log")
    if os.path.isfile(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-40:]
            tail = "".join(escape(l) for l in reversed(lines))
        except OSError:
            pass
    return PAGE_TEMPLATE % {
        "rows": "".join(rows),
        "bookmarklet": bm,
        "log": tail or "暂无日志",
    }


PAGE_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>蔚来签到 · 本地配置页</title>
<style>
body{font:14px/1.6 system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#222}
h1{font-size:20px}h2{font-size:16px;margin-top:28px}
table{border-collapse:collapse;width:100%%}td,th{border:1px solid #ddd;padding:6px 8px;text-align:left;font-size:13px}
th{background:#f5f5f5}
button{padding:4px 10px;cursor:pointer}
button.warn{color:#a11;background:none;border:1px solid #ddd}
.inline{display:inline;margin:0}
textarea{width:100%%;height:72px;box-sizing:border-box}
.tip{color:#666;font-size:13px}
code{background:#f4f4f4;padding:1px 5px;border-radius:4px}
a.bm{display:inline-block;padding:5px 12px;border:1px dashed #888;border-radius:6px;text-decoration:none;color:#036}
.card{border:1px solid #e3e3e3;border-radius:10px;padding:14px 16px;margin:12px 0}
#log{background:#111;color:#9f9;padding:10px;font:12px/1.5 monospace;max-height:280px;overflow:auto;white-space:pre-wrap}
</style></head><body>
<h1>蔚来签到 · 本地配置页</h1>
<p class="tip">凭据只保存在本机 accounts.json，本页仅监听 127.0.0.1。请使用<b>你本人的账号</b>。</p>

<div class="card">
<h2>第一步：获取 token（本人操作，只需一次 / token 失效时重做）</h2>
<ol>
<li>电脑 Chrome 打开 <a href="https://www.nio.cn/" target="_blank">www.nio.cn</a>，右上角用<b>手机号验证码登录</b>（登录你自己的账号）。</li>
<li>回到本页，把右侧 <a class="bm" href="%(bookmarklet)s">📌 提取蔚来 Token</a> 链接<b>拖到浏览器书签栏</b>。</li>
<li>在已登录的 www.nio.cn 标签页点击该书签 → token 自动复制到剪贴板。</li>
<li>回到本页，粘贴到下面的框里，点「保存」。完成。</li>
</ol>
<p class="tip">书签没反应？也可以 F12 → 控制台粘贴下方代码后回车：<br>
<code id="code">把书签链接拖到地址栏按回车可查看代码；或直接粘贴 cookie 串到下面。</code></p>
</div>

<h2>账号状态</h2>
<table><tr><th>别名</th><th>状态</th><th>最近运行</th><th>天数</th><th>日期</th><th>操作</th></tr>%(rows)s</table>

<h2>添加 / 更新账号</h2>
<form method="post" action="/add">
<p>别名（同名为更新）：<input name="alias" placeholder="如：我的蔚来"></p>
<p><textarea name="cred" placeholder="粘贴 token / Bearer xxx / 含 nio-account-info 的整段 cookie"></textarea></p>
<p><button type="submit">保存到本地</button></p>
</form>

<h2>最近日志（不含任何凭据）</h2>
<div id="log">%(log)s</div>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, body, content_type="text/html; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self._send(render_page())
        elif path == "/healthz":
            self._send("ok", "text/plain")
        else:
            self._send("not found", "text/plain", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        path = urllib.parse.urlparse(self.path).path
        if path == "/add":
            alias = (form.get("alias", [""])[0] or "").strip()[:32] or "NIO"
            token = parse_credential(form.get("cred", [""])[0])
            if not token:
                self._send(PAGE_ERR % "没解析出 token：请粘贴 Bearer 值或包含 nio-account-info 的 cookie")
                return
            accounts = load_accounts()
            for acc in accounts:
                if str(acc.get("alias")) == alias:
                    acc["auth"] = token
                    break
            else:
                accounts.append({"alias": alias, "auth": token})
            save_accounts(accounts)
            self._send(PAGE_OK % (escape(alias),))
        elif path == "/del":
            alias = form.get("alias", [""])[0]
            save_accounts([a for a in load_accounts() if str(a.get("alias")) != alias])
            self._send(PAGE_OK % (escape(alias) + " 已删除",))
        elif path == "/run":
            alias = form.get("alias", [""])[0]
            try:
                proc = subprocess.run(
                    [sys.executable, os.path.join(BASE, "checkin.py"), "--once", "--force", "--account", alias],
                    capture_output=True, text=True, timeout=300, cwd=BASE)
                out = (proc.stdout or "") + (proc.stderr or "")
            except subprocess.TimeoutExpired:
                out = "签到执行超时，请稍后看日志确认结果"
            self._send(PAGE_RESULT % (escape(alias), escape(out[-2000:] or "无输出")))
        else:
            self._send("not found", "text/plain", 404)


PAGE_OK = """<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="2;url=/">
<body style="font:14px sans-serif"><p>✅ 账号 %s 已保存到本机 accounts.json，2 秒后返回…</p></body>"""

PAGE_ERR = """<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="4;url=/">
<body style="font:14px sans-serif"><p>❌ %s，4 秒后返回…</p></body>"""

PAGE_RESULT = """<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="6;url=/">
<body style="font:14px sans-serif"><p>账号 %s 触发签到，输出如下（6 秒后返回）：</p><pre style="white-space:pre-wrap;background:#111;color:#9f9;padding:10px">%s</pre></body>"""


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("配置页: http://%s:%d  (仅本机可访问, Ctrl+C 退出)" % (HOST, PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
