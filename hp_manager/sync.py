from __future__ import annotations

from dataclasses import dataclass
import re
from urllib import error, parse, request


LINE_RE = re.compile(
    r"""
    ^\s*
    (?P<name>[^:()]+?)
    \s*:\s*
    (?P<current>\d+)\s*/\s*(?P<max>\d+)
    (?:\s*\(\s*(?P<temp>\d+)\s*\))?
    \s*$
    """,
    re.VERBOSE,
)

DOC_LINK_PATTERNS = (
    re.compile(r"https?://docs\.google\.com/document/d/(?P<doc_id>[-\w]+)"),
    re.compile(r"https?://docs\.google\.com/document/u/\d+/d/(?P<doc_id>[-\w]+)"),
    re.compile(r"https?://drive\.google\.com/open\?id=(?P<doc_id>[-\w]+)"),
)


@dataclass(slots=True)
class ParsedSyncLine:
    name: str
    current_hp: int
    max_hp: int
    temp_hp: int


@dataclass(slots=True)
class ParseIssue:
    line_number: int
    line: str


class SyncFetchError(Exception):
    """Raised when external sync text cannot be fetched."""

    def __init__(self, message_key: str, **context: object) -> None:
        super().__init__(message_key)
        self.message_key = message_key
        self.context = context


def parse_sync_text(text: str) -> tuple[list[ParsedSyncLine], list[ParseIssue]]:
    parsed: list[ParsedSyncLine] = []
    errors: list[ParseIssue] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        match = LINE_RE.match(line)
        if not match:
            errors.append(ParseIssue(line_number=line_number, line=line))
            continue

        parsed.append(
            ParsedSyncLine(
                name=match.group("name").strip(),
                current_hp=int(match.group("current")),
                max_hp=max(1, int(match.group("max"))),
                temp_hp=max(0, int(match.group("temp") or 0)),
            )
        )

    return parsed, errors


def extract_google_doc_id(source: str) -> str:
    cleaned = source.strip()
    if not cleaned:
        raise SyncFetchError("error.sync.no_link")

    for pattern in DOC_LINK_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            return match.group("doc_id")

    parsed_source = parse.urlparse(cleaned)
    if parsed_source.netloc.endswith("google.com"):
        query_id = parse.parse_qs(parsed_source.query).get("id", [])
        if query_id:
            return query_id[0]

    raise SyncFetchError("error.sync.bad_link")


def build_google_doc_export_url(source: str) -> str:
    doc_id = extract_google_doc_id(source)
    return f"https://docs.google.com/document/d/{doc_id}/export?format=txt"


def fetch_google_doc_text(source: str, timeout_seconds: int = 15) -> str:
    export_url = build_google_doc_export_url(source)
    req = request.Request(
        export_url,
        headers={
            "User-Agent": "HP-Manager/1.0",
            "Accept": "text/plain, text/*;q=0.9, */*;q=0.5",
        },
    )

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
    except error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise SyncFetchError("error.sync.access_denied") from exc
        if exc.code == 404:
            raise SyncFetchError("error.sync.not_found") from exc
        raise SyncFetchError("error.sync.http", code=exc.code) from exc
    except error.URLError as exc:
        raise SyncFetchError("error.sync.network", reason=str(exc.reason)) from exc

    if "text/html" in content_type.lower() and b"<html" in raw[:200].lower():
        raise SyncFetchError("error.sync.html_response")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")
