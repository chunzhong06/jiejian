# Worker 生命周期、进程和监督边界的正式延迟导出面。

from importlib import import_module

_EXPORTS = {
    "LocalWorkerSupervisor": (".supervisor", "LocalWorkerSupervisor"),
    "WorkerLifetimeLock": (".lifetime", "WorkerLifetimeLock"),
}


def __getattr__(name: str):
    if name in {"lifetime", "process", "supervisor"}:
        return import_module(f".{name}", __name__)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


__all__ = sorted(_EXPORTS)
