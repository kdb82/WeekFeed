"""Draft sections: fixed titles per kind, schemas, and rendering."""
from __future__ import annotations

SECTION_TITLES = {
    "standup": ["Yesterday", "Today", "Blockers"],
    "weekly": ["Done", "Next", "Blockers"],
}


def sections_array_schema(titles: list[str]) -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"title": {"type": "string", "enum": titles}, "text": {"type": "string"}},
            "required": ["title", "text"],
            "additionalProperties": False,
        },
    }


def sections_schema(kind: str) -> dict:
    return {
        "type": "object",
        "properties": {"sections": sections_array_schema(SECTION_TITLES[kind])},
        "required": ["sections"],
        "additionalProperties": False,
    }


def normalize_sections(kind: str, sections: list) -> list[dict]:
    """Exactly the kind's titles, in order; unknown titles dropped, missing ones empty."""
    by_title = {s.get("title"): str(s.get("text", "")) for s in sections if isinstance(s, dict)}
    return [{"title": t, "text": by_title.get(t, "").strip()} for t in SECTION_TITLES[kind]]


def render_record(sections: list[dict]) -> str:
    return "\n\n".join(f"{s['title']}\n{s['text'].strip() or 'None'}" for s in sections)
