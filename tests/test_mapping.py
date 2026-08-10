import pytest

from quote_agent.mapping import ALIASES, FIELD_PATHS, normalize_label, resolve_field


def test_normalize_label_strips_punctuation_case_and_whitespace():
    assert normalize_label("Driver's Licence") == "driver s licence"
    assert normalize_label("  Marital   Status?  ") == "marital status"
    assert normalize_label("When would you like your insurance to start?") == (
        "when would you like your insurance to start"
    )


def test_every_alias_target_is_a_known_field_path():
    unknown = {path for path in ALIASES.values() if path not in FIELD_PATHS}
    assert unknown == set()


@pytest.mark.parametrize(
    "label,expected_path",
    [
        ("Postal Code", "address.postal_code"),
        ("Driver's licence", "identity.licence_number"),
        ("MARITAL STATUS", "identity.marital_status"),
        ("Do you have winter tires?", "vehicles[].winter_tires"),
        ("Do you have any tickets or convictions in the past 3 years?", "insurance_history.convictions_last_3_years"),
    ],
)
def test_resolve_field_matches_known_aliases_case_and_punctuation_insensitively(label, expected_path):
    assert resolve_field(label) == expected_path


def test_resolve_field_returns_none_without_fallback_when_unmatched():
    assert resolve_field("Some completely novel field nobody has seen") is None


def test_resolve_field_uses_llm_fallback_when_alias_misses():
    def fake_llm(label: str) -> str | None:
        assert label == "A brand new question"
        return "identity.gender"

    assert resolve_field("A brand new question", llm_fallback=fake_llm) == "identity.gender"


def test_resolve_field_passes_through_genuine_no_match_from_fallback():
    def fake_llm(label: str) -> str | None:
        return None

    assert resolve_field("Something truly unrelated", llm_fallback=fake_llm) is None


def test_resolve_field_rejects_hallucinated_field_path_from_fallback():
    def fake_llm(label: str) -> str | None:
        return "identity.social_security_number"  # not a real field

    with pytest.raises(ValueError):
        resolve_field("Weird field", llm_fallback=fake_llm)


def test_resolve_field_does_not_call_fallback_when_alias_already_matches():
    def failing_llm(label: str) -> str | None:
        raise AssertionError("fallback should not be called when an alias already matched")

    assert resolve_field("Postal Code", llm_fallback=failing_llm) == "address.postal_code"
