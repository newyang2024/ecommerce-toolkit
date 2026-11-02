# -*- coding: utf-8 -*-
"""验证弹窗检测：识别滑块、安全验证等需要人工处理的验证组件。"""
from .config_loader import load_rules
from .logger import get_logger

logger = get_logger("captcha")


class CaptchaDetectedError(Exception):
    """检测到页面验证弹窗，需要人工处理。"""

    def __init__(self, reason: str = ""):
        super().__init__(reason)
        self.reason = reason


def detect_captcha(page):
    """检查页面及内嵌框架，命中验证组件返回 (True, 依据)，否则 (False, "")。"""
    rules = load_rules().get("captcha", {})
    keywords = rules.get("keywords", [])
    iframe_markers = rules.get("iframe_markers", [])

    try:
        frames = list(page.frames)
    except Exception:
        frames = []

    # 1. 验证组件 iframe，命中最可靠
    for frame in frames:
        token = ("%s %s" % (frame.url or "", frame.name or "")).lower()
        for marker in iframe_markers:
            if marker.lower() in token:
                return True, "验证组件框架:%s" % marker

    # 2. 主文档和各框架文字里的验证弹窗特征词
    for frame in [page] + frames:
        try:
            text = frame.evaluate(
                "() => document.body ? document.body.innerText : ''") or ""
        except Exception:
            continue
        for kw in keywords:
            if kw in text:
                return True, "验证文字:%s" % kw
    return False, ""


def ensure_no_captcha(page):
    """采集流程调用，命中验证弹窗就抛出异常让上层暂停。"""
    hit, reason = detect_captcha(page)
    if hit:
        logger.warning("检测到验证弹窗：%s", reason)
        raise CaptchaDetectedError(reason)
