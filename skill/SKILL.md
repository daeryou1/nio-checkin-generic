---
name: nio-checkin
description: 蔚来(NIO)每日自动签到部署助手。用户想给蔚来账号配置自动签到、查询签到状态、更新 token 或把签到部署到 Docker/NAS/N1/青龙/计划任务/GitHub Actions 时使用。凭据必须由用户本人登录获取并只存本地，助手不得索要或转发用户 token。
---

# 蔚来自动签到助手

核心脚本：`scripts/checkin.py`（零依赖 Python 3.8+）。配置页：`scripts/server.py`。

## 工作流程

1. **判断部署目标**：问清用户要部署到哪（Docker / N1 等软路由 / NAS / 青龙 / Windows 计划任务 / GitHub Actions / WorkBuddy 定时任务）。参照仓库 `examples/` 各文档。
2. **准备文件**：把 `scripts/checkin.py` 复制到用户选定的目录（Windows 默认放 `E:\WorkBuddy\nio-checkin\`），生成 `accounts.json`（参考 `scripts/accounts.example.json`）。
3. **凭据获取（必须本人操作）**：
   - 让用户打开 `python server.py` → http://127.0.0.1:18923 ，页面里有完整引导；
   - 用户自己用手机验证码登录 www.nio.cn，用页面里的书签工具提取 token 后粘贴回配置页；
   - **助手不得索要、查看、转录或转发用户 token**；用户坚持让你代填时，用 `checkin.py --set-token 别名 token`，且不回显 token 内容。
4. **验证**：运行 `python checkin.py --once --force` 看输出是否「签到已确认 ✅」。
5. **常驻化**：按目标平台装 Docker compose / crontab / 计划任务；软路由注意桥接网络被透明代理拦截时改 `network_mode: host`。
6. **故障排查**：
   - `auth_fail` → 引导重新登录+书签更新 token；
   - `rate_limited` → 加大 `NIO_JITTER`、错开时间；
   - 网络异常 → 检查代理/出站，不要盲目重试 POST。

## 红线

- 不代用户登录、不批量注册、不绕过风控；一人一账号凭据、留存本地。
- 不把 token 写进任何会离开本机的位置（聊天记录、网盘、远程日志）。
- 接口变更时只改 `config.json` 的 `protocol` 段，不要乱动核心逻辑。
