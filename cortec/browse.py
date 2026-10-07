"""
Interactive memory browser — pure filter, paginate, and command logic.

The `cortec browse` CLI command is a thin I/O loop over these functions. Keeping
the navigation and filtering logic here (and side-effect free) makes it fully
unit-testable without driving a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

DEFAULT_PAGE_SIZE = 10

# Commands that only change the view (handled by `step`); open/forget/quit are
# side-effectful and handled by the CLI loop instead.
_NAV_COMMANDS = {"type", "project", "search", "clear", "next", "prev", "page"}
_ALL_COMMANDS = _NAV_COMMANDS | {"open", "forget", "help", "quit", "noop"}

_ALIASES = {
    "n": "next", "p": "prev", "q": "quit", "s": "search",
    "t": "type", "h": "help", "?": "help", "o": "open", "f": "forget",
}


@dataclass(frozen=True)
class BrowseState:
    """A snapshot of the browser's active filters and page position."""
    project: str | None = None
    type: str | None = None
    query: str | None = None
    page: int = 0


def apply_filters(
    memories: list[dict],
    project: str | None = None,
    type_: str | None = None,
    query: str | None = None,
) -> list[dict]:
    """Filter memories by exact project, exact type, and case-insensitive summary substring."""
    out = memories
    if project:
        out = [m for m in out if m.get("project") == project]
    if type_:
        out = [m for m in out if m.get("type") == type_]
    if query:
        q = query.lower()
        out = [m for m in out if q in (m.get("summary") or "").lower()]
    return out


def paginate(
    items: list[dict],
    page: int,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[dict], int, int]:
    """Return (page_items, total_pages, clamped_page) for a 0-indexed page."""
    page_size = max(1, page_size)
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start:start + page_size], total_pages, page


def parse_command(raw: str | None) -> tuple[str, str]:
    """
    Parse a browse input line into (command, argument).

    Recognises short aliases (n/p/q/s/t/h/o/f). Empty input is `noop`;
    anything unrecognised is `unknown` with the raw text as the argument.
    """
    raw = (raw or "").strip()
    if not raw:
        return ("noop", "")
    parts = raw.split(maxsplit=1)
    cmd = _ALIASES.get(parts[0].lower(), parts[0].lower())
    arg = parts[1].strip() if len(parts) > 1 else ""
    if cmd in _ALL_COMMANDS:
        return (cmd, arg)
    return ("unknown", raw)


def step(state: BrowseState, cmd: str, arg: str = "") -> tuple[BrowseState, str]:
    """
    Apply a navigation/filter command to the state, returning (new_state, message).

    Pure: handles only view-changing commands. Side-effectful commands
    (open, forget, quit) are left for the caller's loop.
    """
    if cmd == "type":
        return replace(state, type=arg or None, page=0), f"type = {arg or 'any'}"
    if cmd == "project":
        return replace(state, project=arg or None, page=0), f"project = {arg or 'all'}"
    if cmd == "search":
        return replace(state, query=arg or None, page=0), f"search = {arg or 'none'}"
    if cmd == "clear":
        return replace(state, project=None, type=None, query=None, page=0), "filters cleared"
    if cmd == "next":
        return replace(state, page=state.page + 1), ""
    if cmd == "prev":
        return replace(state, page=max(0, state.page - 1)), ""
    if cmd == "page":
        try:
            target = max(1, int(arg)) - 1
        except (ValueError, TypeError):
            return state, f"invalid page number: {arg!r}"
        return replace(state, page=target), ""
    return state, ""


def visible(
    state: BrowseState,
    memories: list[dict],
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[dict], int, int, int]:
    """Return (page_items, total_pages, clamped_page, total_filtered) for a state."""
    filtered = apply_filters(memories, state.project, state.type, state.query)
    page_items, total_pages, page = paginate(filtered, state.page, page_size)
    return page_items, total_pages, page, len(filtered)
