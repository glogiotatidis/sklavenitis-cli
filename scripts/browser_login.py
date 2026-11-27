"""CI-only: log in through Sklavenitis' real form and export the session.

The site rejects the dependency-free CLI's direct login even with a reCAPTCHA
token (the form is bound to the browser session). This helper submits the real
form with the runner's Chrome, verifies it reaches `/account/`, then writes the
site cookies into the CLI's config directory, exactly like
`sklavenitis auth import`. A sign-in page after submit means the credentials are
wrong, the account is unconfirmed/blocked, or the automated browser is rejected;
it is not a header issue. It prints one boolean, never credentials, cookies, or
the email.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://www.sklavenitis.gr/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
AUTH_COOKIE = ".AspNet.ApplicationCookie_Frontend4"


def main() -> int:
    email = os.environ["SKLAVENITIS_EMAIL"]
    password = os.environ["SKLAVENITIS_PASSWORD"]
    config_dir = Path(os.environ["SKLAVENITIS_CONFIG_DIR"])
    ok = False
    cookies: list[dict] = []
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
            jar = context.cookies()
            if any(c["name"] == AUTH_COOKIE and c["value"] for c in jar):
                cookies = jar
                break
        if cookies:
            # A non-empty auth cookie is not proof: an anonymous session can
            # carry one too. The account page is the authority.
            page.goto(BASE + "account/", wait_until="domcontentloaded", timeout=60_000)
            final = page.url
            ok = ("/account/signin" not in final
                  and "/account/login" not in final
                  and page.locator("#login_form").count() == 0)
            cookies = context.cookies()
        browser.close()

    if ok:
        exported = []
        for c in cookies:
            if not c["domain"].endswith("sklavenitis.gr"):
                continue
            expires = c.get("expires")
            if expires is not None and expires < 0:
                expires = None
            exported.append({
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path") or "/",
                "secure": bool(c.get("secure")),
                "expires": expires,
            })
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / "cookies.json"
        path.write_text(json.dumps(exported, ensure_ascii=False) + "\n", "utf-8")
        os.chmod(path, 0o600)
    print("browser_login_ok=" + str(ok))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
