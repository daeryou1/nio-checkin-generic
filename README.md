# 蔚来账号自动签到程序（自托管通用版）

> **项目名**：`nio-checkin-generic`（仓库名用英文便于 git / 青龙 / Docker 引用，展示名即上方的中文全称）

> **声明（请先读）**：本项目是模拟 App 请求的个人自动化工具，不是官方功能。要求**使用你本人的账号、本人登录获取凭据、凭据只存在你自己的设备上**；不支持也不提供批量注册、代他人签到、绕过风控的能力。接口与风控随时可能变化，工具失效时脚本会通知你。是否使用请自行对照蔚来用户协议判断。

让每个蔚来车主在自己已有的设备上（N1 / NAS / 软路由 / 青龙 / Windows / 云服务器 / GitHub Actions / WorkBuddy 定时任务）跑起来：**本人验证码登录一次，之后全自动**。

## 特性

- **凭据自主可控**：token 由你本人登录 www.nio.cn 获取，只写本地 `accounts.json`，不上传、不代签
- **一键授权**：本地 Web 配置页 + 书签工具，token 失效时点一下书签就能更新，不需要抓包
- **多账号**：家人账号也能一起管，每账号独立时间/通知/状态
- **错峰抖动**：每账号叠加当天固定的随机偏移（默认 0–20 分钟），避免集体同一秒打接口
- **零第三方依赖**：单文件 Python，3.8+ 直接跑，Docker/青龙/无 Docker 通吃
- **结果通知**：企微机器人 / Server酱 / Bark / PushPlus / 钉钉 / 飞书 / Telegram / 自定义 webhook
- **克制且安全**：当天确认成功不再请求；只对明确失败有限重试；429 按 Retry-After；禁止跟随跳转；日志/通知永不输出 token

## 快速开始（3 分钟）

### 1. 拿 token（本人操作，只需一次）

1. 电脑 Chrome 打开 `https://www.nio.cn/`，右上角**手机号验证码登录你自己的账号**
2. 在本项目目录运行 `python server.py`，打开 `http://127.0.0.1:18923`
3. 把配置页里的「📌 提取蔚来 Token」书签拖到书签栏 → 在已登录的 nio.cn 标签页点它 → token 自动进剪贴板
4. 回配置页粘贴 → 保存。完成

> 网页 token 若不被签到接口接受（401），需要 App 凭据：手机抓包（Reqable/Charles）取 `authorization` 请求头，粘进配置页即可，同样只需一次。

### 2. 验证

```sh
python checkin.py --self-test        # 离线自检
python checkin.py --once --force     # 真实签一次，看到「签到已确认 ✅」即通
```

### 3. 选一个常驻方式

| 你有什么 | 怎么部署 | 文档 |
|---|---|---|
| N1 / NAS / 任何 Docker 设备 | `docker compose up -d --build` | 本页下方 |
| 青龙面板 | 订阅仓库或复制脚本 + 环境变量 | [examples/qinglong.md](examples/qinglong.md) |
| 电脑会每天开机 | Windows 计划任务 / crontab | [examples/plain-python.md](examples/plain-python.md) |
| 什么都不想装 | GitHub Actions（token 进 Secrets，有上云风险） | [examples/github-actions.md](examples/github-actions.md) |
| 用 WorkBuddy | 定时任务跑本地脚本 | [examples/workbuddy-automation.md](examples/workbuddy-automation.md) |

### Docker 部署

```sh
# 把 checkin.py / server.py / Dockerfile / docker-compose.yml / accounts.json 放到设备如 /opt/nio-checkin/
cd /opt/nio-checkin
docker compose up -d --build            # 常驻签到
docker compose --profile web up -d      # 可选: 再起 Web 配置页 (127.0.0.1:18923)
```

- 默认桥接网络。个别软路由（如 N1/iStoreOS）桥接出站被透明代理拦截时，解开 compose 里的 `network_mode: host`
- 拉不动 `python:3.12-alpine` 是 Docker Hub 网络问题，配国内镜像加速即可；N1(arm64) 原生支持

## 配置

账号在 `accounts.json`（推荐，见 `accounts.example.json`），或 `.env` 的 `NIO_AUTH`（兼容青龙：多账号换行/`&` 分隔）。全局默认在 `.env` 或可选的 `config.json`：

| 变量 | 默认 | 说明 |
|---|---|---|
| `NIO_HOUR` / `NIO_MINUTE` | 09:03 | 每日基准时间（每账号可单独覆盖） |
| `NIO_JITTER` | 20 | 每账号随机偏移分钟数（当天固定、账号错开），0 关闭 |
| `NIO_MAX_RETRY` / `NIO_RETRY_GAP` | 3 / 30 | 当天失败重试次数与间隔 |
| `NIO_NOTIFY_URL` | 空 | 通知 webhook（自动识别平台） |
| `NIO_NOTIFY_DAILY` | 1 | 成功是否也推送 |

多账号用 `checkin.py --list` 看各账号状态，`--set-token 别名 token` 更新凭据。

## 接口变了怎么办

端点、参数、UA、结果码全部外置在 `config.json` 的 `protocol` 段，接口修订只改配置，不动代码。脚本对未知响应一律按「未确认」处理并通知，不会把失败误判成成功。

## 设计原则

1. **一人一凭据、凭据不出设备**——token 等同账号登录凭据，只放本地，别发聊天/网盘/Git
2. **本人操作**——登录、扫码、验证码环节永远由账号主人完成，程序只保存结果
3. **群体礼仪**——随机抖动 + 有限重试 + 禁止并发轰炸接口，一个人用是方便，一群人用也要不惊动风控

## FAQ

- **token 多久失效？** 不确定（与蔚来服务端策略有关）。失效时脚本推送「凭据失效」，点一次书签重新提取粘贴即可，全程 1 分钟
- **会不会重复签？** 不会。当天确认成功/服务端返回已签到都会记录并跳过；多设几个兜底时间也安全
- **和 Surge/QuantumultX 重写脚本、青龙 weilai.js 有什么区别？** 那些依赖抓包工具取 token 且过期要重新抓包；本项目面向没有抓包条件的普通车主，体验是「网页验证码登录一次 + 书签一键更新」，并且可在无 Mac 代理软件的设备上常驻
- **网页登录的 token 和 App token 一样有效吗？** 网页 cookie `nio-account-info` 里的 `access_token` 实测可被签到接口接受（2026-11 验证）；若后续接口校验 App 专属头，再用抓包取 App 凭据

## 删除我的数据

所有数据都在你自己手里，随时可删干净。**本项目没有服务端**——不存在任何「存在作者那里」的你的数据，仓库里只有代码。

| 位置 | 怎么删 |
|---|---|
| 本机凭据 | 删除 `accounts.json`、`.env`（建议同时在蔚来 App / 网页里退出登录以吊销会话） |
| 本机运行记录 | 删除 `data/` 目录（日志、心跳、状态文件） |
| Docker | `docker compose down -v` 并删除部署目录 |
| 青龙 | 删除环境变量（`NIO_AUTH` 等）+ 删除脚本与运行日志 |
| GitHub Actions | 删除 Secrets（`NIO_AUTH`、`NIO_NOTIFY_URL`）并可删除 fork 仓库 |
| 浏览器书签工具 | 直接删除该书签 |

## 联系与反馈

- **Bug / 接口变更 / 功能建议**：[GitHub Issues](../issues)。反馈接口变更时请附服务端返回的 `result_code` 与 HTTP 状态码即可，**绝不要附 token、cookie 或任何请求头原文**
- **安全漏洞**：不要公开 Issue，请使用 GitHub 的私密漏洞报告（仓库 Security 标签 → Report a vulnerability），见 [SECURITY.md](SECURITY.md)

## 免责声明

1. 本项目是面向个人自动化便利的开源工具，**与蔚来（NIO）官方无任何隶属、合作或授权关系**，未获得任何官方支持或认可
2. 签到通过模拟客户端请求实现，属非官方接口使用；蔚来可能随时变更接口、参数或风控策略导致工具失效，由此产生的签到中断、积分损失等影响由使用者自行承担
3. 使用者应仅使用**本人账号**，并自行对照蔚来 App 用户协议评估使用合规性；对将本工具用于批量注册、代他人签到、绕过风控等违反平台规则或法律法规的用途，作者明确不支持且不承担任何责任
4. 软件按「现状」提供，不含任何明示或默示担保；因使用或无法使用本软件导致的任何直接或间接损失，作者不承担责任，详见 [LICENSE](LICENSE)
5. 若权利人认为本项目侵犯其合法权益，请通过上方联系渠道告知，将尽快处理（修改或下架）

## 许可

[MIT](LICENSE)。本项目与蔚来官方无任何关联。
