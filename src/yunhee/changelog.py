import re
from dataclasses import dataclass
from importlib.resources import files

HEADER_RE = re.compile(r"^## \[(?P<version>[^\]]+)\](?:\s*-\s*(?P<date>\S+))?\s*$", re.MULTILINE)


@dataclass
class Entry:
    version: str
    date: str
    body: str

    def render(self) -> str:
        date = f" - {self.date}" if self.date else ""
        return f"## [{self.version}]{date}\n{self.body}".rstrip()


def version_key(version: str) -> tuple[int, ...]:
    """'0.1.10' > '0.1.9' 이 되도록 숫자 튜플로 비교한다. 숫자가 아닌 조각은 0."""
    return tuple(int(p) if p.isdigit() else 0 for p in version.strip().lstrip("v").split("."))


def read_text() -> str:
    return files("yunhee").joinpath("CHANGELOG.md").read_text(encoding="utf-8")


def parse(text: str) -> list[Entry]:
    """CHANGELOG 텍스트를 버전 항목으로 나눈다. 최신 버전이 먼저 오도록 정렬."""
    matches = list(HEADER_RE.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip("\n")
        entries.append(Entry(m.group("version"), m.group("date") or "", body))
    entries.sort(key=lambda e: version_key(e.version), reverse=True)
    return entries


def select(
    entries: list[Entry],
    version: str | None = None,
    since: str | None = None,
    show_all: bool = False,
    current: str | None = None,
) -> list[Entry]:
    """version: 해당 버전만 / since: 그 버전 이후(미포함)~최신 / show_all: 전부 / 아무것도 없으면 current 버전."""
    if show_all:
        return entries
    if since:
        key = version_key(since)
        return [e for e in entries if version_key(e.version) > key]
    target = version or current
    if target is None:
        return entries[:1]
    key = version_key(target)
    return [e for e in entries if version_key(e.version) == key]


def changes_since(old_version: str, new_version: str) -> list[Entry]:
    """old_version 이후 ~ new_version 까지의 항목 (REPL 버전 변경 안내용)."""
    old_key, new_key = version_key(old_version), version_key(new_version)
    return [e for e in parse(read_text()) if old_key < version_key(e.version) <= new_key]
