"""研究在服务端独立运行：订阅的人走了它照样跑完，回来能接上，只有明确叫停才会取消。"""

import asyncio
import json

from fastapi.testclient import TestClient

from wealthpilot.main import app
from wealthpilot.services import local_run, runs


def _source(gate: asyncio.Event | None = None, log: list | None = None):
    async def gen():
        try:
            yield {"type": "plan", "tasks": []}
            if gate is not None:
                await gate.wait()
            yield {"type": "delta", "content": "结论"}
            yield {"type": "done", "content": "结论", "meta": {"status": "passed"}}
            if log is not None:
                log.append("finished")
        finally:
            if log is not None:
                log.append("closed")
    return gen()


async def test_a_subscriber_leaving_does_not_stop_the_research():
    gate, log = asyncio.Event(), []
    run = runs.start(1, "分析茅台", source=_source(gate, log))
    seen = []
    async for event in runs.subscribe(run):
        seen.append(event["type"])
        if event["type"] == "plan":
            break                                   # 页面关了：订阅结束
    assert seen == ["run", "plan"] and not run.done
    gate.set()
    await run.task
    assert run.done and log == ["finished", "closed"]              # 研究自己跑完了
    assert [e["type"] for e in run.events] == ["run", "plan", "delta", "done"]
    # 回来接上：可以从头重放，也可以从断点接着看
    assert [e["type"] async for e in runs.subscribe(run)] == ["run", "plan", "delta", "done"]
    assert [e["type"] async for e in runs.subscribe(run, 2)] == ["delta", "done"]


async def test_two_pages_can_watch_the_same_run_live():
    gate = asyncio.Event()
    run = runs.start(1, "q", source=_source(gate))

    async def watch():
        return [e["type"] async for e in runs.subscribe(run)]
    first, second = asyncio.create_task(watch()), asyncio.create_task(watch())
    await asyncio.sleep(0.01)
    gate.set()
    assert await first == await second == ["run", "plan", "delta", "done"]


async def test_only_an_explicit_stop_cancels():
    gate, log = asyncio.Event(), []
    run = runs.start(1, "q", source=_source(gate, log))
    await asyncio.sleep(0.01)
    assert [r["run_id"] for r in runs.active(1)][0] == run.id and runs.active(2) == []
    assert runs.get(run.id, 2) is None                              # 别人的研究拿不到
    runs.stop(run)
    await asyncio.gather(run.task, return_exceptions=True)
    assert run.done and run.events[-1]["meta"]["status"] == "stopped" and log == ["closed"]
    assert run.id not in [r["run_id"] for r in runs.active(1)]


async def test_a_crashing_run_ends_with_a_clear_failure():
    async def broken():
        yield {"type": "plan", "tasks": []}
        raise RuntimeError("boom")
    run = runs.start(1, "q", source=broken())
    await run.task
    assert [e["type"] for e in run.events][-2:] == ["error", "done"] and run.events[-1]["meta"]["status"] == "failed"


def test_finished_runs_are_swept_after_a_while(monkeypatch):
    async def main():
        run = runs.start(9, "q", source=_source())
        await run.task
        run.finished_at -= runs.KEEP_SECONDS + 1
        runs.start(9, "next", source=_source())
        return run.id
    old = asyncio.run(main())
    assert old not in runs._RUNS


def _events(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.split("\n\n") if line.startswith("data: ")]


def test_chat_route_starts_a_run_and_it_can_be_replayed(monkeypatch):
    seen = {}

    async def fake(message, history=None, conversation_id="", *, depth="auto", rewrite_of=None, user_id=None):
        seen.update(message=message, depth=depth, conversation_id=conversation_id)
        yield {"type": "plan", "tasks": []}
        yield {"type": "done", "content": "好", "meta": {"status": "passed"}}
    monkeypatch.setattr(local_run, "stream_local", fake)
    with TestClient(app) as client:
        events = _events(client.post("/api/chat", json={"message": "分析茅台", "depth": "quick", "conversation_id": "c-1"}))
        assert [e["type"] for e in events] == ["run", "plan", "done"] and seen == {"message": "分析茅台", "depth": "quick", "conversation_id": "c-1"}
        run_id = events[0]["run_id"]
        again = _events(client.get(f"/api/chat/runs/{run_id}/events"))
        assert [e["type"] for e in again] == ["run", "plan", "done"]
        assert [e["type"] for e in _events(client.get(f"/api/chat/runs/{run_id}/events?start=2"))] == ["done"]
        assert client.get("/api/chat/runs/active").json() == []     # 已经跑完，不在"进行中"里
        assert client.post(f"/api/chat/runs/{run_id}/stop").json() == {"ok": True}
        assert client.get("/api/chat/runs/nope/events").status_code == 404
