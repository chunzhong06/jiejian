# 受控进程的启动、环境、锁与进程树边界的正式延迟导出面。

from importlib import import_module

_EXPORTS = {
    "AttemptProcessControl": (".control", "AttemptProcessControl"),
    "ProcessEnvironmentRole": (".environment", "ProcessEnvironmentRole"),
    "ProcessTreeController": (".tree", "ProcessTreeController"),
    "confirmed_python_executable": (".environment", "confirmed_python_executable"),
    "force_terminate_process_tree": (".control", "force_terminate_process_tree"),
    "lock_is_available": (".lock", "lock_is_available"),
    "minimal_process_environment": (".environment", "minimal_process_environment"),
    "python_environment_report": (".identity", "python_environment_report"),
    "python_module_command": (".environment", "python_module_command"),
    "require_python_environment": (".identity", "require_python_environment"),
    "run_python_module": (".environment", "run_python_module"),
    "spawn_python_module": (".environment", "spawn_python_module"),
    "try_lock_stream": (".lock", "try_lock_stream"),
    "unlock_stream": (".lock", "unlock_stream"),
}


def __getattr__(name: str):
    if name in {"bootstrap", "control", "environment", "identity", "lock", "tree"}:
        return import_module(f".{name}", __name__)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


__all__ = sorted(_EXPORTS)
