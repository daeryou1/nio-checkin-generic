# GitHub Actions 免机器托管版

> ⚠️ **凭据上云警告**：此方式会把 token 存到 GitHub Secrets（云端）。它仍是你自己账号下的私有凭据，但「凭据只留本地」的原则会被打破。只建议没有常开设备的用户使用，并接受该风险。

## 步骤

1. Fork 本仓库到你自己的 GitHub 账号。
2. 仓库 → Settings → Secrets and variables → Actions → New repository secret：
   - `NIO_AUTH`：粘贴完整 `Bearer eyJ...`（多账号用 `&` 分隔）
   - 可选：`NIO_NOTIFY_URL`（通知 webhook）
3. 仓库 → Actions → 启用 workflows。默认每天 UTC+8 09:03±20 分钟随机运行（在 workflow 里可改）。

## 原理

workflow 里执行 `python checkin.py --once`，状态只保存在当次运行中（Actions 无持久盘），因此**每天都会真实请求一次**——服务端返回「已签到」会记为成功，不会重复扣分/刷分，但无法做本地 state 去重与心跳文件。
