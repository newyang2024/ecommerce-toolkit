# 模块经验沉淀 代码审查与 Mac 迁移

## 1. 模块目标
对全部源码做平台兼容性审查，找出 Windows 专属的硬编码和调用，然后在当前 Windows 环境下产出一个可在 Mac 上运行的迁移包，让工具能在没有开发环境的 Mac 上通过一次安装后使用。

## 2. 实际产出
- 代码审查：通读入口、浏览器、配置、核心业务和全部界面文件，确认核心逻辑用 pathlib 和纯 Python 实现，跨平台基础良好，同时定位 launch_edge 硬编码 Edge 路径、三处 os.startfile、.bat 脚本等不兼容点。
- 浏览器改造：launch_edge 按系统分支定位 Edge 并以 Chrome 兜底，覆盖 Windows、macOS、Linux，CDP 端口和独立 profile 逻辑保持不变。
- 跨平台工具：新增 core/platform_utils.py，用系统默认方式打开文件，Mac 走 open，替换三处 os.startfile。
- 导出表修复：state_reader 读回原始链接，COLUMNS 加回链接列，导出补列宽行高自适应，链接列默认隐藏但数据保留。
- 界面适配：字体增加 PingFang SC、Hiragino 等 Mac 回退，日志等宽字体增加 Menlo、Monaco。
- Mac 包：两个 .command 脚本（一键安装、启动）加 Mac 安装与使用说明，打成 84KB 的 zip，条目用正斜杠，.command 带 755 可执行权限。

## 3. 遇到的问题
- Windows 上无法交叉构建 Mac 便携 runtime，PE 和 Mach-O 二进制不通用，自带环境的方案在当前机器做不出来，只能改走源码加一键安装。
- .command 在 Windows 上创建后默认没有 Unix 可执行权限，需要打包时手动写 external_attr，同时在说明里保留右键打开和 chmod 的兜底。
- 导出表是新建工作簿，列定义里没有链接，读结果时也没存 url，导致链接被吞、列前移，需要从读取到展示整条链路补回。

## 4. 踩过的坑
- .command 必须是纯 LF 换行，带 Windows 的 CR 会让 Mac bash 报解析错误，写完要专门检查字节里有没有回车符。
- 不能假设 zip 会保留权限，Windows 上常规打包出的条目不带可执行位，要用 Python zipfile 显式设置 external_attr。
- 本工具通过 CDP 连接系统已装的浏览器，不需要 playwright install 下载浏览器内核，安装脚本保持轻量，避免多余的几百兆下载。

## 5. 原本以为 vs 实际发现
- 原本以为 Mac 迁移包能像 Windows 那样做成自带便携环境、拷过去双击就用，实际跨平台二进制无法在 Windows 上交叉生成，必须在 Mac 上完成环境安装这一步。
- 原本以为平台问题会很多，实际业务代码 pathlib 用得规范，真正要改的只有浏览器定位、系统打开和启动脚本这几处，依赖本身都有 Mac 版本。
- 原本以为导出表链接被吞是表格软件显示问题，实际是代码列定义和读取链路里根本没有链接，跟打开软件无关。

## 6. 下游引用及后续开发可能影响该模块的风险检点
- 后续改 launch_edge 或浏览器路径逻辑时，要同时回归三个平台，不能只在 Windows 上验证。
- 新增系统调用前先判断是否平台专属，优先放进 platform_utils，不要再直接写 os.startfile。
- Mac 包首次安装依赖联网，若用户反馈安装失败，优先查网络和 python3 是否缺失，再考虑依赖版本。
- 链接列默认隐藏这个口径用户尚未最终拍板，若用户希望默认显示，调整 _write_export 的 hidden 设置即可，数据链路已具备。

## 7. 待办
- Mac 包需要在真实 Mac 上跑一次安装和启动，本机无法替代，重点验证依赖安装、浏览器定位和登录采集。
- 本机系统 Python 的 onnxruntime 仍是 1.23.2，根目录报错的启动工具.bat 还没处理，属于 Windows 侧遗留。
- 链接列默认隐藏还是显示，以及根目录 bat 删除还是改写，仍需用户拍板。
- 3 个双色推断商品的人工确认是历史遗留，继续保留。
