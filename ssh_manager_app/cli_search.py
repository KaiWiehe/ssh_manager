"""Pure fuzzy matching and ancestor-preserving terminal tree projection."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

from .session_catalog import CatalogEntry, SOURCE_LABELS

_ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]")


def safe_text(value: str, *, multiline: bool = False) -> str:
    value = _ANSI.sub("", str(value)).replace("\t", "    ")
    return "".join(c if unicodedata.category(c)[0] != "C" or (multiline and c == "\n")
                   else " " if c in "\r\n" else "" for c in value)


def fuzzy_score(query: str, text: str) -> int | None:
    query, text = query.casefold(), text.casefold()
    if not query:
        return 0
    at, score, last = 0, 0, -2
    for char in query:
        found = text.find(char, at)
        if found < 0:
            return None
        score += 10 + (8 if found == last + 1 else 0) + (12 if found == 0 or not text[found - 1].isalnum() else 0)
        score -= min(found - at, 8)
        last, at = found, found + 1
    return score


@dataclass
class SearchFilters:
    sources: set[str] = field(default_factory=lambda: set(SOURCE_LABELS))
    folder: tuple[str, ...] = ()
    view: str = "all"


@dataclass(frozen=True)
class TreeRow:
    path: tuple[str, ...]
    depth: int
    label: str
    entry: CatalogEntry | None = None
    expanded: bool = True

    @property
    def identity(self):
        return ("entry", self.entry.identity) if self.entry else ("folder", self.path)


def matched_entries(entries, query: str, filters: SearchFilters):
    matches = []
    for entry in entries:
        session = entry.session
        source = "app" if session.source == "ssh_alias" else session.source
        path = tuple(session.folder_path)
        if source not in filters.sources or path[:len(filters.folder)] != filters.folder:
            continue
        if filters.view == "favorites" and not entry.favorite:
            continue
        if filters.view == "recent" and not entry.recent:
            continue
        fields = [session.display_name, "/".join(path), session.hostname, entry.user,
                  session.username, SOURCE_LABELS.get(source, source), entry.note]
        score = 0
        for word in query.split():
            scores = [value + (20 if index == 0 else 0)
                      for index, text in enumerate(fields)
                      if (value := fuzzy_score(word, safe_text(text))) is not None]
            if not scores:
                break
            score += max(scores)
        else:
            matches.append((entry, score))
    return matches


def tree_rows(entries, query: str, filters: SearchFilters, collapsed: set | None = None):
    root = {"folders": {}, "entries": [], "score": 0}
    for entry, score in matched_entries(entries, query, filters):
        node = root
        for folder in entry.session.folder_path:
            node = node["folders"].setdefault(folder, {"folders": {}, "entries": [], "score": 0})
            node["score"] = max(node["score"], score)
        node["entries"].append((entry, score))
    rows = []

    def visit(node, path):
        for folder, child in sorted(node["folders"].items(), key=lambda item: (-item[1]["score"], item[0].casefold(), item[0])):
            next_path = (*path, folder)
            expanded = bool(query.strip()) or next_path not in (collapsed or set())
            rows.append(TreeRow(next_path, len(path), safe_text(folder), expanded=expanded))
            if expanded:
                visit(child, next_path)
        for entry, score in sorted(node["entries"], key=lambda item: (-item[1], item[0].session.display_name.casefold(), item[0].identity)):
            rows.append(TreeRow(path, len(path), safe_text(entry.session.display_name), entry))

    visit(root, ())
    return rows


def entry_details(entry: CatalogEntry) -> str:
    s = entry.session
    source = "app" if s.source == "ssh_alias" else s.source
    lines = [s.display_name, "", "Ordner: " + (" / ".join(s.folder_path) or "(Wurzel)"),
             "Quelle: " + SOURCE_LABELS.get(source, source)]
    if s.is_ssh_config_session:
        lines.extend(["Alias: " + s.display_name, "Host / Port / Benutzer: aus SSH-Konfiguration",
                      "Die geladenen Angaben können durch Include/Match abweichen."])
    else:
        lines.extend(["Host: " + s.hostname, "Port: " + str(s.port),
                      "Benutzer: " + (entry.user or "wird vor dem Start abgefragt")])
    lines.extend(["Favorit: " + ("ja" if entry.favorite else "nein"),
                  "Zuletzt verwendet: " + ("ja" if entry.recent else "nein"), "", "Notiz:", entry.note or "Keine Notiz."])
    return safe_text("\n".join(lines), multiline=True)
