from types import SimpleNamespace

import pytest

from swarmci.models import RunConfig, Target
from swarmci.narration import (
    Explanation,
    GroundedText,
    GroundingReview,
    NarrationProgram,
    NarrationService,
    evidence_packets,
    examples,
    validate_explanations,
)
from swarmci.presentation import enrich_snapshot
from swarmci.store import Store


def sample_store(tmp_path):
    store = Store(tmp_path / "graph.db")
    run = store.create_run(RunConfig(target=Target(name="test", url="http://localhost/app"), workers=1))
    for id, history in [("a", "path-one"), ("b", "path-two")]:
        store.node(
            run,
            {
                "id": id,
                "screen_key": "same-screen",
                "depth": 1,
                "url": "http://localhost/app",
                "title": "Tasks",
                "label": "Tasks",
                "controls": [],
                "fingerprint_parts": {"history": history, "controls": "same"},
            },
        )
    store.edge(
        run,
        "a",
        "b",
        {"worker": "worker-1", "path": [{"kind": "click", "label": "Open"}], "action": {"label": "Open"}},
    )
    store.edge(
        run,
        "a",
        "b",
        {"worker": "worker-2", "path": [{"kind": "click", "label": "Open"}], "action": {"label": "Open"}},
    )
    store.edge(
        run,
        "a",
        "b",
        {"worker": "worker-2", "path": [{"kind": "click", "label": "Back"}], "action": {"label": "Back"}},
    )
    return store, run


def test_page_grouping_preserves_state_keys_and_arrival_paths(tmp_path):
    store, run = sample_store(tmp_path)
    before = store.snapshot(run)
    after = enrich_snapshot(before)
    assert {n["id"] for n in after["nodes"]} == {"a", "b"}
    assert len(after["page_groups"]) == 1
    b = next(n for n in after["nodes"] if n["id"] == "b")
    assert (b["page_variants"], b["same_screen_variants"]) == (2, 2)
    assert (b["arrival_count"], b["arrival_paths"], b["arrival_workers"]) == (3, 2, 2)
    assert "action history" in b["variant_note"]
    assert "page_key" not in before["nodes"][0]
    assert len(store.snapshot(run)["edges"]) == 3


def test_evidence_is_prefix_scoped_and_does_not_reveal_later_bugs(tmp_path):
    store, run = sample_store(tmp_path)
    store.bug(run, "later", {"state": "b", "title": "A later verified finding"})
    packets = evidence_packets(store, run)
    assert [p.kind for p in packets] == ["variant", "convergence", "convergence"]
    assert "Arrival 1" in packets[0].facts[2].text
    assert "Arrival 3" in packets[2].facts[2].text
    assert "A later verified finding" not in str([p.model_dump() for p in packets])
    assert all(
        "outside this action packet" in next(f.text for f in p.facts if f.id == "verification")
        for p in packets
    )


def test_output_rejects_unknown_citations_and_wrong_edge():
    demo = examples()[0]
    valid = demo.explanations[0]
    assert validate_explanations(demo.evidence, [valid]) == [valid]
    bad = valid.model_copy(update={"edge_id": "wrong"})
    with pytest.raises(ValueError, match="IDs"):
        validate_explanations(demo.evidence, [bad])
    bad = valid.model_copy(
        update={"happened": GroundedText(text="Unsupported claim", evidence_ids=["invented-fact"])}
    )
    with pytest.raises(ValueError, match="unknown fact"):
        validate_explanations(demo.evidence, [bad])


def test_grounding_review_can_block_schema_valid_hallucinations(monkeypatch):
    demo = examples()[0]
    wrong = demo.explanations[0].model_copy(update={"headline": "This saved eighty actions"})
    program = NarrationProgram()

    class Writer:
        demos = []

        def __call__(self, **kwargs):
            return SimpleNamespace(explanations=[wrong])

    program.writer = Writer()
    program.reviewer = lambda **kwargs: SimpleNamespace(
        reviews=[GroundingReview(edge_id=wrong.edge_id, supported=False, issue="Saved work is not measured")]
    )
    monkeypatch.setattr("swarmci.narration.dspy.Predict", lambda *args, **kwargs: Writer())
    with pytest.raises(ValueError, match="evidence review"):
        program.forward(evidence=demo.evidence)


@pytest.mark.asyncio
async def test_successful_narration_is_persisted_and_not_regenerated(tmp_path, monkeypatch):
    store, run = sample_store(tmp_path)
    service = NarrationService(store)
    calls = []

    def predict(run, packets):
        calls.append(run)
        return [
            Explanation(
                edge_id=p.edge_id,
                headline="Another arrival",
                happened=GroundedText(
                    text="A recorded action reached this state.", evidence_ids=["action", "state"]
                ),
                significance=GroundedText(text="The arrival path is preserved.", evidence_ids=["resolution"]),
            )
            for p in packets
        ]

    monkeypatch.setattr(service, "predict", predict)
    await service.generate(run)
    await service.generate(run)
    assert len(calls) == 1
    assert len(service.get(run)["messages"]) == 3
    assert service.get(run)["error"] is None
