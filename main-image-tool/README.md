# 主图识别工具

读取本地链接库里的竞品天猫商品链接，自动打开商品详情页，定位营销主图，用 OCR 识别图上的活动时间、价格和权益（赠品、保障权益、红包、其他），结果回填到本地 Excel，并生成人工复核清单。

技术方案：Python 3.10、Playwright、RapidOCR（ONNX）、openpyxl、Tkinter。迁入仓库沿用现有实现，未重写。

## 目录约定

```
main-image-tool/
  05_程序/            核心源码（core、ui、config、启动脚本、模块沉淀）
  04_链接库/          本地链接库，需自备，不提交 Git
  06_结果输出/        结果表、复核清单、主图、OCR 结果、日志、进度，不提交 Git
  工具使用说明.md      详细使用说明
```

- `05_程序/core/`：采集与识别逻辑（浏览器、采集器、OCR、时间价格权益提取、运行控制、验证弹窗检测等）。
- `05_程序/ui/`：Tkinter 桌面界面。
- `05_程序/config/`：配置与识别规则。
- `05_程序/模块沉淀/`：各模块开发经验沉淀。

`05_程序/config/config.yaml` 中的路径是相对于 `05_程序` 的，链接库默认读取 `../04_链接库/竞对AI价格表_本地链接库.xlsx`，结果写入 `../06_结果输出`。因此运行前需要在本目录下准备 `04_链接库`，`06_结果输出` 会自动创建。

## 运行准备

在 `05_程序` 目录中执行：

```powershell
cd 05_程序
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

准备链接库：在本目录（`main-image-tool`）下新建 `04_链接库`，放入 `竞对AI价格表_本地链接库.xlsx`。

浏览器：首次使用通过工具界面的"启动浏览器"打开专用 Edge（调试端口 9223），在该浏览器里手动登录天猫。浏览器登录和页面安全验证由用户手动完成，工具不绕过验证；遇到验证弹窗会自动暂停并提醒，用户处理后再继续。

## 启动

图形界面：双击 `05_程序/启动工具.bat`（Windows）或 `05_程序/启动工具.command`（Mac），或运行：

```powershell
.venv\Scripts\python.exe start_app.py
```

命令行：

```powershell
.venv\Scripts\python.exe run.py --limit 5      # 只跑前 5 个
.venv\Scripts\python.exe run.py --no-resume    # 不续跑，从头开始
```

## 输出

结果写入 `06_结果输出`：结果表、人工复核清单、营销主图、OCR 原始结果、运行日志、断点进度。真实链接库、结果表、日志和浏览器数据不提交到 Git。

详细操作见[工具使用说明](工具使用说明.md)。
