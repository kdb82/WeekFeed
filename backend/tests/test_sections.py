from weekfeed.sections import SECTION_TITLES, normalize_sections, render_record, sections_schema


def test_titles_per_kind():
    assert SECTION_TITLES["standup"] == ["Yesterday", "Today", "Blockers"]
    assert SECTION_TITLES["weekly"] == ["Done", "Next", "Blockers"]


def test_normalize_orders_fills_and_drops():
    got = normalize_sections("standup", [
        {"title": "Blockers", "text": " - db access "}, {"title": "Extra", "text": "x"}, {"title": "Yesterday", "text": "- a"},
    ])
    assert got == [
        {"title": "Yesterday", "text": "- a"}, {"title": "Today", "text": ""}, {"title": "Blockers", "text": "- db access"},
    ]


def test_render_record_uses_none_for_empty_sections():
    text = render_record([{"title": "Yesterday", "text": "- a"}, {"title": "Today", "text": "  "}])
    assert text == "Yesterday\n- a\n\nToday\nNone"


def test_schema_restricts_titles():
    schema = sections_schema("weekly")
    item = schema["properties"]["sections"]["items"]
    assert item["properties"]["title"]["enum"] == ["Done", "Next", "Blockers"]
    assert schema["additionalProperties"] is False
