from quote_agent.io import DATA_DIR, load_intake, load_registry, load_results
from quote_agent.models import IntakeProfile


def test_intake_example_matches_schema():
    profile = load_intake(DATA_DIR / "intake.example.json")
    assert isinstance(profile, IntakeProfile)
    assert profile.identity.licence_province == "ON"
    assert profile.coverage_benchmark.third_party_liability_limit == 2_000_000


def test_registry_and_results_start_empty():
    assert load_registry() == []
    assert load_results() == []
