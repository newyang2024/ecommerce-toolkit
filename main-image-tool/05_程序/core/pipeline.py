# -*- coding: utf-8 -*-
"""批量编排：重试、异常隔离、频率控制、登录复查、断点续跑，最后写结果和复核清单。"""
import json
import random
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from .benefit_extractor import BenefitResult
from .collector import Collector, ItemResult
from .config_loader import load_config, resolve_path
from .excel_writer import ExcelWriter
from .link_library import LinkLibrary
from .logger import get_logger
from .login_check import check_login
from .price_extractor import PriceResult
from .review import ReviewCollector
from .run_control import RunControl
from .time_extractor import TimeResult

logger = get_logger("pipeline")


def _serialize(r: ItemResult) -> dict:
    return asdict(r)


def _deserialize(d: dict) -> ItemResult:
    return ItemResult(
        item_id=d["item_id"],
        time=TimeResult(**d["time"]),
        price=PriceResult(**d["price"]),
        benefit=BenefitResult(**d["benefit"]),
    )


class Pipeline:
    def __init__(self, limit: Optional[int] = None, resume: bool = True,
                 progress_callback=None, control=None):
        self.config = load_config()
        self.humanize = self.config["humanize"]
        self.retry_times = self.config["collect"]["retry_times"]

        self.lib = LinkLibrary()
        self.lib.load()
        self.collector = Collector()

        self.limit = limit
        self.progress_callback = progress_callback
        self.control = control or RunControl()
        self.results: Dict[str, ItemResult] = {}
        self.failed: Dict[str, str] = {}

        state_dir = resolve_path(self.config["paths"]["result_dir"]) / "进度"
        state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = state_dir / "pipeline_state.json"
        if resume:
            self._load_state()

    def run(self):
        from .browser import BrowserManager

        browser = BrowserManager()
        browser.start()
        if not check_login(browser.context):
            browser.close()
            self._emit({"type": "login_failed"})
            raise RuntimeError("登录态已失效，请在专用 Edge 里重新登录天猫后再运行。")

        tasks = self.lib.unique_tasks()
        if self.limit:
            tasks = tasks[: self.limit]
        total = len(tasks)
        batch_size = self.humanize["batch_size"]

        self._emit({"type": "start", "total": total})
        stopped = False

        try:
            for idx, task in enumerate(tasks):
                # 每个商品开始前先响应暂停，暂停时阻塞，恢复或停止后再继续
                if self.control.wait_if_paused():
                    stopped = True
                    logger.info("暂停等待期间收到停止，保存进度后退出")
                    break
                # 停止请求在商品之间生效，保存进度后退出
                if self.control.is_stopped():
                    stopped = True
                    logger.info("收到停止请求，保存进度后退出")
                    break

                brief = self._item_brief(task, idx, total)
                if task.item_id in self.results:
                    logger.info("跳过已完成：%s", task.item_id)
                    self._emit(dict(brief, type="skip"))
                    continue

                self._emit(dict(brief, type="item_start"))
                self._process_item(browser, task)
                if self.control.is_stopped():
                    stopped = True
                    self._save_state()
                    break
                self._save_state()
                self._emit(dict(brief, type="item_done",
                                success=len(self.results),
                                failed=len(self.failed),
                                failed_items=dict(self.failed)))

                if idx < total - 1:
                    browser.human_delay("between_items")

                done = idx + 1
                if done % batch_size == 0 and done < total:
                    if self.humanize.get("long_rest_enabled", True):
                        if self._long_rest(browser):
                            stopped = True
                            break
                    if not check_login(browser.context):
                        raise RuntimeError("登录态在中途失效，请重新登录后用断点续跑继续。")
        finally:
            browser.close()

        if stopped:
            self._save_state()
            summary = {
                "xlsx": "",
                "review": "",
                "success": len(self.results),
                "failed": dict(self.failed),
                "review_count": 0,
                "stopped": True,
            }
            self._emit({"type": "stopped",
                        "success": summary["success"],
                        "failed": len(summary["failed"])})
            return summary

        summary = self._finalize()
        summary["stopped"] = False
        self._emit({"type": "finished",
                    "success": summary["success"],
                    "failed": len(summary["failed"]),
                    "review_count": summary["review_count"],
                    "xlsx": summary["xlsx"]})
        return summary

    def _emit(self, event: dict):
        if not self.progress_callback:
            return
        try:
            self.progress_callback(event)
        except Exception:
            pass

    def _item_brief(self, task, idx: int, total: int) -> dict:
        return {
            "index": idx + 1,
            "total": total,
            "item_id": task.item_id,
            "brand": task.brand,
            "name": task.name,
            "door": task.door,
            "color": task.color_raw,
        }

    def _process_item(self, browser, task):
        """处理单个商品：验证弹窗时暂停等待人工，普通异常按重试次数重试。"""
        from .captcha_detector import CaptchaDetectedError

        attempt = 0
        while True:
            if self.control.is_stopped():
                return
            try:
                r = self.collector.process_one(browser, task, self.control)
                if r is None:
                    return  # 商品内部暂停后被停止
                self.results[task.item_id] = r
                self.failed.pop(task.item_id, None)
                logger.info("进度 %d/%d，商品 %s 成功",
                            len(self.results), len(self.lib.unique_tasks()),
                            task.item_id)
                return
            except CaptchaDetectedError as e:
                # 验证弹窗：后端先确保暂停，提醒用户，等待继续后重试，不占重试次数
                logger.warning("商品 %s 触发验证弹窗，等待人工处理：%s",
                               task.item_id, e.reason)
                self.control.request_pause()
                self._emit({"type": "captcha_pause", "reason": e.reason,
                            "item_id": task.item_id})
                if self.control.wait_if_paused():
                    return  # 等待期间被停止
                logger.info("人工验证完成，重新采集商品 %s", task.item_id)
                continue
            except Exception as e:
                last_err = str(e)
                attempt += 1
                logger.warning("商品 %s 第 %d 次失败：%s",
                               task.item_id, attempt, last_err)
                if attempt > self.retry_times:
                    self.failed[task.item_id] = last_err
                    logger.error("商品 %s 最终失败：%s", task.item_id, last_err)
                    return
                time.sleep(random.uniform(2, 5))

    def _long_rest(self, browser) -> bool:
        """长休息，分段睡以便及时响应停止。返回 True 表示休息期间被停止。"""
        lo, hi = self.humanize["long_rest"]
        secs = random.uniform(lo, hi)
        logger.info("已采 %d 个，长休息 %.0f 秒", self.humanize["batch_size"], secs)
        self._emit({"type": "rest", "seconds": int(secs)})

        waited = 0.0
        while waited < secs:
            if self.control.is_stopped():
                logger.info("长休息期间收到停止请求")
                return True
            step = min(1.0, secs - waited)
            time.sleep(step)
            waited += step
        return False

    def _finalize(self):
        result_list = list(self.results.values())
        xlsx = ExcelWriter().write(result_list, self.lib)

        review_items = ReviewCollector().collect(result_list, self.lib)
        review_md = ReviewCollector().write_markdown(review_items)

        self._write_latest_pointer(xlsx)

        logger.info("批量结束：成功 %d，失败 %d，复核 %d",
                    len(self.results), len(self.failed), len(review_items))
        return {
            "xlsx": xlsx,
            "review": review_md,
            "success": len(self.results),
            "failed": dict(self.failed),
            "review_count": len(review_items),
        }

    def _write_latest_pointer(self, xlsx_path):
        """记录最近一次完整跑完的结果文件，供前端下次打开时定位，避免取到验证文件。"""
        result_dir = resolve_path(self.config["paths"]["result_dir"])
        pointer = result_dir / "latest_result.txt"
        try:
            pointer.write_text(str(xlsx_path), encoding="utf-8")
        except Exception as e:
            logger.warning("最新结果指针写入失败：%s", e)

    def _save_state(self):
        state = {
            "results": {k: _serialize(v) for k, v in self.results.items()},
            "failed": self.failed,
        }
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.state_path)

    def _load_state(self):
        if not self.state_path.exists():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.results = {k: _deserialize(v)
                            for k, v in state.get("results", {}).items()}
            self.failed = state.get("failed", {})
            logger.info("已恢复进度：成功 %d，失败 %d",
                        len(self.results), len(self.failed))
        except Exception as e:
            logger.warning("进度文件读取失败，将从头开始：%s", e)
