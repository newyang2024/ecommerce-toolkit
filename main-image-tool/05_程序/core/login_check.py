# -*- coding: utf-8 -*-
"""天猫登录态检查。

通过 CDP 在已连接的浏览器上打开天猫首页，根据登录 cookie 和页面是否出现
登录控件判断登录是否有效。检查用的页面用完即关，不干扰用户当前窗口。
"""
from .config_loader import load_config
from .logger import get_logger

logger = get_logger("login_check")


def check_login(context, timeout=20):
    """返回 True 表示已登录，False 表示登录失效或无法确认。"""
    cfg = load_config()
    probe_url = cfg["browser"]["login_check_url"]

    # 先看 cookie，登录后通常有 unb（用户数字 id）和 _tb_token_
    try:
        cookies = context.cookies()
        names = {c["name"]: c.get("value", "") for c in cookies}
        has_unb = bool(names.get("unb")) and names.get("unb") not in ("0", "")
        has_token = bool(names.get("_tb_token_"))
        logger.info("登录 cookie：unb=%s, _tb_token_=%s",
                    "有" if has_unb else "无", "有" if has_token else "无")
    except Exception as e:
        logger.warning("读取登录 cookie 异常: %s" % e)
        has_unb = has_token = False

    page = context.new_page()
    try:
        page.goto(probe_url, wait_until="domcontentloaded", timeout=timeout * 1000)
        page.wait_for_timeout(2500)
        final_url = page.url

        # 被重定向到登录域名，判定未登录
        if "login.taobao.com" in final_url or "login.tmall.com" in final_url:
            logger.info("登录态检查：被重定向到登录页")
            return False

        # 页面出现登录控件
        login_ui = page.query_selector(
            "input[type='password'], .login-qrcode, .qrcode-img, "
            "img[src*='qrcode'], #J_QRCodeImg"
        )
        if login_ui is not None:
            logger.info("登录态检查：页面出现登录控件")
            return False

        # unb 是登录后的用户数字 id，作为登录的必要条件；
        # _tb_token_ 未登录访问也会种下，不能单独作为依据。
        if has_unb:
            logger.info("登录态检查：已登录")
            return True

        logger.info("登录态检查：未发现有效登录标记，按未登录处理")
        return False
    finally:
        try:
            page.close()
        except Exception:
            pass
