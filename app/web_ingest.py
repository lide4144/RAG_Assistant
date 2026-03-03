from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import re
from urllib import error, parse, request


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", flags=re.IGNORECASE | re.DOTALL)
_TITLE_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:title|twitter:title)["\'][^>]+content=["\']([^"\']+)["\']',
    flags=re.IGNORECASE,
)
_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
_WECHAT_TITLE_RE = re.compile(r"var\s+msg_title\s*=\s*\"([^\"]+)\";", flags=re.IGNORECASE)
_WECHAT_CONTENT_RE = re.compile(
    r"<(?:div|section)[^>]+id=[\"']js_content[\"'][^>]*>(.*?)</(?:div|section)>",
    flags=re.IGNORECASE | re.DOTALL,
)
_ARTICLE_RE = re.compile(r"<article[^>]*>(.*?)</article>", flags=re.IGNORECASE | re.DOTALL)
_BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", flags=re.IGNORECASE | re.DOTALL)


@dataclass
class UrlIngestResult:
    ok: bool
    url: str
    title: str
    text: str
    fetched_at: str
    error_code: str | None = None
    error_message: str | None = None
    http_status: int | None = None


def is_valid_http_url(raw: str) -> bool:
    url = (raw or "").strip()
    if not url:
        return False
    try:
        parsed = parse.urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_url_lines(lines: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    valid: list[str] = []
    invalid: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"[,\s]+", line) if p.strip()]
        for part in parts:
            if not is_valid_http_url(part):
                invalid.append({"line": str(idx), "url": part, "reason": "invalid_url"})
                continue
            if part in seen:
                continue
            seen.add(part)
            valid.append(part)
    return valid, invalid


def load_urls_from_inputs(url_args: list[str] | None, url_file: str | None) -> tuple[list[str], list[dict[str, str]]]:
    lines: list[str] = []
    if url_args:
        lines.extend(url_args)
    if url_file:
        try:
            with open(url_file, "r", encoding="utf-8") as f:
                lines.extend(f.read().splitlines())
        except OSError as exc:
            return [], [{"line": "0", "url": url_file, "reason": f"url_file_read_error:{exc}"}]
    return parse_url_lines(lines)


def _extract_title(html: str) -> str:
    for pattern in (_TITLE_META_RE, _WECHAT_TITLE_RE, _TITLE_TAG_RE):
        matched = pattern.search(html)
        if matched:
            return _strip_html(matched.group(1))
    return "Untitled Web Document"


def _strip_html(html: str) -> str:
    cleaned = _SCRIPT_STYLE_RE.sub(" ", html)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _extract_main_content(html: str, *, is_wechat: bool) -> str:
    candidates: list[str] = []
    if is_wechat:
        matched = _WECHAT_CONTENT_RE.search(html)
        if matched:
            candidates.append(matched.group(1))
    for pattern in (_ARTICLE_RE, _BODY_RE):
        matched = pattern.search(html)
        if matched:
            candidates.append(matched.group(1))
    if not candidates:
        candidates = [html]
    texts = [_strip_html(c) for c in candidates]
    texts = [t for t in texts if t]
    if not texts:
        return ""
    texts.sort(key=len, reverse=True)
    return texts[0]


def fetch_url_document(url: str, *, timeout_sec: int = 10, min_text_chars: int = 120) -> UrlIngestResult:
    fetched_at = datetime.now(timezone.utc).isoformat()
    if not is_valid_http_url(url):
        return UrlIngestResult(
            ok=False,
            url=url,
            title="",
            text="",
            fetched_at=fetched_at,
            error_code="invalid_url",
            error_message="URL must be absolute http/https address",
        )

    is_wechat = "mp.weixin.qq.com" in url.lower()
    req = request.Request(
        url=url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            )
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            status = int(resp.status or 200)
            body = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
    except error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        reason = "access_restricted" if code in {401, 403, 429} else "network_error"
        return UrlIngestResult(
            ok=False,
            url=url,
            title="",
            text="",
            fetched_at=fetched_at,
            http_status=code if code > 0 else None,
            error_code=reason,
            error_message=f"http_error:{code}",
        )
    except (error.URLError, TimeoutError) as exc:
        return UrlIngestResult(
            ok=False,
            url=url,
            title="",
            text="",
            fetched_at=fetched_at,
            error_code="network_error",
            error_message=str(exc),
        )

    try:
        html = body.decode(charset, errors="replace")
    except LookupError:
        html = body.decode("utf-8", errors="replace")

    title = _extract_title(html)
    text = _extract_main_content(html, is_wechat=is_wechat)
    if len(text) < min_text_chars:
        return UrlIngestResult(
            ok=False,
            url=url,
            title=title,
            text="",
            fetched_at=fetched_at,
            http_status=status,
            error_code="empty_content",
            error_message="extracted body text too short",
        )
    return UrlIngestResult(
        ok=True,
        url=url,
        title=title,
        text=text,
        fetched_at=fetched_at,
        http_status=status,
    )


def structured_url_failure(row: UrlIngestResult) -> dict[str, str]:
    payload = {
        "source_type": "url",
        "source_uri": row.url,
        "reason": row.error_code or "unknown",
        "detail": row.error_message or "",
    }
    if row.http_status is not None:
        payload["http_status"] = str(row.http_status)
    return payload


def url_meta_json(*, fetched_at: str, http_status: int | None) -> dict[str, str]:
    payload: dict[str, str] = {"fetched_at": fetched_at}
    if http_status is not None:
        payload["http_status"] = str(http_status)
    return payload
