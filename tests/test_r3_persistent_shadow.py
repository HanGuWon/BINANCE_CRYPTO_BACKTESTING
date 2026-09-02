from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

import scripts.run_r3_prospective_collector as runner
from binance_research.r3_operations import append_manifest, build_manifest, verify_engineering_shadow_root
from binance_research.r3_timing import calibrate_server_clock


def test_engineering_shadow_persistent_spans_four_absolute_cycles(tmp_path: Path, monkeypatch) -> None:
    calibration = calibrate_server_clock(local_before_ms=0, server_ms=0, local_after_ms=0)
    calls = []

    class FakeClient:
        def calibrate_server_clock(self, market: str):
            assert market == "um"
            return calibration

    class FakeCollector:
        def __init__(self, store):
            self.client = FakeClient()
            self.clock_calibration = None

        async def stream_liquidations(self, symbol, *, evidence_mode):
            assert symbol == "ALL" and evidence_mode == "ENGINEERING_SHADOW"
            try:
                while True:
                    import asyncio
                    await asyncio.sleep(0.001)
                    yield {}
            finally:
                return

    def fake_cycle(root, symbols, roster_sha256, **kwargs):
        calls.append(kwargs["boundary"])
        return {"manifest_sha256": f"m{len(calls)}"}

    monkeypatch.setattr(runner, "validate_engineering_shadow_inputs", lambda *args, **kwargs: (["AAAUSDT"], "a" * 64))
    monkeypatch.setattr(runner, "ForwardCollector", FakeCollector)
    monkeypatch.setattr(runner, "_run_cycle", fake_cycle)
    monkeypatch.setattr(runner, "single_instance_lock", lambda _: nullcontext())
    result = runner.run_engineering_shadow_forever(tmp_path, Path("roster.json"), max_cycles=4, wait_for_boundary=False)
    assert result["cycles"] == 4
    assert len(calls) == 4
    assert all((calls[index + 1] - calls[index]).total_seconds() == 900 for index in range(3))
    assert (tmp_path / "health" / "shutdown_receipt.json").is_file()


def test_engineering_shadow_waits_for_real_boundary_without_injection(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    calibration = calibrate_server_clock(local_before_ms=0, server_ms=0, local_after_ms=0)
    calls = []
    sleeps = []
    original_sleep = asyncio.sleep

    class FakeClient:
        def calibrate_server_clock(self, market: str):
            return calibration

    class FakeCollector:
        def __init__(self, store):
            self.client = FakeClient()
            self.clock_calibration = None

        async def stream_liquidations(self, symbol, *, evidence_mode):
            try:
                while True:
                    import asyncio
                    await asyncio.sleep(0.001)
                    yield {}
            finally:
                return

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        await original_sleep(0)

    def fake_cycle(root, symbols, roster_sha256, **kwargs):
        calls.append(kwargs["boundary"])
        return {"manifest_sha256": f"m{len(calls)}"}

    monkeypatch.setattr(runner, "validate_engineering_shadow_inputs", lambda *args, **kwargs: (["AAAUSDT"], "a" * 64))
    monkeypatch.setattr(runner, "ForwardCollector", FakeCollector)
    monkeypatch.setattr(runner, "_run_cycle", fake_cycle)
    monkeypatch.setattr(runner, "single_instance_lock", lambda _: nullcontext())
    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)
    result = runner.run_engineering_shadow_forever(tmp_path, Path("roster.json"), max_cycles=2, wait_for_boundary=True)
    assert result["cycles"] == 2
    assert len(calls) == 2
    assert all((calls[index + 1] - calls[index]).total_seconds() == 900 for index in range(len(calls) - 1))
    assert sleeps and all(delay >= 0 for delay in sleeps)


def test_shadow_reconciles_files_appended_by_stream_before_verification(tmp_path: Path) -> None:
    raw = tmp_path / "raw_v1" / "um" / "AAAUSDT"
    raw.mkdir(parents=True)
    for stream in ("premium", "book_ticker", "open_interest"):
        (raw / f"{stream}.jsonl").write_text(
            '{"symbol":"AAAUSDT","stream":"' + stream + '","evidence_mode":"ENGINEERING_SHADOW"}\n',
            encoding="utf-8",
        )
    for stream in ("klines_15m", "premium_klines_15m"):
        (raw / f"{stream}.jsonl").write_text(
            '{"symbol":"AAAUSDT","stream":"' + stream + '","evidence_mode":"ENGINEERING_SHADOW","payload":{"source_open_time":"2026-08-30T00:00:00+00:00","source_available_time":"2026-08-30T00:15:00+00:00"}}\n',
            encoding="utf-8",
        )
    stale = build_manifest(tmp_path / "raw_v1", manifest_id="before-stream")
    append_manifest(tmp_path / "raw_v1", stale)
    (raw / "liquidation.jsonl").write_text(
        '{"symbol":"AAAUSDT","stream":"liquidation","evidence_mode":"ENGINEERING_SHADOW"}\n',
        encoding="utf-8",
    )
    runner._reconcile_manifest_after_stream_stop(tmp_path, roster_sha256="a" * 64, evidence_mode="ENGINEERING_SHADOW", cycles=1)
    verified = verify_engineering_shadow_root(tmp_path, expected_symbols=["AAAUSDT"], roster_sha256="a" * 64)
    assert verified["files"] == 6
    assert verified["rows"] == 6
