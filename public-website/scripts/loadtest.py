#!/usr/bin/env python3
"""
public-website/scripts/loadtest.py
───────────────────────────────────
Load generator for the deployed public website.

WHAT IT MEASURES
Per concurrency level: achieved RPS, success / error / timeout counts broken
down by status, latency p50/p95/p99 (and min/max), bytes transferred, and for
download runs whether each transfer actually completed and matched the
published SHA-256.

WHAT IT DELIBERATELY DOES NOT DO
It does not fabricate a number it did not observe. A run that is cut short by a
rate limit reports the 429s as 429s; those are the system working, not a
failure to be tuned away, and hiding them would make the capacity figure a lie.

SAFETY
  * Point it only at a deployment you own. There is no default target.
  * `--max-total-bytes` caps a download run. 10,000 × 19.5 MB is 195 GB; the
    cap exists so an accidental zero is not a bandwidth bill.
  * Read paths are safe to hammer. Auth paths create rows, so they use accounts
    you pass in explicitly rather than registering thousands of users.

USAGE
  python loadtest.py --base-url https://api.example.com --scenario health \
      --levels 100,500,1000 --requests-per-level 2000

  python loadtest.py --base-url https://api.example.com --scenario download \
      --token-file tokens.txt --release-id <uuid> --levels 5,20 \
      --expect-sha256 <hex> --max-total-bytes 2000000000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:  # pragma: no cover - operator-facing message
    sys.exit("httpx is required:  pip install httpx")


# ── Result accounting ─────────────────────────────────────────────────────────


@dataclass
class Outcome:
    latency_ms: float
    status: Optional[int]
    bytes_read: int = 0
    error: Optional[str] = None
    complete: bool = True


@dataclass
class LevelReport:
    scenario: str
    concurrency: int
    requested: int
    wall_seconds: float
    outcomes: list[Outcome] = field(default_factory=list)

    def summary(self) -> dict:
        latencies = sorted(o.latency_ms for o in self.outcomes if o.status is not None)
        by_status: dict[str, int] = {}
        for outcome in self.outcomes:
            key = str(outcome.status) if outcome.status is not None else (outcome.error or "error")
            by_status[key] = by_status.get(key, 0) + 1

        ok = sum(1 for o in self.outcomes if o.status is not None and 200 <= o.status < 300)
        timeouts = sum(1 for o in self.outcomes if o.error == "timeout")
        total_bytes = sum(o.bytes_read for o in self.outcomes)
        incomplete = sum(1 for o in self.outcomes if not o.complete)

        def pct(p: float) -> Optional[float]:
            if not latencies:
                return None
            index = min(int(round(p / 100 * len(latencies) + 0.5)) - 1, len(latencies) - 1)
            return round(latencies[max(index, 0)], 1)

        completed = len(self.outcomes)
        return {
            "scenario": self.scenario,
            "concurrency": self.concurrency,
            "requests": completed,
            "wall_seconds": round(self.wall_seconds, 2),
            "rps": round(completed / self.wall_seconds, 1) if self.wall_seconds else None,
            "success": ok,
            "success_rate_pct": round(100 * ok / completed, 2) if completed else None,
            "timeouts": timeouts,
            "incomplete_transfers": incomplete,
            "by_status": dict(sorted(by_status.items())),
            "latency_ms": {
                "p50": pct(50),
                "p95": pct(95),
                "p99": pct(99),
                "min": round(min(latencies), 1) if latencies else None,
                "max": round(max(latencies), 1) if latencies else None,
                "mean": round(statistics.fmean(latencies), 1) if latencies else None,
            },
            "bytes": total_bytes,
            "throughput_mib_s": (
                round(total_bytes / 1_048_576 / self.wall_seconds, 2)
                if self.wall_seconds and total_bytes
                else None
            ),
        }


# ── Request drivers ───────────────────────────────────────────────────────────


async def _timed_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    headers: Optional[dict] = None,
    timeout: float,
) -> Outcome:
    started = time.perf_counter()
    try:
        response = await client.get(path, headers=headers, timeout=timeout)
        body = response.content
        return Outcome(
            latency_ms=(time.perf_counter() - started) * 1000,
            status=response.status_code,
            bytes_read=len(body),
        )
    except httpx.TimeoutException:
        return Outcome((time.perf_counter() - started) * 1000, None, error="timeout")
    except Exception as exc:  # noqa: BLE001 — the failure mode is the data
        return Outcome(
            (time.perf_counter() - started) * 1000, None, error=type(exc).__name__
        )


async def _timed_download(
    client: httpx.AsyncClient,
    path: str,
    *,
    headers: dict,
    timeout: float,
    expect_sha256: Optional[str],
) -> Outcome:
    """
    Stream an artefact and verify it arrived whole.

    A load test of a download that discards the body measures the server's
    willingness to start sending, not its ability to finish. Completion and
    integrity are the properties that matter for a distributed binary, so both
    are checked here.
    """
    import hashlib

    started = time.perf_counter()
    digest = hashlib.sha256()
    read = 0
    try:
        async with client.stream(
            "GET", path, headers=headers, timeout=timeout
        ) as response:
            expected_length = int(response.headers.get("Content-Length") or 0)
            async for chunk in response.aiter_bytes(65_536):
                read += len(chunk)
                digest.update(chunk)

            elapsed = (time.perf_counter() - started) * 1000
            complete = expected_length == 0 or read == expected_length
            if response.status_code == 200 and expect_sha256:
                complete = complete and digest.hexdigest() == expect_sha256.lower()
            return Outcome(elapsed, response.status_code, read, complete=complete)
    except httpx.TimeoutException:
        return Outcome((time.perf_counter() - started) * 1000, None, read, "timeout", False)
    except Exception as exc:  # noqa: BLE001
        return Outcome(
            (time.perf_counter() - started) * 1000, None, read, type(exc).__name__, False
        )


# ── Scenarios ─────────────────────────────────────────────────────────────────

READ_SCENARIOS = {
    "health": "/health/live",
    "ready": "/health/ready",
    "releases": "/api/v1/releases",
    "latest": "/api/v1/releases/latest",
}


async def run_level(args, concurrency: int, tokens: list[str]) -> LevelReport:
    total = args.requests_per_level
    report = LevelReport(args.scenario, concurrency, total, 0.0)
    gate = asyncio.Semaphore(concurrency)
    budget = {"bytes": args.max_total_bytes}
    budget_lock = asyncio.Lock()

    limits = httpx.Limits(
        max_connections=concurrency + 10, max_keepalive_connections=concurrency
    )

    async with httpx.AsyncClient(
        base_url=args.base_url, limits=limits, follow_redirects=False
    ) as client:

        async def one(index: int) -> Optional[Outcome]:
            async with gate:
                if args.scenario == "download":
                    async with budget_lock:
                        if budget["bytes"] <= 0:
                            return None
                        budget["bytes"] -= args.artefact_bytes
                    token = tokens[index % len(tokens)]
                    return await _timed_download(
                        client,
                        f"/api/v1/downloads/{args.release_id}/file",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=args.timeout,
                        expect_sha256=args.expect_sha256,
                    )

                headers = None
                if tokens:
                    headers = {"Authorization": f"Bearer {tokens[index % len(tokens)]}"}
                return await _timed_get(
                    client,
                    READ_SCENARIOS[args.scenario],
                    headers=headers,
                    timeout=args.timeout,
                )

        started = time.perf_counter()
        results = await asyncio.gather(*(one(i) for i in range(total)))
        report.wall_seconds = time.perf_counter() - started

    report.outcomes = [r for r in results if r is not None]
    return report


async def main_async(args) -> int:
    tokens: list[str] = []
    if args.token_file:
        tokens = [
            line.strip()
            for line in Path(args.token_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not tokens:
            sys.exit(f"No tokens found in {args.token_file}")

    if args.scenario == "download":
        if not tokens or not args.release_id:
            sys.exit("--scenario download requires --token-file and --release-id")

    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    run = {
        "target": args.base_url,
        "scenario": args.scenario,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "levels": [],
    }

    for concurrency in levels:
        print(f"\n── concurrency {concurrency} ──", flush=True)
        report = await run_level(args, concurrency, tokens)
        summary = report.summary()
        run["levels"].append(summary)
        print(json.dumps(summary, indent=2), flush=True)

        if args.settle > 0 and concurrency != levels[-1]:
            print(f"settling for {args.settle}s", flush=True)
            await asyncio.sleep(args.settle)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(run, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")

    return 0


def parse_args(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="API origin, e.g. https://api.example.com")
    parser.add_argument(
        "--scenario",
        required=True,
        choices=[*READ_SCENARIOS.keys(), "download"],
    )
    parser.add_argument("--levels", default="100,500,1000")
    parser.add_argument("--requests-per-level", type=int, default=2000)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--settle", type=float, default=20.0, help="seconds between levels")
    parser.add_argument("--token-file", help="one bearer token per line")
    parser.add_argument("--release-id")
    parser.add_argument("--expect-sha256", help="published checksum, verified per transfer")
    parser.add_argument("--artefact-bytes", type=int, default=19_579_732)
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=5_000_000_000,
        help="hard cap on bytes pulled during a download run",
    )
    parser.add_argument("--out", help="write the full run as JSON here")
    return parser.parse_args(argv)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    raise SystemExit(asyncio.run(main_async(parse_args())))
