# Windows / macOS / Linux 无 Docker 部署

## 1. 安装

只要系统里有 Python 3.8+（零第三方依赖），把这两个文件放进任意目录，如 `D:\nio-checkin\`：

- `checkin.py`
- `accounts.json`（由 `accounts.example.json` 复制改名，填入你的 token）

## 2. 先自检 + 手动验证

```sh
python checkin.py --self-test        # 离线自检
python checkin.py --once --force     # 真实签到一次验证凭据
```

## 3a. Windows 计划任务

管理员 PowerShell（或「任务计划程序」图形界面）：

```powershell
$action  = New-ScheduledTaskAction -Execute "python" -Argument "D:\nio-checkin\checkin.py --once" -WorkingDirectory "D:\nio-checkin"
$trigger = New-ScheduledTaskTrigger -Daily -At "09:03"
Register-ScheduledTask -TaskName "NIO签到" -Action $action -Trigger $trigger
```

脚本自带当日去重，可再建 13:03 / 20:03 两个触发器兜底，不会重复签。

## 3b. Linux / NAS crontab

```sh
python3 checkin.py --self-test
crontab -e
3 9,13,20 * * * cd /opt/nio-checkin && python3 checkin.py --once >> data/cron.log 2>&1
```

## 4. 更新 token

```sh
python checkin.py --set-token 我的蔚来 "eyJ..."
```

或直接编辑 `accounts.json`。
