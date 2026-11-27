"""Dependency-free HTTP transport with a persistent cookie jar.

Sklavenitis is a server-rendered ASP.NET site: the search page, the cart
fragment and every user-flow step are HTML, while the cart state and address
lookups are JSON. The site identifies the session with cookies only, so the
whole CLI is `urllib` plus a `CookieJar` that survives between runs.
"""
from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from . import store

BASE = "https://www.sklavenitis.gr"

# Keep this a plain browser UA. Akamai returns 403 for a custom suffix such as
# "sklavenitis-cli/0.1.0" from datacenter IPs (GitHub Actions), even though the
# same request from a residential IP is allowed. Match the Chrome UA used by the
# CI browser login so an exported session is used with the same client identity.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")


class TransportError(RuntimeError):
    """The request never produced an HTTP response."""


class Response:
    __slots__ = ("status", "headers", "text", "url")

    def __init__(self, status: int, headers: Any, text: str, url: str) -> None:
        self.status = status
        self.headers = headers
        self.text = text
        self.url = url

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") if self.headers else "") or ""

    @property
    def is_json(self) -> bool:
        return "json" in self.content_type.lower()

    def json(self) -> Any:
        return json.loads(self.text)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Response {self.status} {self.content_type} {self.url}>"


def cookies_from_jar(jar: http.cookiejar.CookieJar) -> list[dict[str, Any]]:
    out = []
    for c in jar:
        out.append({
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "secure": bool(c.secure),
            "expires": c.expires,
        })
    return out


def cookies_to_jar(cookies: list[dict[str, Any]]) -> http.cookiejar.CookieJar:
    jar = http.cookiejar.CookieJar()
    for c in cookies:
        domain = str(c.get("domain") or "www.sklavenitis.gr")
        jar.set_cookie(http.cookiejar.Cookie(
            version=0,
            name=str(c["name"]),
            value=str(c.get("value") or ""),
            port=None,
            port_specified=False,
            domain=domain,
            domain_specified=domain.startswith("."),
            domain_initial_dot=domain.startswith("."),
            path=str(c.get("path") or "/"),
            path_specified=True,
            secure=bool(c.get("secure")),
            expires=c.get("expires"),
            discard=c.get("expires") is None,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        ))
    return jar


class Session:
    """One cookie jar, one opener, no surprises.

    Cookies are written back to the config directory after every request, so a
    killed process does not lose the session in the middle of an add-to-cart
    flow.
    """

    def __init__(self, timeout: int = 30, user_agent: Optional[str] = None) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or UA
        self.jar = cookies_to_jar(store.load_cookies())
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.verbose = False
        # The cookie import validates a candidate jar before committing it.
        self.save_enabled = True

    # ------------------------------------------------------------------ cookies
    def save(self) -> None:
        if self.save_enabled:
            store.save_cookies(cookies_from_jar(self.jar))

    def cookie(self, name: str) -> Optional[str]:
        for c in self.jar:
            if c.name == name:
                return c.value
        return None

    def clear(self) -> None:
        self.jar.clear()
        store.save_cookies([])

    # ----------------------------------------------------------------- transport
    def request(self, method: str, url: str, *, form: Optional[dict[str, Any]] = None,
                json_body: Any = None, headers: Optional[dict[str, str]] = None,
                follow: bool = True) -> Response:
        data: Optional[bytes] = None
        extra = headers or {}
        ajax = any(key.lower() == "x-requested-with" for key in extra)
        if ajax:
            hdrs = {
                "User-Agent": self.user_agent,
                "Accept": "*/*",
                "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
        else:
            hdrs = {
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                          "image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode()
            hdrs["Content-Type"] = "application/json"
        elif form is not None:
            data = urllib.parse.urlencode(form).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        hdrs.update(extra)

        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        opener = self.opener
        if not follow:
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self.jar),
                _NoRedirect(),
            )
        try:
            with opener.open(req, timeout=self.timeout) as raw:
                body = raw.read().decode("utf-8", "replace")
                return Response(raw.status, raw.headers, body, raw.geturl())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            return Response(exc.code, exc.headers, body, exc.geturl() or url)
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise TransportError(f"cannot reach {url}: {reason}") from exc
        finally:
            self.save()

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, form: Optional[dict[str, Any]] = None,
             **kwargs: Any) -> Response:
        return self.request("POST", url, form={} if form is None else form, **kwargs)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Return the 3xx response instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None
