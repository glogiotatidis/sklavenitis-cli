"""CI-only: obtain a reCAPTCHA v3 token with the runner's Chrome.

The CLI itself is dependency-free and posts the token with the login form. This
helper uses the browser the login modal would use, so the daily account job can
exercise the real login endpoint instead of stopping at the captcha.

It prints exactly one GITHUB_ENV line, no credentials and no cookies.
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = "https://www.sklavenitis.gr/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--disable-blink-features=AutomationControlled"])
        page = browser.new_page(user_agent=UA, locale="el-GR")
        # The sign-in page renders the same form directly; skip the header modal
        # and its cookie-consent overlay.
        page.goto(BASE + "account/signin-register/", wait_until="domcontentloaded",
                  timeout=60_000)
        page.wait_for_selector("#login_form", state="visible", timeout=30_000)
        page.wait_for_function(
            "typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function'",
            timeout=30_000,
        )
        token = page.evaluate("""async () => {
            const el = document.querySelector('[data-plugin-recaptcha]');
            if (!el) throw new Error('no recaptcha element in the login modal');
            const opts = JSON.parse(el.getAttribute('data-plugin-recaptcha'));
            await new Promise(resolve => grecaptcha.ready(resolve));
            return await grecaptcha.execute(opts.sitekey, {action: 'submit'});
        }""")
        browser.close()
    if not token:
        print("reCAPTCHA returned no token", file=sys.stderr)
        return 1
    print(f"SKLAVENITIS_RECAPTCHA_TOKEN={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
