from __future__ import annotations

from dataclasses import dataclass, field
import re
from urllib import error, parse, request


HP_LINE_RE = re.compile(
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
SECTION_RE = re.compile(r"^\[\s*(?P<section>[^\]:]+?)\s*(?::\s*(?P<name>[^\]]+?)\s*)?\]$")
MONEY_LINE_RE = re.compile(r"^(?P<kind>[A-Za-zА-Яа-я]+)\s*:\s*(?P<value>\d+)\s*$")
SPELL_SLOT_RE = re.compile(r"^(?P<level>[1-6])\s*:\s*(?P<current>\d+)\s*/\s*(?P<max>\d+)\s*$")

DOC_LINK_PATTERNS = (
    re.compile(r"https?://docs\.google\.com/document/d/(?P<doc_id>[-\w]+)"),
    re.compile(r"https?://docs\.google\.com/document/u/\d+/d/(?P<doc_id>[-\w]+)"),
    re.compile(r"https?://drive\.google\.com/open\?id=(?P<doc_id>[-\w]+)"),
)

HIDDEN_SYNC_CHARS = {
    ord("\ufeff"): None,
    ord("\u200b"): None,
    ord("\u200c"): None,
    ord("\u200d"): None,
    ord("\u200e"): None,
    ord("\u200f"): None,
    ord("\u2060"): None,
    ord("\u2066"): None,
    ord("\u2067"): None,
    ord("\u2068"): None,
    ord("\u2069"): None,
}

HP_SECTION_NAMES = {"hp", "хп"}
MONEY_SECTION_NAMES = {"money", "деньги"}
SPELL_SECTION_NAMES = {"spell_slots", "spellslots", "ячейки_заклинаний", "ячейкизаклинаний"}
MONEY_ALIASES = {
    "cc": "cc",
    "sc": "sc",
    "gc": "gc",
    "мм": "cc",
    "см": "sc",
    "зм": "gc",
}


@dataclass(slots=True)
class ParsedSyncLine:
    name: str
    current_hp: int
    max_hp: int
    temp_hp: int


@dataclass(slots=True)
class ParsedSpellSlotsSection:
    name: str
    slots: dict[int, tuple[int, int]]


@dataclass(slots=True)
class ParsedMoneySection:
    name: str
    money: dict[str, int]


@dataclass(slots=True)
class ParsedSyncData:
    hp_lines: list[ParsedSyncLine] = field(default_factory=list)
    money_sections: list[ParsedMoneySection] = field(default_factory=list)
    spell_sections: list[ParsedSpellSlotsSection] = field(default_factory=list)
    issues: list["ParseIssue"] = field(default_factory=list)


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


def _normalize_sync_line(raw_line: str) -> str:
    return raw_line.translate(HIDDEN_SYNC_CHARS).strip()


def _normalize_section_name(value: str) -> str:
    return value.strip().casefold().replace(" ", "_")


def parse_sync_text(text: str) -> ParsedSyncData:
    parsed = ParsedSyncData()
    inside_block = False
    current_section = "hp"
    current_money_owner = ""
    current_spell_owner = ""
    money_sections: dict[str, dict[str, int]] = {}
    spell_sections: dict[str, dict[int, tuple[int, int]]] = {}

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = _normalize_sync_line(raw_line)

        if line == ">>>":
            inside_block = not inside_block
            if inside_block:
                current_section = "hp"
                current_spell_owner = ""
            continue

        if not inside_block or not line:
            continue

        section_match = SECTION_RE.match(line)
        if section_match:
            section_name = _normalize_section_name(section_match.group("section"))
            section_target = (section_match.group("name") or "").strip()
            if section_name in HP_SECTION_NAMES:
                current_section = "hp"
                current_money_owner = ""
                current_spell_owner = ""
                continue
            if section_name in MONEY_SECTION_NAMES and section_target:
                current_section = "money"
                current_money_owner = section_target
                current_spell_owner = ""
                money_sections.setdefault(current_money_owner, {"cc": 0, "sc": 0, "gc": 0})
                continue
            if section_name in SPELL_SECTION_NAMES and section_target:
                current_section = "spell_slots"
                current_money_owner = ""
                current_spell_owner = section_target
                spell_sections.setdefault(current_spell_owner, {})
                continue

            parsed.issues.append(ParseIssue(line_number=line_number, line=line))
            continue

        if current_section == "hp":
            match = HP_LINE_RE.match(line)
            if not match:
                parsed.issues.append(ParseIssue(line_number=line_number, line=line))
                continue
            parsed.hp_lines.append(
                ParsedSyncLine(
                    name=match.group("name").strip(),
                    current_hp=int(match.group("current")),
                    max_hp=max(1, int(match.group("max"))),
                    temp_hp=max(0, int(match.group("temp") or 0)),
                )
            )
            continue

        if current_section == "money":
            match = MONEY_LINE_RE.match(line)
            if not match:
                parsed.issues.append(ParseIssue(line_number=line_number, line=line))
                continue
            if not current_money_owner:
                parsed.issues.append(ParseIssue(line_number=line_number, line=line))
                continue
            money_key = MONEY_ALIASES.get(match.group("kind").strip().casefold())
            if money_key is None:
                parsed.issues.append(ParseIssue(line_number=line_number, line=line))
                continue
            money_sections.setdefault(current_money_owner, {"cc": 0, "sc": 0, "gc": 0})[money_key] = max(
                0, int(match.group("value"))
            )
            continue

        if current_section == "spell_slots":
            match = SPELL_SLOT_RE.match(line)
            if not match or not current_spell_owner:
                parsed.issues.append(ParseIssue(line_number=line_number, line=line))
                continue
            level = int(match.group("level"))
            current = int(match.group("current"))
            maximum = max(0, int(match.group("max")))
            spell_sections.setdefault(current_spell_owner, {})[level] = (max(0, min(current, maximum)), maximum)
            continue

        parsed.issues.append(ParseIssue(line_number=line_number, line=line))

    for name, money in money_sections.items():
        parsed.money_sections.append(ParsedMoneySection(name=name, money=money))

    for name, slots in spell_sections.items():
        parsed.spell_sections.append(ParsedSpellSlotsSection(name=name, slots=slots))

    return parsed


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
