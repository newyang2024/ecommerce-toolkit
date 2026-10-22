# 项目约定

## 目标与目录

本仓库用于维护电商数据工具。当前可运行项目在 `marketing-calendar/`：从万相台下载五类报表，并将数据写入用户提供的 Excel 日报表底本。保留现有 Python、Tkinter、Playwright 和 Windows Excel 方案；仅在需求明确时调整架构。

- `marketing-calendar/marketing_calendar/`：程序代码。
- `marketing-calendar/tests/`：单元测试。
- `marketing-calendar/config/config.example.json`：可提交的配置示例。
- `marketing-calendar/README.md` 与 `迁移说明.md`：运行、迁移说明。
- `marketing-calendar/data/`、`output/`、`logs/`、本机配置、真实工作簿与 CSV：仅保存在本机，不提交。

## 运行与测试

在 `marketing-calendar/` 中执行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py check
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe main.py gui
```

完整整理及透视表刷新需要 Windows、Microsoft Edge、桌面版 Microsoft Excel 和用户提供的日报表底本。浏览器登录及网站安全验证由用户手动完成；不要绕过验证或在提交结果不明确时重复创建下载任务。

## 数据、密钥与网络

不得将账号密码、Cookie、浏览器配置、下载的报表、真实客户底本、日志或密钥提交到仓库。不要把个人电脑的绝对路径写入代码或默认配置。网络请求保持直连：不读取系统代理或代理环境变量；requests/httpx 使用 `trust_env=False`，Playwright 使用 `direct://` 并维持现有直连启动设置。不得写入代理地址或固定本机 IP。日志不能记录凭据、Cookie 或完整请求头。

## 维护流程

开始新功能前先同步 `origin/main`、检查 Git 状态与已有改动。保留用户未提交的修改，在功能分支实施并运行相关测试，更新必要文档，再提交、推送并尽可能创建 Pull Request。远程仓库已有文件不能因迁移或更新而被覆盖；本仓库是后续代码维护的唯一来源，旧的非 Git 工作目录只用于核对和保留历史资料。
