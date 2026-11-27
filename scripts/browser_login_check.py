"""CI-only diagnostic: does the configured account log in in a real browser?

Prints a single boolean, never the email, password, or cookies. Used once to
separate bad credentials from an automated-login block before deciding how the
daily account job should authenticate.
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = "https://www.sklavenitis.gr/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
AUTH_COOKIE = ".AspNet.ApplicationCookie_Frontend4"


def main() -> int:
    email = os.environ["SKLAVENITIS_EMAIL"]
    password = os.environ["SKLAVENITIS_PASSWORD"]
    ok = False
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent=UA, locale="el-GR")
        page = context.new_page()
        page.goto(BASE + "account/signin-register/", wait_until="domcontentloaded",
                  timeout=60_000)
        page.wait_for_selector("#login_form", state="visible", timeout=30_000)
        page.fill("#Email", email)
        page.fill("#Password", password)
        try:
            page.evaluate("document.querySelector('#Login').requestSubmit()")
        except Exception:
            pass
        for _ in range(60):
            page.wait_for_timeout(500)
            if any(c["name"] == AUTH_COOKIE and c["value"] for c in context.cookies()):
                ok = True
                break
        browser.close()
    print("browser_login_ok=" + str(ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
