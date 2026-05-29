import json
from pathlib import Path

from src.adapters.elasticsearch.field_caps import (
    FieldDefinition,
    map_elastic_field,
    parse_field_caps,
    unmap_elastic_field,
)

FIX = Path(__file__).parent / "fixtures" / "fieldcaps_response.json"


def _defs() -> dict[str, FieldDefinition]:
    return {
        "smb.service": FieldDefinition(
            "smb.service", "text", aggregatable=False, searchable=True
        ),
        "smb.service.keyword": FieldDefinition(
            "smb.service.keyword", "keyword", aggregatable=True, searchable=True
        ),
        "agent.ip": FieldDefinition(
            "agent.ip", "ip", aggregatable=True, searchable=True
        ),
        "event.acknowledged": FieldDefinition(
            "event.acknowledged", "boolean", aggregatable=True, searchable=True
        ),
    }


def test_map_remaps_nonaggregatable_to_keyword():
    assert map_elastic_field(_defs(), "smb.service") == "smb.service.keyword"


def test_map_leaves_aggregatable_unchanged():
    assert map_elastic_field(_defs(), "agent.ip") == "agent.ip"
    assert map_elastic_field(_defs(), "event.acknowledged") == "event.acknowledged"


def test_unmap_strips_keyword_when_base_nonaggregatable():
    assert unmap_elastic_field(_defs(), "smb.service.keyword") == "smb.service"


def test_parse_field_caps_multitype_prefers_nonaggregatable():
    data = json.loads(FIX.read_text())
    defs = parse_field_caps(data)
    assert "smb.service" in defs
    # when a field has multiple type entries, NON-aggregatable wins
    multi = next((d for d in defs.values() if d.name and not d.aggregatable), None)
    assert multi is not None


def test_parse_field_caps_cache_metadata():
    # Mirrors Go TestFieldMappingCache: parsed defs carry name/type/agg/searchable.
    defs = parse_field_caps(json.loads(FIX.read_text()))
    svc = defs["smb.service"]
    assert svc.name == "smb.service"
    assert svc.field_type == "text"
    assert svc.aggregatable is False
    assert svc.searchable is True
    kw = defs["smb.service.keyword"]
    assert kw.name == "smb.service.keyword"
    assert kw.field_type == "keyword"
    assert kw.aggregatable is True
    assert kw.searchable is True


def test_map_unmap_against_real_fixture():
    # Mirrors Go TestFieldMapping using the real fieldcaps fixture.
    defs = parse_field_caps(json.loads(FIX.read_text()))
    # Exists as keyword and not already aggregatable -> remapped
    assert map_elastic_field(defs, "smb.service") == "smb.service.keyword"
    # Only keyword variant is aggregatable -> keyword stripped on unmap
    assert unmap_elastic_field(defs, "smb.service.keyword") == "smb.service"


def test_map_multitype_collision_prefers_keyword():
    # Mirrors Go TestFieldMappingCollisions: multi-type text/keyword fields
    # are parsed as non-aggregatable, so map remaps to the .keyword twin.
    defs = parse_field_caps(json.loads(FIX.read_text()))
    for field in (
        "event.module",
        "event.category",
        "event.dataset",
        "event.kind",
        "event.outcome",
        "event.type",
        "event.timezone",
    ):
        assert map_elastic_field(defs, field) == field + ".keyword"
