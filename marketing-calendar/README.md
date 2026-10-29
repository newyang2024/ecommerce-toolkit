# 营销日历工具

Windows 桌面工具：下载万相台计划、商品、内容、关键词、人群五类报表，将 CSV 写入用户提供的日报表底本，并刷新汇总透视表。沿用 Python、Tkinter、Playwright、Microsoft Edge 和桌面版 Excel。

## 安装与启动

需要 Python 3.10～3.13、Microsoft Edge、Microsoft Excel。首次安装：

若使用另行交付的“便携版 ZIP”，其中已经包含 Python 运行时，不用执行本节的 venv/pip 步骤；请按包内 [TXT 迁移说明](迁移说明_便携版.txt) 解压并运行。便携包由源码机执行 `python tools/build_portable.py` 生成，且不会包含真实业务文件。

```powershell
cd marketing-calendar
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config\config.example.json config\config.json
.venv\Scripts\python.exe main.py check
.venv\Scripts\python.exe main.py gui
```

也可双击 `启动营销日历工具.bat`，它优先使用本目录的 `.venv`。先在项目专用 Edge 手动登录，再在界面选择**包含最新匹配源、公式行足够的日报表底本**。网站出现验证时按界面提示人工处理。

五表下载分两段：先逐张设置筛选、提交并确认任务 ID，让网站并行生成；全部确认后统一进入下载管理页，优先下载已生成的报表并归档。提交状态不明确时暂停核对，不会自动重提；续跑沿用已确认的任务 ID。

下载管理页若只显示了部分异步列表行，程序会短时、只读地重新加载并查找已确认的任务 ID；仍找不到时暂停人工核对。提交按钮和下载按钮不会因超时自动重复点击。

透视表刷新会根据真实日期值而非固定日期文本格式定位筛选项；对模板中唯一的空白日期页筛选字段，兼容不同 Excel 版本在刷新前不暴露筛选项的表现。

已有五份 CSV 时，可只做本地整理；运行目录须含 `manifest.json` 和 `extracted/`：

```powershell
.venv\Scripts\python.exe main.py merge --run-dir "output\本次运行目录" --base-workbook "日报表底本的实际路径.xlsx" --output "output\本次运行目录\万相台日报表_新版本.xlsx"
```

输出文件不覆盖已有文件。详情及换电脑步骤见[迁移说明](迁移说明.md)。

## 检查

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe main.py check
```

真实工作簿、CSV、浏览器登录态、日志和本机配置均不进入 Git。当前整理流程校验报表列和日期，但匹配源中的型号、类目仍须按业务资料核对；报表站点的安全验证也需要人工完成。
