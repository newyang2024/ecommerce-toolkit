# -*- coding: utf-8 -*-
"""配置加载：读取 config.yaml 和 rules.yaml。"""
from pathlib import Path

import yaml

# 程序根目录（core 的上一级）
PROGRAM_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROGRAM_ROOT / "config"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError("找不到配置文件: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("配置文件格式不正确: %s" % path)
    return data


def load_config() -> dict:
    """加载主配置 config.yaml。"""
    return _load_yaml(CONFIG_DIR / "config.yaml")


def load_rules() -> dict:
    """加载字段规则 rules.yaml。"""
    return _load_yaml(CONFIG_DIR / "rules.yaml")


def resolve_path(rel_path: str) -> Path:
    """把配置里相对程序根目录的路径解析成绝对路径。"""
    p = Path(rel_path)
    if p.is_absolute():
        return p
    return (PROGRAM_ROOT / p).resolve()
