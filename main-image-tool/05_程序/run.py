# -*- coding: utf-8 -*-
"""主入口：运行批量采集，支持限量冒烟和断点续跑。"""
import argparse

from core.pipeline import Pipeline


def main():
    parser = argparse.ArgumentParser(description="天猫主图智能信息提取")
    parser.add_argument("--limit", type=int, default=None,
                        help="只采集前 N 个商品，用于冒烟")
    parser.add_argument("--no-resume", action="store_true",
                        help="不读取已有进度，从头开始")
    args = parser.parse_args()

    pipeline = Pipeline(limit=args.limit, resume=not args.no_resume)
    summary = pipeline.run()

    print("\n===== 运行结果 =====")
    print("成功：", summary["success"])
    print("失败：", summary["failed"])
    print("复核项：", summary["review_count"])
    print("结果表：", summary["xlsx"])
    print("复核清单：", summary["review"])


if __name__ == "__main__":
    main()
