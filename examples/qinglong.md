# 青龙面板部署

## 方式一：拉仓库（推荐）

青龙面板 → 订阅管理 → 新建订阅：

```
https://github.com/<你的用户名>/nio-checkin-generic
```

（Fork 本仓库后填你自己的 fork 地址，或手动复制脚本）

类型选「script」，定时 `0 9 * * *`（脚本内部还会再叠加随机抖动）。

## 方式二：直接复制脚本

把 `checkin.py` 内容粘贴到青龙 → 脚本管理 → 新建 `nio_checkin.py`。

## 环境变量

青龙 → 环境变量 → 新建：

| 变量名 | 值 | 说明 |
|---|---|---|
| `NIO_AUTH` | `Bearer eyJ...`，多账号用 `&` 或换行分隔 | 兼容青龙圈 `&` 分隔多账号的习惯，别名自动 NIO1/NIO2… |
| `NIO_UA` | （可选）抓包 UA | 留空用内置 |
| `NIO_NOTIFY_URL` | （可选）通知 webhook | 支持企微机器人/Server酱/Bark/PushPlus/钉钉/飞书/Telegram |

## 定时任务

```
任务命令: task nio_checkin.py once
定时规则: 3 9 * * *
```

`--once` 模式当天成功自动跳过，多设几个兜底时间也不会重复签（如 `3 9,13,20 * * *`）。

## token 更新

青龙报 401/凭据失效时：电脑登录 www.nio.cn → 用书签工具提取新 token → 编辑 `NIO_AUTH` 环境变量即可。
