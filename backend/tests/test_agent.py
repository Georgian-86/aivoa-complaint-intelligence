"""Graph-level behaviour: routing, state merge, and the safety floor."""

from app.agent.graph import GRAPH, PIPELINE_STEPS, run_intake


def test_graph_wiring_matches_declared_pipeline():
    nodes = set(GRAPH.get_graph().nodes) - {"__start__", "__end__"}
    assert nodes == {step["node"] for step in PIPELINE_STEPS}


def test_unusable_input_short_circuits_to_finalise():
    """A two-word note must not burn LLM calls on extraction."""
    state = run_intake(raw_text="thanks bye", channel="text")
    visited = [entry["node"] for entry in state["trace"]]
    assert visited == ["ingest", "finalise"]
    assert any("too short" in w for w in state["warnings"])


def test_full_pipeline_visits_every_node(particulate_email):
    state = run_intake(raw_text=particulate_email, channel="email")
    visited = {entry["node"] for entry in state["trace"]}
    assert visited == {step["node"] for step in PIPELINE_STEPS}
    assert all(entry["status"] == "ok" for entry in state["trace"])


def test_fan_out_branches_both_merge(particulate_email):
    """completeness and dedupe run in the same superstep; the `trace` reducer
    must keep both contributions."""
    state = run_intake(raw_text=particulate_email, channel="email")
    nodes = [entry["node"] for entry in state["trace"]]
    assert nodes.count("completeness") == 1
    assert nodes.count("dedupe") == 1
    assert nodes.index("classify") > max(nodes.index("completeness"), nodes.index("dedupe"))


def test_patient_harm_is_classified_critical(particulate_email):
    state = run_intake(raw_text=particulate_email, channel="email")
    assert state["risk"]["severity"] == "Critical"
    assert "recall_assessment" in state["risk"]["regulatory_flags"]
    assert state["form"]["priority"] == "P1 - Immediate"


def test_analyst_values_are_never_overwritten(particulate_email):
    state = run_intake(
        raw_text=particulate_email,
        channel="email",
        existing_form={"product_name": "Analyst typed this", "batch_number": "MANUAL-001"},
    )
    assert state["form"]["product_name"] == "Analyst typed this"
    assert state["form"]["batch_number"] == "MANUAL-001"
    assert state["fields"]["product_name"]["source"] == "analyst"


def test_due_date_follows_severity_tat(particulate_email):
    state = run_intake(raw_text=particulate_email, channel="email")
    assert state["risk"]["recommended_tat_days"] == 3  # Critical
    assert state["form"]["due_date"]


def test_every_node_reports_timing(particulate_email):
    state = run_intake(raw_text=particulate_email, channel="email")
    assert all("duration_ms" in entry for entry in state["trace"])
    assert state["duration_ms"] > 0
