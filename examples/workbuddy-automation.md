# WorkBuddy 定时任务接入

没有常开设备、但电脑每天会开机的用户，可以用 WorkBuddy 的定时任务（自动化）驱动本地脚本。

## 创建自动化

对 WorkBuddy 说一句话即可创建，提示词模板（一次性配置）：

> 每天上午 9 点半左右执行一次：在 `E:\WorkBuddy\nio-checkin-generic` 目录运行 `python checkin.py --once`，把 heartbeat.json 的状态汇总告诉我；如果状态是 auth_fail 就提醒我重新登录 www.nio.cn 更新 token。

注意事项：

- 脚本自带当日去重，自动化每天触发多次也不会重复签。
- 电脑关机那天不会签到（这是本方式唯一短板，介意就用 N1/NAS/GitHub Actions）。
- 凭据仍在本地 accounts.json，WorkBuddy 只执行命令，不上传任何东西。
