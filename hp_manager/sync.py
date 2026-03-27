from __future__ import annotations

from dataclasses import dataclass, field
import re
from urllib import error, parse, request


FIELD_RE = re.compile(r"^(?P<label>[^:]+?)\s*:\s*(?P<value>.*)$")
HEALTH_VALUE_RE = re.compile(
    r"""
    ^\s*
    (?P<current>\d+)\s*/\s*(?P<max>\d+)
    (?:\s*\(\s*(?P<temp>\d+)\s*\))?
    \s*$
    """,
    re.VERBOSE,
)
SPELL_SLOT_RE = re.compile(r"^(?P<level>[1-9])\s*:\s*(?P<current>\d+)\s*/\s*(?P<max>\d+)\s*$")
MONEY_TOKEN_RE = re.compile(r"(?P<value>\d+)\s*(?P<kind>[A-Za-zА-Яа-я]+)")

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

NAME_FIELD_NAMES = {"name", "имя"}
HEALTH_FIELD_NAMES = {"health", "hp", "здоровье", "хп"}
MONEY_FIELD_NAMES = {"coins", "coin", "money", "монеты", "деньги"}
SPELL_FIELD_NAMES = {"spell_slots", "spellslots", "spells", "ячейки_заклинаний", "ячейкизаклинаний"}
MONEY_ALIASES = {
    "cc": "cc",
    "sc": "sc",
    "gc": "gc",
    "мм": "cc",
    "см": "sc",
    "зм": "gc",
}
SPELL_SLOT_LEVELS = tuple(range(1, 10))


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


def _default_money() -> dict[str, int]:
    return {"cc": 0, "sc": 0, "gc": 0}


def _default_spell_slots() -> dict[int, tuple[int, int]]:
    return {level: (0, 0) for level in SPELL_SLOT_LEVELS}


def _parse_money_value(value: str) -> dict[str, int] | None:
    money = _default_money()
    stripped = value.strip()
    if not stripped:
        return money

    cursor = 0
    matched = False
    for match in MONEY_TOKEN_RE.finditer(stripped):
        if stripped[cursor:match.start()].strip():
            return None
        money_key = MONEY_ALIASES.get(match.group("kind").strip().casefold())
        if money_key is None:
            return None
        money[money_key] = max(0, int(match.group("value")))
        cursor = match.end()
        matched = True

    if stripped[cursor:].strip():
        return None

    return money if matched else None


def parse_sync_text(text: str) -> ParsedSyncData:
    parsed = ParsedSyncData()
    inside_block = False
    collecting_spell_slots = False
    current_record: dict[str, object] | None = None

    def finalize_record() -> None:
        nonlocal current_record
        if current_record is None:
            return

        name = str(current_record["name"]).strip()
        if not name:
            current_record = None
            return

        current_hp, max_hp, temp_hp = current_record.get("health", (0, 1, 0))  # type: ignore[assignment]
        money = dict(current_record.get("money", _default_money()))  # type: ignore[arg-type]
        slots = dict(current_record.get("spell_slots", _default_spell_slots()))  # type: ignore[arg-type]

        parsed.hp_lines.append(
            ParsedSyncLine(
                name=name,
                current_hp=max(0, int(current_hp)),
                max_hp=max(1, int(max_hp)),
                temp_hp=max(0, int(temp_hp)),
            )
        )
        parsed.money_sections.append(ParsedMoneySection(name=name, money=money))
        parsed.spell_sections.append(ParsedSpellSlotsSection(name=name, slots=slots))
        current_record = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = _normalize_sync_line(raw_line)

        if line == ">>>":
            if inside_block:
                finalize_record()
                collecting_spell_slots = False
                inside_block = False
            else:
                inside_block = True
                collecting_spell_slots = False
                current_record = None
            continue

        if not inside_block:
            continue

        if not line:
            collecting_spell_slots = False
            continue

        if collecting_spell_slots and current_record is not None:
            spell_match = SPELL_SLOT_RE.match(line)
            if spell_match:
                level = int(spell_match.group("level"))
                current = int(spell_match.group("current"))
                maximum = max(0, int(spell_match.group("max")))
                spell_slots = current_record.setdefault("spell_slots", _default_spell_slots())
                if isinstance(spell_slots, dict):
                    spell_slots[level] = (max(0, min(current, maximum)), maximum)
                continue
            collecting_spell_slots = False

        field_match = FIELD_RE.match(line)
        if not field_match:
            parsed.issues.append(ParseIssue(line_number=line_number, line=line))
            continue

        field_name = _normalize_section_name(field_match.group("label"))
        field_value = field_match.group("value").strip()

        if field_name in NAME_FIELD_NAMES:
            if not field_value:
                parsed.issues.append(ParseIssue(line_number=line_number, line=line))
                collecting_spell_slots = False
                continue
            finalize_record()
            current_record = {
                "name": field_value,
                "health": (0, 1, 0),
                "money": _default_money(),
                "spell_slots": _default_spell_slots(),
            }
            collecting_spell_slots = False
            continue

        if current_record is None:
            parsed.issues.append(ParseIssue(line_number=line_number, line=line))
            collecting_spell_slots = False
            continue

        if field_name in HEALTH_FIELD_NAMES:
            health_match = HEALTH_VALUE_RE.match(field_value)
            if not health_match:
                parsed.issues.append(ParseIssue(line_number=line_number, line=line))
                collecting_spell_slots = False
                continue
            current_record["health"] = (
                int(health_match.group("current")),
                max(1, int(health_match.group("max"))),
                max(0, int(health_match.group("temp") or 0)),
            )
            collecting_spell_slots = False
            continue

        if field_name in MONEY_FIELD_NAMES:
            money = _parse_money_value(field_value)
            if money is None:
                parsed.issues.append(ParseIssue(line_number=line_number, line=line))
                collecting_spell_slots = False
                continue
            current_record["money"] = money
            collecting_spell_slots = False
            continue

        if field_name in SPELL_FIELD_NAMES:
            collecting_spell_slots = True
            continue

        parsed.issues.append(ParseIssue(line_number=line_number, line=line))

    if inside_block:
        finalize_record()

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
