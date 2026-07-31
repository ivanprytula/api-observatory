"""Unit tests for contract drift pure-Python helpers.

All helpers are deterministic and operate only on in-memory data structures —
no database, no HTTP client needed.
"""

from __future__ import annotations

import pytest

from services.ingestor.repositories.contract_drift import (
    _compatibility_score,
    _diff_contract,
    _event_type,
    _fingerprint,
    _flatten_schema,
    _severity,
    _structure_fingerprint,
    _summary,
)


@pytest.mark.unit
class TestFingerprint:
    def test_identical_payloads_produce_same_hash(self) -> None:
        a = {"z": 1, "a": 2}
        b = {"a": 2, "z": 1}
        assert _fingerprint(a) == _fingerprint(b)

    def test_different_payloads_produce_different_hash(self) -> None:
        assert _fingerprint({"x": 1}) != _fingerprint({"x": 2})

    def test_returns_64_char_hex_string(self) -> None:
        h = _fingerprint({"key": "value"})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_dict_is_stable(self) -> None:
        assert _fingerprint({}) == _fingerprint({})

    def test_structure_fingerprint_ignores_observed_values(self) -> None:
        first = _flatten_schema({"id": 1, "status": "ok"})
        second = _flatten_schema({"id": 99, "status": "degraded"})
        assert _structure_fingerprint(first) == _structure_fingerprint(second)


@pytest.mark.unit
class TestFlattenSchema:
    def test_flat_dict(self) -> None:
        flat = _flatten_schema({"id": 1, "name": "ok"})
        assert flat == {"id": "number", "name": "string"}

    def test_nested_dict_flattens_with_dot_notation(self) -> None:
        flat = _flatten_schema({"payload": {"temp": 20.5, "region": "eu"}})
        assert flat["payload"] == "object"
        assert flat["payload.temp"] == "number"
        assert flat["payload.region"] == "string"

    def test_null_value_typed_as_null(self) -> None:
        flat = _flatten_schema({"missing": None})
        assert flat["missing"] == "null"

    def test_bool_typed_before_number(self) -> None:
        flat = _flatten_schema({"flag": True})
        assert flat["flag"] == "boolean"

    def test_integer_and_fractional_numbers_share_json_number_type(self) -> None:
        integer = _flatten_schema({"amount": 1})
        fractional = _flatten_schema({"amount": 1.5})
        assert integer == fractional == {"amount": "number"}

    def test_list_value_typed_as_array(self) -> None:
        flat = _flatten_schema({"items": [1, 2, 3]})
        assert flat["items"] == "array"
        assert flat["items[]"] == "number"

    def test_object_array_unions_observed_element_fields(self) -> None:
        flat = _flatten_schema(
            {"items": [{"id": 1, "name": "first"}, {"id": 2, "price": 9.5}]}
        )
        assert flat == {
            "items": "array",
            "items[]": "object",
            "items[].id": "number",
            "items[].name": "string",
            "items[].price": "number",
        }

    def test_mixed_element_types_form_deterministic_union(self) -> None:
        first = _flatten_schema({"items": [1, "one", None]})
        second = _flatten_schema({"items": [None, "one", 1]})
        assert first == second
        assert first["items[]"] == "null|number|string"

    def test_nested_arrays_use_repeated_wildcards(self) -> None:
        flat = _flatten_schema({"groups": [[{"id": 1}]]})
        assert flat["groups"] == "array"
        assert flat["groups[]"] == "array"
        assert flat["groups[][]"] == "object"
        assert flat["groups[][].id"] == "number"

    def test_array_analysis_stops_after_twenty_elements(self) -> None:
        elements = [{f"field_{index}": index} for index in range(21)]
        flat = _flatten_schema({"items": elements})
        assert "items[].field_19" in flat
        assert "items[].field_20" not in flat

    def test_empty_nested_object_only_observations_parent(self) -> None:
        flat = _flatten_schema({"meta": {}})
        assert flat["meta"] == "object"
        assert len(flat) == 1


@pytest.mark.unit
class TestDiffContract:
    def test_no_diff_returns_empty_collections(self) -> None:
        schema = {"id": "number", "name": "string"}
        added, removed, changed = _diff_contract(schema, schema)
        assert added == []
        assert removed == []
        assert changed == {}

    def test_added_field_detected(self) -> None:
        prev = {"id": "number"}
        curr = {"id": "number", "email": "string"}
        added, removed, changed = _diff_contract(prev, curr)
        assert added == ["email"]
        assert removed == []
        assert changed == {}

    def test_removed_field_detected(self) -> None:
        prev = {"id": "number", "legacy": "string"}
        curr = {"id": "number"}
        added, removed, changed = _diff_contract(prev, curr)
        assert added == []
        assert removed == ["legacy"]
        assert changed == {}

    def test_type_change_detected(self) -> None:
        prev = {"status": "string"}
        curr = {"status": "object"}
        added, removed, changed = _diff_contract(prev, curr)
        assert added == []
        assert removed == []
        assert changed == {"status": {"from_type": "string", "to_type": "object"}}

    def test_results_are_sorted(self) -> None:
        prev = {"z": "string", "a": "number"}
        curr = {"z": "object", "b": "number"}
        added, removed, changed = _diff_contract(prev, curr)
        assert added == ["b"]
        assert removed == ["a"]
        assert list(changed.keys()) == ["z"]

    def test_null_is_distinct_from_missing(self) -> None:
        present_null = _flatten_schema({"comment": None})
        missing = _flatten_schema({})
        added, removed, changed = _diff_contract(present_null, missing)
        assert added == []
        assert removed == ["comment"]
        assert changed == {}

    def test_concrete_to_null_is_a_type_change(self) -> None:
        concrete = _flatten_schema({"comment": "available"})
        present_null = _flatten_schema({"comment": None})
        added, removed, changed = _diff_contract(concrete, present_null)
        assert added == []
        assert removed == []
        assert changed == {"comment": {"from_type": "string", "to_type": "null"}}

    def test_array_element_field_addition_is_detected(self) -> None:
        baseline = _flatten_schema({"items": [{"id": 1}]})
        current = _flatten_schema({"items": [{"id": 1, "price": 9.5}]})
        added, removed, changed = _diff_contract(baseline, current)
        assert added == ["items[].price"]
        assert removed == []
        assert changed == {}

    def test_array_element_field_removal_is_detected(self) -> None:
        baseline = _flatten_schema({"items": [{"id": 1, "price": 9.5}]})
        current = _flatten_schema({"items": [{"id": 1}]})
        added, removed, changed = _diff_contract(baseline, current)
        assert added == []
        assert removed == ["items[].price"]
        assert changed == {}

    def test_empty_array_is_inconclusive_for_element_removals(self) -> None:
        baseline = _flatten_schema({"items": [{"id": 1, "price": 9.5}]})
        current = _flatten_schema({"items": []})
        added, removed, changed = _diff_contract(baseline, current)
        assert added == []
        assert removed == []
        assert changed == {}


@pytest.mark.unit
class TestEventType:
    def test_no_changes_returns_none(self) -> None:
        assert _event_type([], [], {}) == "none"

    def test_only_added_fields_returns_non_breaking(self) -> None:
        assert _event_type(["new_field"], [], {}) == "non_breaking"

    def test_removed_field_returns_breaking(self) -> None:
        assert _event_type([], ["old_field"], {}) == "breaking"

    def test_type_change_returns_breaking(self) -> None:
        assert (
            _event_type([], [], {"f": {"from_type": "str", "to_type": "int"}})
            == "breaking"
        )

    def test_removed_and_added_returns_breaking(self) -> None:
        assert _event_type(["new"], ["old"], {}) == "breaking"


@pytest.mark.unit
class TestCompatibilityScore:
    def test_no_changes_returns_max(self) -> None:
        assert _compatibility_score([], [], {}) == 100.0

    def test_penalty_for_added_field(self) -> None:
        score = _compatibility_score(["f1", "f2"], [], {})
        assert score == 100.0 - 2 * 2.0

    def test_penalty_for_removed_field(self) -> None:
        score = _compatibility_score([], ["f1"], {})
        assert score == 100.0 - 20.0

    def test_penalty_for_type_change(self) -> None:
        score = _compatibility_score([], [], {"f": {}})
        assert score == 100.0 - 15.0

    def test_score_floored_at_zero(self) -> None:
        # 6 removed fields × 20 penalty = 120 > 100 → floor at 0
        score = _compatibility_score([], ["a", "b", "c", "d", "e", "f"], {})
        assert score == 0.0


@pytest.mark.unit
class TestSeverity:
    def test_none_event_type_returns_none(self) -> None:
        assert _severity("none", 100.0) == "none"

    def test_high_score_returns_low(self) -> None:
        assert _severity("non_breaking", 95.0) == "low"

    def test_medium_range_returns_medium(self) -> None:
        assert _severity("breaking", 80.0) == "medium"

    def test_low_score_returns_high(self) -> None:
        assert _severity("breaking", 60.0) == "high"

    def test_very_low_score_returns_critical(self) -> None:
        assert _severity("breaking", 30.0) == "critical"


@pytest.mark.unit
class TestSummary:
    def test_no_event_returns_stable_message(self) -> None:
        msg = _summary("none", [], [], {})
        assert msg == "No schema drift detected."

    def test_breaking_with_removed_includes_count(self) -> None:
        msg = _summary("breaking", [], ["field_a"], {})
        assert "breaking" in msg
        assert "removed=1" in msg

    def test_non_breaking_with_added_includes_count(self) -> None:
        msg = _summary("non_breaking", ["new_field"], [], {})
        assert "added=1" in msg

    def test_all_change_types_represented(self) -> None:
        msg = _summary("breaking", ["f1"], ["f2"], {"f3": {}})
        assert "added=1" in msg
        assert "removed=1" in msg
        assert "type_changed=1" in msg
