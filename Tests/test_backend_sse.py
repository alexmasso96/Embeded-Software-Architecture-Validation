"""
Phase 1 — SSE event stream over a real uvicorn server.

The sync FastAPI TestClient can't drive a streaming SSE endpoint cleanly, so
this test boots an actual uvicorn server on an OS-assigned port and reads the
stream with an async httpx client — the same transport the frontend's
EventSource uses. Asserts that a fired job's progress reaches the stream and
that the ?token= query-param auth path works for EventSource.
"""
import asyncio
import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.abspath("src"))

import httpx
import uvicorn

from backend.app import create_app

TOKEN = "sse-token"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def server():
    port = _free_port()
    app = create_app(token=TOKEN)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    # Wait for startup.
    deadline = time.time() + 5
    while not srv.started and time.time() < deadline:
        time.sleep(0.02)
    assert srv.started, "uvicorn did not start"
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=5)


def test_sse_delivers_job_events(server):
    async def run():
        base = server
        async with httpx.AsyncClient(timeout=10.0) as client:
            seen = []
            # EventSource can't send headers → token via query param.
            async with client.stream("GET", f"{base}/api/events?token={TOKEN}") as resp:
                assert resp.status_code == 200

                async def fire():
                    await asyncio.sleep(0.2)
                    await client.post(f"{base}/api/jobs/_demo", json={"steps": 2},
                                      headers={"Authorization": f"Bearer {TOKEN}"})

                task = asyncio.create_task(fire())
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        seen.append(line.split(":", 1)[1].strip())
                    # Job emits queued→running→progress×2→done = several 'job' events.
                    if seen.count("job") >= 3:
                        break
                await task
            return seen

        return seen

    seen = asyncio.run(run())
    assert "ready" in seen
    assert seen.count("job") >= 3


def test_sse_rejects_bad_token(server):
    async def run():
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{server}/api/events?token=wrong")
            return r.status_code

    assert asyncio.run(run()) == 401
