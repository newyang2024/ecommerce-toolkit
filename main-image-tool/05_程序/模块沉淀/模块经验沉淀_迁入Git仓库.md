# 模块经验沉淀：迁入 Git 仓库

## 1. 模块名称
主图识别工具纳入 ecommerce-toolkit 仓库。

## 2. 对应计划
把主图识别工具迁入用户创建的 GitHub 仓库 ecommerce-toolkit，作为后续维护的唯一代码来源，补充 README、.gitignore 和根目录 AGENTS.md，用功能分支提交推送并创建 Pull Request。

## 3. 代码文件与作用
本次不改工具源码，只做仓库整理与文档。

- 仓库本地工作目录：C:\Users\user\Desktop\AI开发项目\ecommerce-toolkit（已存在，含 marketing-calendar 工具）。
- 新增 main-image-tool/05_程序/：从源项目 05_程序 复制，排除 data（浏览器配置，约 900MB）和 __pycache__，源码原样迁入。
- 新增 main-image-tool/README.md、工具使用说明.md：目录约定、运行准备、启动与输出说明。
- 更新根目录 README.md、AGENTS.md、.gitignore：加入主图识别工具的条目、目录约定、运行检查命令和数据排除规则。
- 功能分支：feature/main-image-tool，基于 feature/marketing-calendar-migration（该分支含营销日历工具，main 仅有 Initial commit）。
- Pull Request：#1 迁入主图识别工具，目标 main，https://github.com/newyang2024/ecommerce-toolkit/pull/1 。

## 4. 测试结果
- 33 个 Python 文件 py_compile 语法检查通过。
- git 暂存内容核对：71 个新增/修改文件均为源码、配置与文档，浏览器数据、__pycache__、链接库、结果表、迁移包 zip 均被 .gitignore 排除。
- 推送 feature/main-image-tool 到 origin 成功，创建 PR #1，状态 OPEN。

## 5. 用法示例
克隆仓库后，在 main-image-tool/05_程序/ 中：
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe start_app.py
```
命令行：`.venv\Scripts\python.exe run.py --limit 5`。
运行前在 main-image-tool/ 下准备 04_链接库/竞对AI价格表_本地链接库.xlsx，结果写入 06_结果输出。

## 6. 注意事项
- 本机最初没有 git 和 gh，用 winget 安装 Git.Git 和 GitHub.cli，git 在 C:\Program Files\Git\bin，gh 在 C:\Program Files\GitHub CLI。
- 推送用 HTTPS 走 Windows 凭据管理器已有 GitHub 凭据，无需额外登录即可推送。
- gh 登录时该 token 缺 read:org scope，gh auth login 验证不通过；改用 GH_TOKEN 环境变量方式，gh 不强制校验该 scope，可正常 api 与建 PR。token 不要打印或写日志。
- 仓库已有约定：真实报表、链接库、登录状态、浏览器数据、结果输出不进 Git，.gitignore 已全局排除 xlsx、csv、zip、docx，主图工具另加 data、链接库、结果输出目录。
- 源项目根目录 C:\Users\user\Desktop\AI开发项目\主图识别工具 保留作历史资料，后续维护以仓库为准。

## 7. 待办
- 以后每次开发新功能，先 git fetch、同步 origin/main、检查已有改动，再在功能分支更新代码和文档。
- PR #1 待用户审查合并；营销日历工具的 PR 可另行处理。
- 真实链接库、识别结果、浏览器配置不进 Git，换机需自备。
- 源项目根目录报错的启动工具.bat 尚未处理，属历史遗留。
