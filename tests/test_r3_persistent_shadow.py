from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

import scripts.run_r3_prospective_collector as runner
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
