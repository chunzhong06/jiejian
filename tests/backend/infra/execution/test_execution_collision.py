# 验证进程运行时中的并发碰撞实验。

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

from product.backend.core.lifecycle import RunVerdict
from product.backend.core.verification.collision import (
    CollisionAnomaly,
    CollisionBudget,
    CollisionObservation,
)
from product.backend.infra.execution.collision import CollisionExperiment


def test_barrier_repeats_same_baseline_and_always_cleans_up() -> None:
    entered = 0
    entered_lock = threading.Lock()
    both_entered = threading.Event()
    cleanup_called = False

    def request(_timeout: float) -> str:
        nonlocal entered
        with entered_lock:
            entered += 1
            if entered % 2 == 0:
                both_entered.set()
        assert both_entered.wait(timeout=0.5)
        return "accepted"

    def cleanup() -> None:
        nonlocal cleanup_called
        cleanup_called = True

    result = CollisionExperiment(
        CollisionBudget(
            max_requests=4,
            repetitions=2,
            request_timeout_ms=500,
            experiment_timeout_ms=2_000,
            synchronization_timeout_ms=200,
        )
    ).run(
        sequential_probe=lambda: True,
        restore_baseline=lambda: "same-baseline",
        requests_for_repetition=lambda _repetition: (request, request),
        observe=lambda *_args: CollisionObservation(
            anomalies=(CollisionAnomaly.DUPLICATE_EFFECT,),
            invariants_complete=True,
        ),
        cleanup=cleanup,
    )

    assert result.verdict is RunVerdict.BLOCK
    assert len(result.trials) == 2
    assert {trial.baseline_fingerprint for trial in result.trials} == {"same-baseline"}
    assert cleanup_called is True


class _QuotaRaceHandler(BaseHTTPRequestHandler):
    server: "_QuotaRaceServer"

    def do_POST(self) -> None:  # noqa: N802 - 标准库 HTTP 回调
        if self.path != "/claim":
            self.send_error(404)
            return
        allowed = self.server.claimed < 1
        time.sleep(0.03)
        if allowed:
            self.server.claimed += 1
        payload = json.dumps({"accepted": allowed}).encode("utf-8")
        self.send_response(200 if allowed else 409)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args: object) -> None:
        return


class _QuotaRaceServer(ThreadingHTTPServer):
    claimed: int


def test_real_loopback_race_reproduces_quota_bypass() -> None:
    """L5：真实回环 HTTP 碰撞必须复现业务额度突破，而非只比较响应时序。"""

    server = _QuotaRaceServer(("127.0.0.1", 0), _QuotaRaceHandler)
    server.claimed = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/claim"

    def claim(timeout: float) -> int:
        request = Request(url, method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status
        except Exception as exc:  # urllib 对 409 使用异常路径，状态仍是受控测试事实
            return int(getattr(exc, "code", 0))

    def reset() -> str:
        server.claimed = 0
        return "quota=0;limit=1"

    def sequential_probe() -> bool:
        reset()
        return claim(0.5) == 200 and claim(0.5) == 409 and server.claimed == 1

    try:
        result = CollisionExperiment(
            CollisionBudget(
                max_requests=4,
                repetitions=2,
                request_timeout_ms=1_000,
                experiment_timeout_ms=5_000,
                synchronization_timeout_ms=500,
            )
        ).run(
            sequential_probe=sequential_probe,
            restore_baseline=reset,
            requests_for_repetition=lambda _repetition: (claim, claim),
            observe=lambda *_args: CollisionObservation(
                anomalies=(CollisionAnomaly.QUOTA_BYPASS,) if server.claimed > 1 else (),
                invariants_complete=True,
            ),
            cleanup=lambda: None,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)

    assert result.verdict is RunVerdict.BLOCK
    assert result.repeatable_anomalies == (CollisionAnomaly.QUOTA_BYPASS,)
