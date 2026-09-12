import pytest

from swarmci.agents import translate
from swarmci.models import RunConfig, Target
from swarmci.store import Store


def test_atomic_claims_across_connections(tmp_path):
    a = Store(tmp_path / "db")
    b = Store(tmp_path / "db")
    target = Target(name="test", url="http://localhost")
    run = a.create_run(RunConfig(target=target, workers=1))
    assert a.enqueue(run, "same", {"path": []})
    assert not b.enqueue(run, "same", {"path": []})
    assert a.claim(run, "worker-a")
    assert b.claim(run, "worker-b") is None


def test_converging_paths_retain_every_attempt(tmp_path):
    s = Store(tmp_path / "db")
    run = s.create_run(RunConfig(target=Target(name="test", url="http://localhost"), workers=1))
    for id in ["a", "b"]:
        s.node(run, {"id": id, "screen_key": "screen", "depth": 1})
    s.edge(run, "a", "b", {"path": ["click", "undo"], "action": {"value": "one"}})
    s.edge(run, "a", "b", {"path": ["click", "back"], "action": {"value": "two"}})
    snap = s.snapshot(run)
    assert len(snap["nodes"]) == 2
    assert len(snap["edges"]) == 2
    assert snap["edges"][0]["payload"]["path"] != snap["edges"][1]["payload"]["path"]


def test_parallel_backend_isolation_required():
    with pytest.raises(ValueError, match="isolated"):
        RunConfig(target=Target(name="app", url="http://localhost"), workers=2)


def test_agent_actions_fail_closed():
    with pytest.raises(ValueError, match="adapter"):
        translate({"evaluate": {"code": "malicious()"}}, {})
    with pytest.raises(ValueError, match="selector"):
        translate({"click": {"index": 22}}, {})
    a = translate({"input": {"index": 3, "text": "test", "clear": False}}, {3: "#name"})
    assert a.kind == "fill" and not a.clear


def test_restart_marks_incomplete_runs(tmp_path):
    s = Store(tmp_path / "db")
    id = s.create_run(RunConfig(target=Target(name="test", url="http://localhost"), workers=1))
    s.enqueue(id, "one", {})
    s.claim(id, "worker")
    s.recover()
    assert s.snapshot(id)["status"] == "interrupted"
    assert s.snapshot(id)["jobs"] == {"interrupted": 1}


def test_dashboard_restart_does_not_interrupt_separate_live_runner(tmp_path):
    runner = Store(tmp_path / 'db')
    dashboard = Store(tmp_path / 'db')
    run = runner.create_run(RunConfig(target=Target(name='test', url='http://localhost'), workers=1))
    runner.status(run, 'running')
    runner.enqueue(run, 'branch', {'path': []})
    runner.claim(run, 'worker')
    dashboard.recover()
    assert runner.snapshot(run)['status'] == 'running'
    assert runner.snapshot(run)['jobs'] == {'running': 1}


def test_repeated_replay_failure_prunes_only_affected_paths(tmp_path):
    s = Store(tmp_path / 'db')
    run = s.create_run(RunConfig(target=Target(name='test', url='http://localhost'), workers=1))
    prefix = [{'kind': 'click', 'selector': '#missing'}]
    s.enqueue(run, 'bad', {'path': prefix + [{'kind': 'reload'}]})
    s.enqueue(run, 'good', {'path': [{'kind': 'click', 'selector': '#works'}]})
    s.replay_failure(run, prefix)
    assert s.snapshot(run)['jobs'] == {'queued': 2}
    s.replay_failure(run, prefix)
    assert s.snapshot(run)['jobs'] == {'queued': 1, 'skipped': 1}
    assert not s.enqueue(run, 'later-bad', {'path': prefix})
    assert s.claim(run, 'worker')['signature'] == 'good'
