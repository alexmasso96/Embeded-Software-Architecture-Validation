"""
Structural no-freeze probe (plan §8).

Drives several CPU-bound jobs inside the WORKER process while this process — the
stand-in for the UI/pywebview process — measures its own loop latency. Because
the worker is a separate OS process, its GIL contention cannot stall us: the
sleep-tick latency must stay under THRESHOLD_MS. This is the structural
guarantee that the Qt single-process design could not give. Run it on an
EDR-protected machine before cutover, where per-syscall scanning makes any
accidental shared-process work visible.

    python scripts/freeze_probe.py            # ~5s, exits 0 (PASS) / 1 (FAIL)
    python scripts/freeze_probe.py --seconds 10 --burn 8 --threshold 50
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))          # for `desktop` / `backend`
sys.path.insert(0, str(_REPO / "src"))  # for `Application_Logic`

from desktop.worker import spawn_worker, wait_until_ready  # noqa: E402

TOKEN = "freeze-probe-token"
TICK = 0.01  # intended sleep per sample (10 ms)


def _post(port: int, path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method="POST"
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 (localhost)
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=5.0, help="measurement window")
    ap.add_argument("--burn", type=float, default=6.0, help="CPU burn per worker job")
    ap.add_argument("--jobs", type=int, default=4, help="concurrent worker jobs")
    ap.add_argument("--threshold", type=float, default=50.0, help="max tick latency, ms")
    args = ap.parse_args()

    proc, port, lifeline = spawn_worker(TOKEN)
    try:
        if not wait_until_ready(port):
            print("Worker failed to become ready.", file=sys.stderr)
            return 2

        for _ in range(args.jobs):
            _post(port, "/api/jobs/_demo", {"steps": 1, "burn": args.burn})

        latencies: list[float] = []
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            t0 = time.monotonic()
            time.sleep(TICK)
            latencies.append((time.monotonic() - t0 - TICK) * 1000.0)

        latencies = [max(0.0, x) for x in latencies]
        p50 = statistics.median(latencies)
        p95 = statistics.quantiles(latencies, n=20)[-1] if len(latencies) >= 20 else max(latencies)
        worst = max(latencies)
        print(
            f"worker_jobs={args.jobs} burn={args.burn}s samples={len(latencies)} "
            f"p50={p50:.1f}ms p95={p95:.1f}ms worst={worst:.1f}ms "
            f"threshold={args.threshold:.0f}ms"
        )
        ok = worst < args.threshold
        print("PASS — UI loop stayed responsive under worker load" if ok
              else "FAIL — UI loop stalled; heavy work is leaking into this process")
        return 0 if ok else 1
    finally:
        lifeline.close()
        proc.join(timeout=8)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=3)
        if proc.is_alive():
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
