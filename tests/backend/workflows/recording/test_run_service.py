# Recording 运行编排测试：验证同一命令生命周期内的采集顺序与进程清理。

from types import SimpleNamespace

from product.backend.workflows.recording import run_service as run_service_module
from product.backend.workflows.recording.run_service import RecordingRunService


def test_capture_waits_for_ready_then_starts_stops_and_closes(monkeypatch, tmp_path) -> None:
    events: list[str] = []
    phase = {"value": "AWAITING_CAPTURE"}

    class Process:
        def poll(self):
            return None

    class Dispatcher:
        def __init__(self, **_kwargs) -> None:
            events.append("dispatcher")

        def start(self, **_kwargs):
            events.append("worker-start")
            return Process()

        def wait_recording(self, *_args, **_kwargs) -> None:
            events.append("worker-finished")
            phase["value"] = "FINISHED"

        def close_process(self, _process) -> None:
            events.append("worker-closed")

    class Lifecycle:
        def status(self, _recording_id):
            return SimpleNamespace(capture_phase=phase["value"])

        def start_capture(self, _recording_id) -> None:
            events.append("capture-start")
            phase["value"] = "CAPTURING"

        def stop_capture(self, _recording_id) -> None:
            events.append("capture-stop")
            phase["value"] = "STOPPING"

    monkeypatch.setattr(
        run_service_module,
        "required_recording_secret_names",
        lambda _request: (),
    )
    service = RecordingRunService(
        tmp_path,
        lambda: None,
        SimpleNamespace(),
        lambda _names: {},
        dispatcher_factory=Dispatcher,
    )
    started = SimpleNamespace(
        request=SimpleNamespace(recording_id="rec_current"),
        result=SimpleNamespace(job=SimpleNamespace(job_id="job_current")),
    )

    result = service.capture(
        started,
        lifecycle=Lifecycle(),
        capture_control=lambda: events.append("user-finished"),
        timeout_seconds=5,
    )

    assert result.capture_phase == "FINISHED"
    assert events == [
        "dispatcher",
        "worker-start",
        "capture-start",
        "user-finished",
        "capture-stop",
        "worker-finished",
        "worker-closed",
    ]
