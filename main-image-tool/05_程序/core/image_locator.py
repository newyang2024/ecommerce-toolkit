# -*- coding: utf-8 -*-
"""营销主图定位与下载：定位第一张缩略图，构造高清 URL 下载，失败回退截图。"""
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .config_loader import load_config, resolve_path
from .logger import get_logger

logger = get_logger("image_locator")


@dataclass
class LocatedImage:
    item_id: str
    local_path: Path
    source_url: str
    second_path: Optional[Path] = None
    used_screenshot: bool = False


def _build_hd_url(url: str) -> str:
    """压缩缩略图 URL 构造高清原图。"""
    cuts = ["_q50.jpg_.webp", "_q50.png_.webp", ".jpg_.webp", ".png_.webp"]
    for cut in cuts:
        if url.endswith(cut):
            base = url[: -len(cut)]
            if base.endswith(".jpg") or base.endswith(".png"):
                return base
            ext = ".png" if "png" in cut else ".jpg"
            return base + ext
    return url


class ImageLocator:
    def __init__(self):
        self.config = load_config()
        self.img_dir = resolve_path(self.config["paths"]["main_image_dir"])
        self.img_dir.mkdir(parents=True, exist_ok=True)

    def _thumbnails(self, page) -> List[str]:
        return page.evaluate(
            """() => Array.from(document.querySelectorAll(
                '[class*="thumbnailPic"], [class*="thumbnailOtherPic"]'))
                .map(i => (i.currentSrc||i.src||'')).filter(Boolean)"""
        )

    def _download(self, url: str, path: Path) -> bool:
        # alicdn 国内直连，禁用代理
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = opener.open(req, timeout=20).read()
            if len(data) < 10000:
                return False
            path.write_bytes(data)
            return True
        except Exception as e:
            logger.warning("下载失败 %s：%s", url[:80], e)
            return False

    def _screenshot_main(self, page, path: Path) -> bool:
        try:
            el = page.locator('[class*="mainPicWrap"]').first
            el.screenshot(path=str(path))
            return path.exists()
        except Exception as e:
            logger.warning("主图截图失败：%s", e)
            return False

    def locate_and_download(self, page, item_id: str) -> LocatedImage:
        thumbs = self._thumbnails(page)
        # 去重保序
        uniq = []
        for t in thumbs:
            if t not in uniq:
                uniq.append(t)

        local_path = self.img_dir / ("%s.jpg" % item_id)
        result = LocatedImage(item_id=item_id, local_path=local_path,
                             source_url=uniq[0] if uniq else "")

        if uniq:
            hd = _build_hd_url(uniq[0])
            if self._download(hd, local_path):
                logger.info("营销主图已下载：%s", local_path.name)
            else:
                # 试原始 URL
                if self._download(uniq[0], local_path):
                    logger.info("营销主图用原始链接下载：%s", local_path.name)
                elif self._screenshot_main(page, local_path):
                    result.used_screenshot = True
                    logger.info("营销主图改用截图：%s", local_path.name)
                else:
                    logger.error("营销主图获取失败：%s", item_id)
        else:
            if self._screenshot_main(page, local_path):
                result.used_screenshot = True

        # 第二张作为权益补充（若存在且与第一张不同）
        if len(uniq) >= 2:
            second = self.img_dir / ("%s_2.jpg" % item_id)
            hd2 = _build_hd_url(uniq[1])
            if self._download(hd2, second):
                result.second_path = second

        return result
