# 所属业务域的共享测试构造器；不导入测试用例。
from __future__ import annotations
import json
import pytest
import product.backend.infra.observers.adapters.async_task as async_module
from product.protocols import AsyncTaskApiLocator, AsyncTaskObserverInvocation, AsyncTaskPollBudget, Correlation, ObservationPhase, ObserverBudget, ObserverSpec, ObserverTarget, ObserverType

def _spec(*, base_url: str = "https://127.0.0.1:8443", allow_loopback_http: bool = False, max_polls: int = 4, poll_interval_us: int = 0, timeout_us: int = 5_000_000, max_response_bytes: int = 8192, common_max_bytes: int | None = None) -> ObserverSpec:
    locator = AsyncTaskApiLocator(
        base_url=base_url,
        relative_path_template="/observer/tasks/by-case/{request_marker}",
        read_only_credential_ref="env:TASK_TOKEN",
        allow_private_network=True,
        allow_loopback_http=allow_loopback_http,
        poll_budget=AsyncTaskPollBudget(max_polls=max_polls, poll_interval_us=poll_interval_us, per_request_timeout_us=100_000, max_response_bytes=max_response_bytes),
    )
    return ObserverSpec(
        observer_id="async_observer",
        observer_type=ObserverType.ASYNC_TASK_STATUS,
        target=ObserverTarget(target_id="task-state", locator=locator, normalization_id="task-state", normalization_version="1.0"),
        phases=(ObservationPhase.EVENTUAL,),
        required=True,
        budget=ObserverBudget(timeout_us=timeout_us, max_rows=1, max_bytes=common_max_bytes or max_response_bytes),
    )

def _response(state: str, *, task_id: str | None = "task-1", final_result: dict[str, object] | None = None, case_tag: str = "case-1", resource_id: str = "resource-a") -> bytes:
    return json.dumps({"schema_version": "1", "case_tag": case_tag, "resource_id": resource_id, "task_id": task_id, "state": state, "final_result": final_result}, separators=(",", ":")).encode()

def _invocation(spec: ObserverSpec | None = None) -> AsyncTaskObserverInvocation:
    return AsyncTaskObserverInvocation(spec=spec or _spec(), correlation=Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"), phase=ObservationPhase.EVENTUAL)

def _run_fake(monkeypatch: pytest.MonkeyPatch, responses: list[bytes], *, status_codes: list[int] | None = None, spec: ObserverSpec | None = None):
    invocation = _invocation(spec)
    monkeypatch.setenv("TASK_TOKEN", "opaque-task-secret")
    queue = list(responses)
    codes = list(status_codes or [200] * len(queue))

    class Response:
        def __init__(self, content: bytes, status_code: int) -> None:
            self.content = content
            self.status_code = status_code

        def iter_bytes(self):
            yield self.content

    class Stream:
        def __init__(self, response: Response) -> None:
            self.response = response

        def __enter__(self) -> Response:
            return self.response

        def __exit__(self, *args: object) -> None:
            return None

    class Client:
        last: Response | None = None

        def stream(self, method: str, url: str, *, headers: dict[str, str]) -> Stream:
            assert headers == {"Authorization": "Bearer opaque-task-secret"}
            if not queue:
                assert self.last is not None
                return Stream(self.last)
            self.last = Response(queue.pop(0), codes.pop(0))
            return Stream(self.last)

        def close(self) -> None:
            pass

    monkeypatch.setattr(async_module.httpx, "Client", lambda **kwargs: Client())
    envelope = async_module._run_child(invocation, utc_now_us=lambda: 100)
    return envelope, async_module.evaluate_observer_outcome(envelope, required=True)
