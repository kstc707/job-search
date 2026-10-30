"""Make URLs and domains safe to display.

`https://fedex-help.top/pay` becomes `hxxps://fedex-help[.]top/pay`: a reader can still see
exactly what it is, but no browser, chat app or dashboard will turn it into a clickable link.
Every place that shows a URL to a person goes through this one function.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def defang_host(host: str) -> str:
    if host.startswith("[") and host.endswith("]"):  # IPv6 literal: colons are not links
        return host
    return host.replace(".", "[.]")


def defang(value: str) -> str:
    value = value.strip()
    if "://" not in value:  # a bare domain or host:port
        return defang_host(value)
    parts = urlsplit(value)
    scheme = parts.scheme.lower().replace("http", "hxxp").replace("ftp", "fxp")
    host = parts.hostname or ""
    if ":" in host:  # urlsplit strips IPv6 brackets
        host = f"[{host}]"
    netloc = defang_host(host)
    if parts.port:
        netloc += f":{parts.port}"
    if parts.username:  # user:pass@host tricks stay visible, defanged
        netloc = f"{parts.username}@{netloc}"
    rest = parts.path
    if parts.query:
        rest += "?" + parts.query
    if parts.fragment:
        rest += "#" + parts.fragment
    return f"{scheme}://{netloc}{rest}"
