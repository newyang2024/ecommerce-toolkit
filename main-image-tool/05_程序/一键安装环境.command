#!/bin/bash
# 天猫主图智能信息提取工具 Mac 环境一键安装
# 双击运行，自动创建虚拟环境并安装全部依赖，需要联网。

cd "$(dirname "$0")"

fail() {
  echo ""
  echo "安装中断：$1"
  echo "按回车键关闭窗口，并把上面的报错反馈给开发。"
  read
  exit 1
}

echo "=========================================="
echo "  天猫主图智能信息提取工具 环境安装"
echo "=========================================="

# 1. 检查 python3
if ! command -v python3 >/dev/null 2>&1; then
  echo "没有检测到 python3，尝试打开 Xcode 命令行工具安装器。"
  xcode-select --install 2>/dev/null || true
  echo "请在弹出的窗口里完成安装，结束后重新双击本脚本。"
  echo "按回车键关闭窗口。"
  read
  exit 1
fi

PY_VER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "检测到 Python 版本：$PY_VER"

# 2. 创建虚拟环境
echo "正在创建虚拟环境 .venv ..."
python3 -m venv .venv || fail "创建虚拟环境失败"

# 3. 激活并安装依赖
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip || fail "升级 pip 失败"
echo "正在安装依赖，请保持联网，可能需要几分钟。"
pip install -r requirements.txt || fail "依赖安装失败"

# 4. 给启动脚本加可执行权限，方便以后双击
chmod +x ./*.command 2>/dev/null || true

echo ""
echo "=========================================="
echo "  环境安装完成。"
echo "  以后双击「启动工具.command」即可打开工具。"
echo "=========================================="
echo "按回车键关闭窗口。"
read
