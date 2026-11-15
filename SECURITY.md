# 安全策略

## 如何报告安全问题

**请不要用公开 Issue 报告安全漏洞。**

请使用 GitHub 的私密漏洞报告：打开仓库 → Security 标签 → Report a vulnerability。
维护者会在 7 天内响应；修复前请勿公开细节。

## 关心的安全问题

- token / cookie 经日志、通知、错误输出、心跳文件意外泄漏
- HTTP 重定向或 SSRF 导致 Authorization 头外发到第三方主机
- 本地配置页（server.py）的 CSRF / 局域网暴露 / token 泄漏
- 依赖解析用户粘贴内容时的注入风险

## 项目自身的安全基线

- token 永不写入日志、通知、心跳文件；日志只记录结果码与统计数字
- 所有签到请求禁止跟随跨域跳转（`NoRedirect`）
- 配置页仅监听 `127.0.0.1`，凭据只落本地 `accounts.json`
- 项目无服务端、无遥测：不存在代码之外收集或存储用户数据的环节

## 用户侧建议

- `accounts.json`、`.env` 含账号凭据：不要提交 git、不要发聊天/网盘、权限设 600（Linux）
- 不在不可信设备上部署；GitHub Actions 方式会把 token 存入云端 Secrets，使用前评估接受度
