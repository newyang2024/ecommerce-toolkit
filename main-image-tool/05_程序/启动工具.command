#!/bin/bash
# 天猫主图智能信息提取工具 Mac 启动脚本
# 双击运行，使用虚拟环境打开桌面界面。

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "还没有安装运行环境，请先双击「一键安装环境.command」。"
  echo "按回车键关闭窗口。"
  read
  exit 1
fi

.venv/bin/python start_app.py
if [ $? -ne 0 ]; then
  echo ""
  echo "程序异常退出，请把上面的报错反馈给开发。"
  echo "按回车键关闭窗口。"
  read
fi
