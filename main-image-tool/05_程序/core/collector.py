# -*- coding: utf-8 -*-
"""单商品采集：打开页面、定位主图、OCR、提取时间价格权益，串成完整流程。"""
from dataclasses import dataclass

from .benefit_extractor import BenefitExtractor, BenefitResult
from .captcha_detector import ensure_no_captcha
from .image_locator import ImageLocator
from .logger import get_logger
from .ocr_engine import OCREngine
from .price_extractor import PriceExtractor, PriceResult
from .time_extractor import TimeExtractor, TimeResult

logger = get_logger("collector")


class RiskControlError(Exception):
    """页面提示访问异常，疑似触发风控。"""


@dataclass
class ItemResult:
    item_id: str
    time: TimeResult
    price: PriceResult
    benefit: BenefitResult

    @property
    def need_review(self) -> bool:
        return self.time.need_review or self.price.need_review


class Collector:
    def __init__(self):
        self.locator = ImageLocator()
        self.ocr = OCREngine()
        self.time_ext = TimeExtractor()
        self.price_ext = PriceExtractor()
        self.benefit_ext = BenefitExtractor()

    def process_one(self, browser, item, control=None):
        page = browser.new_page()
        try:
            if control is not None and control.wait_if_paused():
                return None  # 暂停期间被停止
            page.goto(item.url, wait_until="domcontentloaded")
            browser.human_delay("page_settle")
            self._note_risk(page)
            ensure_no_captcha(page)  # 页面加载后先确认没有验证弹窗

            if control is not None and control.wait_if_paused():
                return None

            located = self.locator.locate_and_download(page, item.item_id)
            ensure_no_captcha(page)  # 定位主图过程中也可能弹出验证

            blocks1 = self.ocr.recognize(located.local_path)
            self.ocr.save_raw(blocks1, item.item_id)

            groups = [blocks1]
            if located.second_path:
                groups.append(self.ocr.recognize(located.second_path))

            time_r = self.time_ext.extract(blocks1)
            price_r = self.price_ext.extract(blocks1)
            benefit_r = self.benefit_ext.extract(groups)

            logger.info("商品 %s 处理完成，需复核 %s",
                        item.item_id, ItemResult(item.item_id, time_r,
                                                 price_r, benefit_r).need_review)
            return ItemResult(item.item_id, time_r, price_r, benefit_r)
        finally:
            browser.close_page(page)

    def _note_risk(self, page):
        # 访问异常只影响页面右侧动态内容，不影响主图缩略图，记录后继续抓主图
        try:
            hit = page.evaluate(
                """() => !!(document.body &&
                    document.body.innerText &&
                    document.body.innerText.includes('访问异常'))""")
        except Exception:
            return
        if hit:
            logger.warning("页面提示访问异常，但不影响主图，继续采集")
