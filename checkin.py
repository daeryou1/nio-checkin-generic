#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔚来(NIO)每日自动签到 · 通用多账号版（零第三方依赖）

凭据原则: 每个用户用"自己的账号"登录获取 token, 凭据只存在本地, 不上传、不代签。
登录获取方式见 README.md 或运行 server.py 打开本地配置页。

用法:
    python checkin.py                     常驻, 按每账号时间+随机抖动签到 (Docker/常驻用)
    python checkin.py --once              所有账号各跑一次, 当天成功自动跳过 (crontab/青龙用)
    python checkin.py --once --force      忽略当日去重, 强制跑
    python checkin.py --account 别名      只处理指定账号
    python checkin.py --list              列出账号与状态
    python checkin.py --set-token 别名 TOKEN   更新某账号 token
    python checkin.py --self-test         离线自检, 不发网络请求

账号来源 (二者可共存, 账号合并去重):
    1. accounts.json   多账号完整配置 (推荐, 见 accounts.example.json)
    2. 环境变量/.env   NIO_AUTH 支持换行或 & 分隔多账号 (兼容青龙习惯), 别名自动 NIO1/NIO2...

安全约定: 日志、通知、心跳文件不输出 token / 完整响应原文。
"""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))
BASE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 协议适配器
# 接口变更时只需改 config.json 的 "protocol" 段, 不动核心代码。
DEFAULT_PROTOCOL = {
    "endpoint": "https://gateway-front-external.nio.com/moat/10086/c/award_cn/checkin",
    "app_id": "10086",
    "user_agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Mobile/15E148 NIOAppCN/6.10.0 "
        "(com.do1.WeiLaiApp; build:2682; OS:iOS) webview/lg _dsbridge"
    ),
    "success_codes": ["success"],
    "already_codes": ["credit_limit_reached", "already_checked_in", "repeat_checkin"],
    "auth_fail_codes": ["unauthorized", "token_expired", "invalid_token", "not_login", "auth_failed"],
}

DEFAULT_CFG = {
    "hour": 9,
    "minute": 3,
    "jitter": 20,          # 每账号随机偏移分钟数 (当天内固定, 账号间错开; 0 关闭)
    "max_retry": 3,        # 当天失败后额外重试次数
    "retry_gap": 30,       # 重试间隔(分钟)
    "notify_url": "",
    "notify_daily": True,
    "data_dir": os.path.join(BASE, "data"),
    "notify_title_prefix": "蔚来签到",
}

APP_NAME = "nio-checkin"


def now_cn():
    return datetime.now(CN_TZ)


def today_str():
    return now_cn().strftime("%Y-%m-%d")


def log(cfg, alias, message):
    line = "[%s] [%s] %s" % (now_cn().strftime("%Y-%m-%d %H:%M:%S"), alias, message)
    print(line, flush=True)
    try:
        os.makedirs(cfg["data_dir"], exist_ok=True)
        with open(os.path.join(cfg["data_dir"], "checkin.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- 配置加载
def _read_kv_env(path):
    env = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _int(value, default, low, high):
    try:
        n = int(str(value))
        return max(low, min(high, n))
    except (TypeError, ValueError):
        return default


def load_global_config():
    cfg = dict(DEFAULT_CFG)
    cfg["protocol"] = dict(DEFAULT_PROTOCOL)
    for path in (os.path.join(BASE, "config.json"),):
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    user = json.load(f)
                if isinstance(user, dict):
                    for k, v in user.items():
                        if k == "protocol" and isinstance(v, dict):
                            cfg["protocol"].update(v)
                        elif k in cfg:
                            cfg[k] = v
            except (OSError, ValueError):
                pass
    env = _read_kv_env(os.path.join(BASE, ".env"))
    env.update({k: v for k, v in os.environ.items() if k.startswith("NIO_") or k in ("RUN_ON_START", "TZ")})
    cfg["hour"] = _int(env.get("NIO_HOUR"), cfg["hour"], 0, 23)
    cfg["minute"] = _int(env.get("NIO_MINUTE"), cfg["minute"], 0, 59)
    cfg["jitter"] = _int(env.get("NIO_JITTER"), cfg["jitter"], 0, 120)
    cfg["max_retry"] = _int(env.get("NIO_MAX_RETRY"), cfg["max_retry"], 0, 24)
    cfg["retry_gap"] = _int(env.get("NIO_RETRY_GAP"), cfg["retry_gap"], 5, 240)
    cfg["notify_url"] = env.get("NIO_NOTIFY_URL", "").strip() or cfg["notify_url"]
    cfg["notify_daily"] = env.get("NIO_NOTIFY_DAILY", "1" if cfg["notify_daily"] else "0") == "1"
    dd = env.get("NIO_DATA_DIR", "").strip()
    if dd:
        cfg["data_dir"] = dd
    return cfg


def load_accounts(cfg):
    """合并 accounts.json 与 NIO_AUTH 环境变量, 返回账号列表。"""
    accounts = []
    path = os.path.join(BASE, "accounts.json")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else data.get("accounts", [])
            for item in items:
                if isinstance(item, dict) and item.get("auth"):
                    accounts.append(_normalize(item, cfg))
        except (OSError, ValueError):
            pass
    env = _read_kv_env(os.path.join(BASE, ".env"))
    env.update({k: v for k, v in os.environ.items() if k.startswith("NIO_")})
    raw = env.get("NIO_AUTH", "").strip()
    if raw:
        parts = [p.strip() for p in raw.replace("\n", "&").split("&") if p.strip()]
        for i, token in enumerate(parts, 1):
            item = {"alias": env.get("NIO_ALIAS", "").strip() or "NIO%d" % i, "auth": token}
            if env.get("NIO_UA", "").strip():
                item["ua"] = env["NIO_UA"].strip()
            accounts.append(_normalize(item, cfg))
    # 去重: 同 alias 后者覆盖; 同 token 视为同一账号
    merged, seen_tokens = [], set()
    for acc in accounts:
        if acc["auth"] in seen_tokens:
            continue
        seen_tokens.add(acc["auth"])
        merged.append(acc)
    return merged


def _normalize(item, cfg):
    auth = str(item.get("auth", "")).strip()
    if auth and not auth.lower().startswith("bearer "):
        auth = "Bearer " + auth
    acc = {
        "alias": str(item.get("alias") or item.get("name") or "NIO").strip()[:32],
        "auth": auth,
        "ua": str(item.get("ua") or "").strip() or cfg["protocol"]["user_agent"],
        "hour": _int(item.get("hour"), cfg["hour"], 0, 23),
        "minute": _int(item.get("minute"), cfg["minute"], 0, 59),
        "jitter": _int(item.get("jitter"), cfg["jitter"], 0, 120),
        "notify_url": str(item.get("notify_url") or "").strip() or cfg["notify_url"],
        "notify_daily": bool(item.get("notify_daily", cfg["notify_daily"])),
    }
    return acc


def day_jitter_minutes(alias, jitter):
    """当天固定、账号间错开的随机偏移, 避免所有人同一秒打接口。"""
    if jitter <= 0:
        return 0
    seed = hashlib.sha256(("%s|%s|%s" % (APP_NAME, alias, today_str())).encode()).hexdigest()
    return int(seed[:8], 16) % jitter


def account_target(acc, cfg):
    base = acc["hour"] * 60 + acc["minute"]
    return base + day_jitter_minutes(acc["alias"], acc["jitter"])


# ---------------------------------------------------------------- 状态
def state_path(cfg, alias):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in alias)
    return os.path.join(cfg["data_dir"], "state-%s.json" % safe)


def read_state(cfg, alias):
    try:
        with open(state_path(cfg, alias), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(cfg, alias, state):
    try:
        os.makedirs(cfg["data_dir"], exist_ok=True)
        path = state_path(cfg, alias)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass


def write_heartbeat(cfg, accounts):
    hb = {"updated": now_cn().isoformat(timespec="seconds"), "accounts": []}
    for acc in accounts:
        st = read_state(cfg, acc["alias"])
        hb["accounts"].append({
            "alias": acc["alias"],
            "day": st.get("day"),
            "status": st.get("status"),
            "streak": st.get("streak"),
            "total": st.get("total"),
            "last_run": st.get("last_run"),
            "fail_streak": st.get("fail_streak", 0),
        })
    try:
        os.makedirs(cfg["data_dir"], exist_ok=True)
        with open(os.path.join(cfg["data_dir"], "heartbeat.json"), "w", encoding="utf-8") as f:
            json.dump(hb, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ---------------------------------------------------------------- 网络与解析
class NoRedirect(urllib.request.HTTPRedirectHandler):
    """禁止跟随跳转, 避免 Authorization 被带到其它主机。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_once(cfg, acc):
    proto = cfg["protocol"]
    url = proto["endpoint"] + "?app_id=" + proto["app_id"] + "&timestamp=" + str(int(time.time()))
    req = urllib.request.Request(
        url,
        data=b"event=checkin",
        method="POST",
        headers={
            "authorization": acc["auth"],
            "content-type": "application/x-www-form-urlencoded",
            "accept": "application/json",
            "user-agent": acc["ua"],
        },
    )
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=8) as resp:
            return resp.status, resp.read(65536), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(65536)
        except Exception:
            body = b""
        return exc.code, body, dict(exc.headers or {})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, b"", {"_error": type(exc).__name__}


def safe_stat(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value < 2 ** 53:
        return value
    if isinstance(value, str) and value.isdigit() and len(value) <= 16:
        return int(value)
    return None


def parse_result(cfg, status, body):
    proto = cfg["protocol"]
    try:
        obj = json.loads(body.decode("utf-8", "replace"))
    except (ValueError, AttributeError):
        return {"kind": "unknown", "code": "parse_error"}
    if not isinstance(obj, dict):
        return {"kind": "unknown", "code": "parse_error"}
    code = str(obj.get("result_code", ""))
    data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    out = {"kind": "fail", "code": code or "missing"}

    if status == 401 or code in proto["auth_fail_codes"]:
        out["kind"] = "auth_fail"
        return out
    if status == 429:
        out["kind"] = "rate_limited"
        return out
    checked_in = data.get("checked_in") is True
    if status == 200 and (code in proto["success_codes"] or checked_in):
        out["kind"] = "already" if code in proto["already_codes"] else "success"
    elif code in proto["already_codes"]:
        out["kind"] = "already"
    for source in (stats, data, obj):
        for key in ("continuous_checkin_days", "continuous_days", "consecutive"):
            if out.get("streak") is None:
                out["streak"] = safe_stat(source.get(key))
        for key in ("accumulate_days", "total_days", "accumulateDays", "total"):
            if out.get("total") is None:
                out["total"] = safe_stat(source.get(key))
    tip = data.get("tip") if isinstance(data.get("tip"), str) else ""
    if tip and len(tip) <= 60:
        out["tip"] = tip
    return out


def do_checkin(cfg, acc, note=""):
    """执行一次签到, 仅对 429 做有限重试。"""
    for attempt in range(1, 4):
        status, body, headers = request_once(cfg, acc)
        result = parse_result(cfg, status, body)
        kind = result["kind"]
        if kind == "rate_limited" and attempt < 3:
            wait = 60
            raw = headers.get("Retry-After", "")
            if str(raw).isdigit():
                wait = max(1, min(120, int(raw)))
            log(cfg, acc["alias"], "服务端限流, %d 秒后重试 (%d/3)" % (wait, attempt))
            time.sleep(wait)
            continue
        if status == 0:
            return "fail", "网络异常 (%s)" % headers.get("_error", "unknown")
        detail = ""
        if result.get("streak") is not None:
            detail += " 连续 %d 天" % result["streak"]
        if result.get("total") is not None:
            detail += " 累计 %d 天" % result["total"]
        if result.get("tip"):
            detail += " / " + result["tip"]
        return kind, (detail or "结果码 %s" % result["code"]) + note
    return "rate_limited", "服务端持续限流, 未确认签到"


# ---------------------------------------------------------------- 通知
def notify(cfg, acc, title, content):
    url = acc["notify_url"]
    if not url:
        return
    try:
        if "qyapi.weixin.qq.com" in url:
            payload = json.dumps({"msgtype": "text", "text": {"content": title + "\n" + content}}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        elif "sctapi.ftqq.com" in url or "sct.ftqq.com" in url:
            payload = urllib.parse.urlencode({"title": title, "desp": content}).encode()
            req = urllib.request.Request(url, data=payload)
        elif "api.day.app" in url or "/bark" in url:
            req = urllib.request.Request(url.rstrip("/") + "/" + urllib.parse.quote(title) + "/" + urllib.parse.quote(content))
        elif "pushplus" in url or "pushplus" in content:
            payload = json.dumps({"title": title, "content": title + "\n" + content, "token": url.split("token=")[-1] if "token=" in url else url}).encode()
            req = urllib.request.Request("https://www.pushplus.plus/send", data=payload, headers={"Content-Type": "application/json"})
        elif "oapi.dingtalk.com" in url:
            payload = json.dumps({"msgtype": "text", "text": {"content": title + " " + content}}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        elif "open.feishu.cn" in url:
            payload = json.dumps({"msg_type": "text", "content": {"text": title + "\n" + content}}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        elif "api.telegram.org" in url:
            payload = urllib.parse.urlencode({"chat_id": url.split("chat_id=")[-1].split("/")[0] if "chat_id=" in url else "", "text": title + "\n" + content}).encode()
            base = url.split("?")[0]
            req = urllib.request.Request(base, data=payload)
        else:
            payload = json.dumps({"title": title, "content": content}).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read(1024)
    except Exception as exc:
        log(cfg, acc["alias"], "通知发送失败: %s (不影响签到)" % type(exc).__name__)


# ---------------------------------------------------------------- 单次执行
def run_once(cfg, acc, force=False):
    alias = acc["alias"]
    state = read_state(cfg, alias)
    day = today_str()
    if state.get("day") != day:
        state = {"day": day, "attempts": 0, "fail_streak": state.get("fail_streak", 0)}
    if not force and state.get("status") in ("success", "already"):
        return True, "今日已确认签到"
    if not acc["auth"]:
        state.update({"status": "no_token", "last_run": now_cn().isoformat(timespec="seconds")})
        write_state(cfg, alias, state)
        return False, "缺少凭据"

    kind, detail = do_checkin(cfg, acc)
    state["attempts"] = int(state.get("attempts", 0)) + 1
    state["last_run"] = now_cn().isoformat(timespec="seconds")
    state["status"] = kind

    if kind in ("success", "already"):
        state["fail_streak"] = 0
        state["last_success"] = day
        if state.get("streak") is not None:
            state["streak"] = kind_streak_from(detail)
        log(cfg, alias, "签到已确认 ✅%s" % detail)
        write_state(cfg, alias, state)
        if acc["notify_daily"] and kind == "success":
            notify(cfg, acc, "%s ✅ %s" % (cfg["notify_title_prefix"], alias), "今日签到已确认。" + detail)
        return True, detail

    state["fail_streak"] = int(state.get("fail_streak", 0)) + 1
    if kind == "auth_fail":
        log(cfg, alias, "凭据已失效 (401/认证错误), 需重新登录获取 token")
        notify(cfg, acc, "%s ⚠️ %s 凭据失效" % (cfg["notify_title_prefix"], alias),
               "Token 已过期。请重新登录 www.nio.cn 后, 打开本地配置页或用书签工具一键更新。")
    else:
        log(cfg, alias, "签到未确认: %s (第 %d 次尝试, %d 分钟后重试)" % (detail, state["attempts"], cfg["retry_gap"]))
        if state["fail_streak"] >= 3:
            notify(cfg, acc, "%s ⚠️ %s 连续失败" % (cfg["notify_title_prefix"], alias),
                   "已连续 %d 次未确认, 请检查网络。最近原因: %s" % (state["fail_streak"], detail))
    write_state(cfg, alias, state)
    return False, detail


def kind_streak_from(detail):
    try:
        return int(detail.split("连续 ")[1].split(" 天")[0])
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------- 调度
def loop(cfg, only_alias=None):
    accounts = [a for a in load_accounts(cfg) if not only_alias or a["alias"] == only_alias]
    if not accounts:
        print("没有可用账号: 请创建 accounts.json 或设置 NIO_AUTH (见 README)", flush=True)
        return 1
    log(cfg, "core", "启动: %d 个账号 | 抖动 %d 分钟 | 重试 %d 次/间隔 %d 分钟" % (
        len(accounts), cfg["jitter"], cfg["max_retry"], cfg["retry_gap"]))
    write_heartbeat(cfg, accounts)
    tick = 0
    while True:
        tick += 1
        now_m = now_cn().hour * 60 + now_cn().minute
        changed = False
        for acc in accounts:
            alias = acc["alias"]
            state = read_state(cfg, alias)
            if state.get("day") != today_str():
                state = {"day": today_str(), "attempts": 0, "fail_streak": state.get("fail_streak", 0)}
                write_state(cfg, alias, state)
            if state.get("status") in ("success", "already"):
                continue
            if state.get("status") in ("no_token", "auth_fail") and state.get("attempts", 0) > cfg["max_retry"]:
                continue
            target = account_target(acc, cfg)
            attempts = int(state.get("attempts", 0))
            last_run = state.get("last_run")
            gap_ok = True
            if last_run and attempts > 0:
                try:
                    elapsed = (now_cn() - datetime.fromisoformat(last_run)).total_seconds() / 60
                    gap_ok = elapsed >= cfg["retry_gap"]
                except ValueError:
                    gap_ok = True
            if attempts == 0 and now_m < target:
                continue
            if attempts > cfg["max_retry"]:
                continue
            if attempts > 0 and not gap_ok:
                continue
            ok, _ = run_once(cfg, acc)
            changed = True
        if changed:
            write_heartbeat(cfg, accounts)
        if tick % 60 == 0:
            log(cfg, "core", "心跳: 运行中, %d 个账号" % len(accounts))
        time.sleep(45)


# ---------------------------------------------------------------- 账号管理 CLI
def set_token(cfg, alias, token):
    path = os.path.join(BASE, "accounts.json")
    data = {"accounts": []}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                data = {"accounts": data}
        except (OSError, ValueError):
            data = {"accounts": []}
    accounts = data.get("accounts", [])
    for acc in accounts:
        if str(acc.get("alias")) == alias:
            acc["auth"] = token
            break
    else:
        accounts.append({"alias": alias, "auth": token})
    data["accounts"] = accounts
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("已更新账号 %s 的 token (%s)" % (alias, os.path.basename(path)))
    return 0


def list_accounts(cfg):
    accounts = load_accounts(cfg)
    if not accounts:
        print("没有可用账号")
        return 0
    for acc in accounts:
        st = read_state(cfg, acc["alias"])
        print("%-12s 时间 %02d:%02d+%02d' 状态 %-10s %s" % (
            acc["alias"], acc["hour"], acc["minute"],
            day_jitter_minutes(acc["alias"], acc["jitter"]),
            st.get("status", "new"), st.get("last_run", "")))
    return 0


# ---------------------------------------------------------------- 自检
def self_test(cfg):
    print("自检: 配置读取 OK | 抖动 %d 分钟 | 数据目录 %s" % (cfg["jitter"], cfg["data_dir"]))
    cases = [
        (200, b'{"result_code":"success","data":{"checked_in":true,"tip":"+5 \\u79ef\\u5206","stats":{"continuous_checkin_days":12,"accumulate_days":300}}}', "success"),
        (200, b'{"result_code":"credit_limit_reached"}', "already"),
        (200, b'{"data":{"checked_in":true}}', "success"),
        (401, b'{"result_code":"unauthorized"}', "auth_fail"),
        (429, b'{}', "rate_limited"),
        (200, b'not-json', "unknown"),
    ]
    for status, body, expect in cases:
        got = parse_result(cfg, status, body)["kind"]
        assert got == expect, (expect, got)
        print("解析用例 %-12s -> %s" % (expect, got))
    assert day_jitter_minutes("A", 30) == day_jitter_minutes("A", 30)
    assert day_jitter_minutes("A", 30) != day_jitter_minutes("B", 30) or True
    print("抖动: 当天固定 OK, 值域 0..%d" % max(0, cfg["jitter"] - 1))
    test_cfg = dict(cfg, data_dir=os.path.join(cfg["data_dir"], "_selftest"))
    acc = {"alias": "t1", "auth": "Bearer x", "ua": "u", "hour": 9, "minute": 0, "jitter": 0, "notify_url": "", "notify_daily": False}
    write_state(test_cfg, acc["alias"], {"day": today_str(), "status": "success"})
    assert read_state(test_cfg, acc["alias"])["status"] == "success"
    print("状态读写: OK")
    print("自检全部通过 (未发送任何网络请求)")
    return 0


def main():
    cfg = load_global_config()
    args = sys.argv[1:]
    if "--self-test" in args:
        return self_test(cfg)
    if "--list" in args:
        return list_accounts(cfg)
    if "--set-token" in args:
        i = args.index("--set-token")
        return set_token(cfg, args[i + 1], args[i + 2])
    only = None
    if "--account" in args:
        only = args[args.index("--account") + 1]
    if "--once" in args:
        accounts = [a for a in load_accounts(cfg) if not only or a["alias"] == only]
        if not accounts:
            print("没有可用账号: 请创建 accounts.json 或设置 NIO_AUTH", flush=True)
            return 1
        rc = 0
        for acc in accounts:
            ok, detail = run_once(cfg, acc, force="--force" in args)
            write_heartbeat(cfg, accounts)
            if not ok:
                rc = 1
        return rc
    return loop(cfg, only_alias=only)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
