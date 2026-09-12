import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from swarmci import storage


def test_headroom_uses_the_fuller_filesystem(monkeypatch):
    monkeypatch.setattr(storage.shutil, "disk_usage", Mock(side_effect=[
        SimpleNamespace(free=4 * storage.GIB), SimpleNamespace(free=storage.GIB),
    ]))
    status = storage.storage_status()
    assert status["free_bytes"] == storage.GIB
    assert not status["accepting_runs"]


@pytest.mark.asyncio
async def test_low_storage_rejects_run_before_creation(monkeypatch):
    from swarmci import api
    from swarmci.models import RunConfig, Target

    monkeypatch.setattr(api, "storage_status", lambda: {"accepting_runs": False})
    start = Mock()
    monkeypatch.setattr(api.coordinator, "start", start)
    with pytest.raises(HTTPException) as error:
        await api.start(RunConfig(target=Target(name="test", url="http://localhost"), workers=1))
    assert error.value.status_code == 503
    start.assert_not_called()


@pytest.mark.asyncio
async def test_critical_storage_cancels_work_once_and_preserves_server(monkeypatch):
    task = asyncio.create_task(asyncio.sleep(60))
    narration_task = asyncio.create_task(asyncio.sleep(60))
    coordinator = SimpleNamespace(tasks={"run": task}, store=SimpleNamespace(event=Mock()))
    narration = SimpleNamespace(tasks={"story": narration_task})
    monkeypatch.setattr(storage, "storage_status", lambda: {"free_bytes": 512 * 1024**2})
    storage.cancel_if_critical(coordinator, narration)
    storage.cancel_if_critical(coordinator, narration)
    await asyncio.gather(task, narration_task, return_exceptions=True)
    assert task.cancelled() and narration_task.cancelled()
    coordinator.store.event.assert_called_once()


@pytest.mark.asyncio
async def test_healthy_storage_keeps_work_running(monkeypatch):
    task = asyncio.create_task(asyncio.sleep(60))
    coordinator = SimpleNamespace(tasks={"run": task})
    monkeypatch.setattr(storage, "storage_status", lambda: {"free_bytes": 4 * storage.GIB})
    storage.cancel_if_critical(coordinator, SimpleNamespace(tasks={}))
    assert not task.cancelling()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def test_monitor_releases_reserve_but_keeps_evidence(tmp_path, monkeypatch):
    from scripts import storage_monitor as monitor

    reserve = tmp_path / "disk-reserve"
    reserve.write_bytes(b"reserve")
    evidence = tmp_path / "evidence.webm"
    evidence.write_bytes(b"preserve")
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _: SimpleNamespace(free=2 * storage.GIB))
    monitor.maintain(tmp_path, reserve)
    assert not reserve.exists()
    assert evidence.read_bytes() == b"preserve"


def test_monitor_does_not_allocate_reserve_under_pressure(tmp_path, monkeypatch):
    from scripts import storage_monitor as monitor

    reserve = tmp_path / "disk-reserve"
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _: SimpleNamespace(free=3 * storage.GIB))
    monitor.maintain(tmp_path, reserve)
    assert not reserve.exists()


def test_monitor_allocates_real_blocks_with_sufficient_headroom(tmp_path, monkeypatch):
    from scripts import storage_monitor as monitor

    reserve = tmp_path / "disk-reserve"
    allocate = Mock()
    monkeypatch.setattr(monitor.os, "posix_fallocate", allocate, raising=False)
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _: SimpleNamespace(free=5 * storage.GIB))
    monitor.maintain(tmp_path, reserve)
    assert reserve.exists()
    assert allocate.call_args.args[1:] == (0, monitor.RESERVE_BYTES)
