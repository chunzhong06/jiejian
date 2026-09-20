# 只读 Git 上下文；不读取远端、提交正文或凭据，不改动仓库和索引。
from __future__ import annotations

import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Literal

from pydantic import Field
from product.protocols.execution_v3 import WireModel


class GitSourceContext(WireModel):
    status: Literal["AVAILABLE", "UNBORN", "NOT_A_REPOSITORY", "UNAVAILABLE"]
    head: str | None = Field(default=None, pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    has_local_changes: bool | None = None


def _git(root: Path, *args: str) -> tuple[int, bytes]:
    # 禁止环境重定向仓库、可执行配置和索引刷新；输出与执行时间同时有界。
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    # 保留正常换行与 attributes 配置，否则 Windows CRLF 会被误报为变化。
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    with subprocess.Popen(["git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c",
                           "core.untrackedCache=false", *args], cwd=root, env=env,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
        with ThreadPoolExecutor(max_workers=1) as pool:
            read = pool.submit(process.stdout.read, 65537)
            try:
                output = read.result(timeout=3)
                if len(output) > 65536:
                    raise ValueError("bounded Git output exceeded")
                return process.wait(timeout=1), output.strip()
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()


def inspect_git_source(root: str | Path) -> GitSourceContext:
    """读取授权源码目录的当前 Git 上下文；无法核对时不返回部分身份或异常正文。"""
    root = Path(root)
    try:
        code, inside = _git(root, "rev-parse", "--is-inside-work-tree")
        if code or inside != b"true":
            marker = any((parent / ".git").exists() for parent in (root, *root.parents))
            return GitSourceContext(status="UNAVAILABLE" if marker else "NOT_A_REPOSITORY")
        first_code, first = _git(root, "rev-parse", "--verify", "HEAD")
        # status 可能通过 attributes 触发自定义 clean/process filter；存在此配置时只读 HEAD。
        filter_code, filters = _git(root, "config", "--name-only", "--get-regexp", r"^filter\..*\.(clean|process)$")
        if filter_code not in (0, 1):
            return GitSourceContext(status="UNAVAILABLE")
        code, status = (0, b"") if filters else _git(root, "status", "--porcelain=v1", "--untracked-files=normal",
                                                    "--ignore-submodules=all", "--", ".")
        last_code, last = _git(root, "rev-parse", "--verify", "HEAD")
        if code or (first_code, first) != (last_code, last):
            return GitSourceContext(status="UNAVAILABLE")
        if first_code:
            return GitSourceContext(status="UNBORN", has_local_changes=None if filters else bool(status))
        if not re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", first):
            return GitSourceContext(status="UNAVAILABLE")
        return GitSourceContext(status="AVAILABLE", head=first.decode("ascii"), has_local_changes=None if filters else bool(status))
    except (OSError, ValueError, subprocess.SubprocessError, TimeoutError):
        return GitSourceContext(status="UNAVAILABLE")
