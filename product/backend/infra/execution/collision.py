# =============================================================================
# 独立并发碰撞实验同步器
#
# 定位
#   在隔离 Runner 内为明确配置的 TOCTOU 实验提供 barrier 同步和有界重复。
#
# 职责
#   验证顺序语义｜逐轮恢复基线｜同步请求组｜收集 Observer 业务不变量
#
# 边界
#   普通权限 Case 仍串行；请求回调必须遵守传入超时，清理回调始终执行。
# =============================================================================

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from product.backend.core.verification.collision import (
    CollisionBudget,
    CollisionClue,
    CollisionExperimentResult,
    CollisionObservation,
    CollisionTrial,
    classify_collision_trials,
)


@dataclass(frozen=True, slots=True)
class CollisionResponse:
    request_index: int
    value: Any | None
    error_code: str | None
    started_ns: int
    finished_ns: int


CollisionRequest = Callable[[float], Any]


class CollisionExperiment:
    """执行一次独立碰撞实验；目标请求与 Observer 均由隔离执行边界注入。"""

    def __init__(self, budget: CollisionBudget) -> None:
        self._budget = budget

    def run(
        self,
        *,
        sequential_probe: Callable[[], bool],
        restore_baseline: Callable[[], str],
        requests_for_repetition: Callable[[int], Sequence[CollisionRequest]],
        observe: Callable[[int, str, tuple[CollisionResponse, ...]], CollisionObservation],
        cleanup: Callable[[], None],
    ) -> CollisionExperimentResult:
        deadline = time.monotonic() + self._budget.experiment_timeout_ms / 1000
        trials: list[CollisionTrial] = []
        request_count = 0
        try:
            sequential_valid = bool(sequential_probe())
            if not sequential_valid:
                return classify_collision_trials(
                    sequential_semantics_valid=False,
                    expected_repetitions=self._budget.repetitions,
                    trials=(),
                )
            for repetition in range(1, self._budget.repetitions + 1):
                if time.monotonic() >= deadline:
                    break
                baseline = restore_baseline()
                requests = tuple(requests_for_repetition(repetition))
                if not 2 <= len(requests) <= 64:
                    raise ValueError("collision request group must contain between 2 and 64 requests")
                if request_count + len(requests) > self._budget.max_requests:
                    raise ValueError("collision request budget exceeded")
                request_count += len(requests)
                responses = self._run_group(requests, deadline)
                complete = len(responses) == len(requests) and all(item.error_code is None for item in responses)
                if complete:
                    observation = observe(repetition, baseline, responses)
                else:
                    observation = CollisionObservation(
                        invariants_complete=False,
                        clues=(CollisionClue.REQUEST_FAILURE, CollisionClue.OBSERVER_INCOMPLETE),
                        reason_codes=("COLLISION_REQUEST_INCOMPLETE",),
                    )
                trials.append(
                    CollisionTrial(
                        repetition=repetition,
                        baseline_fingerprint=baseline,
                        request_count=len(requests),
                        responses_complete=complete,
                        observation=observation,
                    )
                )
                # 超时请求可能仍在隔离进程中收敛；不得在未知状态上继续下一轮。
                if not complete:
                    break
            return classify_collision_trials(
                sequential_semantics_valid=True,
                expected_repetitions=self._budget.repetitions,
                trials=tuple(trials),
            )
        finally:
            cleanup()

    def _run_group(
        self,
        requests: tuple[CollisionRequest, ...],
        experiment_deadline: float,
    ) -> tuple[CollisionResponse, ...]:
        barrier = threading.Barrier(len(requests) + 1)
        response_lock = threading.Lock()
        responses: list[CollisionResponse] = []
        synchronization_timeout = self._budget.synchronization_timeout_ms / 1000
        request_timeout = self._budget.request_timeout_ms / 1000

        def invoke(index: int, request: CollisionRequest) -> None:
            started_ns = 0
            try:
                barrier.wait(timeout=synchronization_timeout)
                started_ns = time.monotonic_ns()
                value = request(request_timeout)
                response = CollisionResponse(index, value, None, started_ns, time.monotonic_ns())
            except threading.BrokenBarrierError:
                response = CollisionResponse(index, None, "SYNCHRONIZATION_TIMEOUT", started_ns, time.monotonic_ns())
            except Exception as exc:  # noqa: BLE001 - 只保留异常类型，禁止泄露目标正文或凭据
                response = CollisionResponse(index, None, f"REQUEST_{type(exc).__name__.upper()}", started_ns, time.monotonic_ns())
            with response_lock:
                responses.append(response)

        threads = [
            threading.Thread(target=invoke, args=(index, request), daemon=True, name=f"collision-{index}")
            for index, request in enumerate(requests)
        ]
        for thread in threads:
            thread.start()
        try:
            barrier.wait(timeout=synchronization_timeout)
        except threading.BrokenBarrierError:
            pass
        group_deadline = min(experiment_deadline, time.monotonic() + request_timeout)
        for thread in threads:
            thread.join(timeout=max(0.0, group_deadline - time.monotonic()))
        return tuple(sorted(responses, key=lambda item: item.request_index))
