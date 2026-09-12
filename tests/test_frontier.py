from swarmci.frontier import control_key, exploration_frontier
from swarmci.models import Action, RunConfig, Target
from swarmci.runner import Coordinator
from swarmci.store import Store


def state(depth=1):
    return {
        "id": "state",
        "screen_key": "screen",
        "depth": depth,
        "controls": [
            {"tag": "button", "label": "Status"},
            {"tag": "a", "label": "Pages", "href": "/pages"},
            {"tag": "input", "label": "Password", "type": "password"},
            {"tag": "a", "label": "Outside", "href": "https://elsewhere.test"},
            {"tag": "button", "label": "Disabled", "disabled": True},
        ],
    }


def test_frontier_changes_focus_after_reservation():
    target = Target(name="App", url="http://localhost")
    observation = state()
    first = exploration_frontier(observation, target, {}, count=1)[0]
    second = exploration_frontier(observation, target, {first["control_key"]: 1}, count=1)[0]
    assert first["control_key"] != second["control_key"]
    assert {c["control_key"] for c in exploration_frontier(observation, target, {})} == {
        control_key(observation["controls"][0]),
        control_key(observation["controls"][1]),
    }


async def test_deep_discovery_competes_with_full_shallow_queue(tmp_path):
    store = Store(tmp_path / "graph.db")
    config = RunConfig(target=Target(name="App", url="http://localhost"), workers=1, max_jobs=3)
    run = store.create_run(config)
    for i in range(3):
        store.enqueue(run, f"shallow-{i}", {"path": [], "priority": 1})
    await Coordinator(store).branch(run, config, state(5), [Action(kind="reload")] * 5, "worker-a")
    job = store.claim(run, "worker-b")
    assert len(job["payload"]["path"]) == 5
    assert job["payload"]["owner"] == "worker-a"
    assert store.exploration_attempts(run, "screen")
    assert store.attempted_job_count(run) == 1
    assert store.job_count(run) > config.max_jobs
