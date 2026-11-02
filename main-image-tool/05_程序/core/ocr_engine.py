# -*- coding: utf-8 -*-
"""OCR 引擎封装：RapidOCR 单例，输出统一的文字块结构，可保存原始结果。"""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

from .config_loader import load_config, resolve_path
from .logger import get_logger

logger = get_logger("ocr_engine")


@dataclass
class TextBlock:
    text: str
    box: List[List[float]]
    score: float
    cx: float
    cy: float
    width: float
    height: float
    rx: float       # 中心相对位置 0 到 1
    ry: float


_engine_singleton = None


def _get_engine():
    global _engine_singleton
    if _engine_singleton is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine_singleton = RapidOCR()
        logger.info("RapidOCR 模型已加载")
    return _engine_singleton


class OCREngine:
    def __init__(self):
        self.config = load_config()
        self.ocr_dir = resolve_path(self.config["paths"]["ocr_dir"])
        self.ocr_dir.mkdir(parents=True, exist_ok=True)

    def recognize(self, image_path, image_size: Optional[tuple] = None) -> List[TextBlock]:
        image_path = Path(image_path)
        if image_size is None:
            from PIL import Image
            with Image.open(image_path) as im:
                image_size = im.size  # (w, h)
        w, h = image_size

        engine = _get_engine()
        result, _ = engine(str(image_path))
        blocks: List[TextBlock] = []
        for box, text, score in result or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            cx, cy = sum(xs) / 4, sum(ys) / 4
            blocks.append(TextBlock(
                text=text, box=[[float(a), float(b)] for a, b in box],
                score=float(score), cx=cx, cy=cy,
                width=max(xs) - min(xs), height=max(ys) - min(ys),
                rx=cx / w, ry=cy / h,
            ))
        logger.info("OCR 完成：%s，%d 个文字块", image_path.name, len(blocks))
        return blocks

    def save_raw(self, blocks: List[TextBlock], item_id: str) -> Path:
        path = self.ocr_dir / ("%s_ocr.json" % item_id)
        data = [asdict(b) for b in blocks]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
