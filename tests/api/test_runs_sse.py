"""GET /v1/runs/{run_id}/events (CONTRACTS §6.1)."""

from __future__ import annotations

import json

TERMINAL = {"done", "error"}


def _parse_sse(raw: str) -> list[dict]:
    frames = []
    for chunk in raw.strip("\n").split("\n\n"):
        if not chunk:
            continue
        frame: dict = {}
        for line in chunk.split("\n"):
            if line.startswith("retry:"):
                frame["retry"] = line.split(":", 1)[1].strip()
            elif line.startswith("id:"):
                frame["id"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("event:"):
                frame["event"] = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                frame["data"] = json.loads(line.split(":", 1)[1].strip())
            elif line.startswith(":"):
                frame["comment"] = line[1:].strip()
        frames.append(frame)
    return frames


async def _start_check(client) -> tuple[str, str]:
    resp = await client.post("/v1/checks", data={"text": "hello there friend", "lang": "en"})
    body = resp.json()
    return body["run_id"], body["events_url"]


async def test_sse_framing_retry_line_and_order(client):
    _run_id, events_url = await _start_check(client)
    async with client.stream("GET", events_url) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        raw = (await response.aread()).decode()

    frames = _parse_sse(raw)
    assert frames[0] == {"retry": "2000"}

    event_frames = [f for f in frames[1:] if "event" in f]
    assert event_frames, "expected at least one real event"
    types = [f["event"] for f in event_frames]
    assert types[-1] == "done"
    if "verdict" in types and "explanation" in types:
        assert types.index("verdict") < types.index("explanation")

    # every real event frame carries id/event/data, data is compact JSON
    for f in event_frames:
        assert isinstance(f["id"], int)
        assert isinstance(f["data"], dict)

    # ids are strictly increasing
    ids = [f["id"] for f in event_frames]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


async def test_sse_last_event_id_header_replays_only_later_events(client):
    _run_id, events_url = await _start_check(client)

    async with client.stream("GET", events_url) as response:
        raw = (await response.aread()).decode()
    all_frames = [f for f in _parse_sse(raw) if "event" in f]
    assert len(all_frames) >= 4, "need enough events for a meaningful midpoint"
    cutoff_id = all_frames[len(all_frames) // 2]["id"]

    async with client.stream("GET", events_url, headers={"Last-Event-ID": str(cutoff_id)}) as response:
        assert response.status_code == 200
        raw2 = (await response.aread()).decode()
    replayed = [f for f in _parse_sse(raw2) if "event" in f]

    assert replayed  # strictly fewer than all, and non-empty
    assert len(replayed) < len(all_frames)
    assert all(f["id"] > cutoff_id for f in replayed)
    assert replayed == [f for f in all_frames if f["id"] > cutoff_id]


async def test_sse_last_event_id_query_param_also_works(client):
    _run_id, events_url = await _start_check(client)
    async with client.stream("GET", events_url) as response:
        raw = (await response.aread()).decode()
    all_frames = [f for f in _parse_sse(raw) if "event" in f]
    cutoff = all_frames[0]["id"]

    async with client.stream("GET", f"{events_url}?last_event_id={cutoff}") as response:
        raw2 = (await response.aread()).decode()
    replayed = [f for f in _parse_sse(raw2) if "event" in f]
    assert all(f["id"] > cutoff for f in replayed)


async def test_sse_unknown_run_is_json_404(client):
    resp = await client.get("/v1/runs/no-such-run/events")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["error"]["code"] == "run_not_found"


async def test_sse_stream_closes_after_done(client):
    """aread() would hang forever if the generator did not return after `done`."""
    _run_id, events_url = await _start_check(client)
    async with client.stream("GET", events_url) as response:
        raw = (await response.aread()).decode()
    frames = [f for f in _parse_sse(raw) if "event" in f]
    assert frames[-1]["event"] == "done"


async def test_client_disconnect_mid_stream_does_not_break_the_server(client):
    _run_id, events_url = await _start_check(client)
    async with client.stream("GET", events_url) as response:
        async for _line in response.aiter_lines():
            break  # disconnect after the very first line (the retry: line)

    # the server must still be healthy afterwards
    resp = await client.get("/healthz")
    assert resp.status_code == 200
