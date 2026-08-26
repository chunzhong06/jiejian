# =============================================================================
# 测试身份准备子进程入口
#
# 定位
#   受控 Python 子进程协议、headed browser 与 Windows SecretStore 的组合边界。
#
# 职责
#   读取唯一请求｜等待显式保存/取消控制｜写入非秘密结果和可恢复引用日志。
#
# 边界
#   stdout 只承载结果协议；stderr 只输出稳定代码；密码、Cookie/Token 正文不落盘。
#
# 调用链
#   IdentityPreparationManager → process bootstrap → browser adapter → result
# =============================================================================

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO, TextIO
from uuid import uuid4

from product.backend.core.errors import JiejianError
from product.backend.infra.identity.browser import IdentityPreparationBrowserAdapter
from product.backend.infra.identity.control import (
    identity_preparation_control_paths,
    valid_identity_preparation_marker,
    write_identity_preparation_marker,
)
from product.backend.infra.secrets import default_secret_store
from product.protocols import (
    IDENTITY_PREPARATION_REQUEST_MAX_BYTES,
    IdentityPreparationResultType,
    canonical_identity_preparation_json_bytes,
    parse_identity_preparation_request,
)


IDENTITY_PREPARATION_EXIT_OK = 0
IDENTITY_PREPARATION_EXIT_PROTOCOL = 64
IDENTITY_PREPARATION_EXIT_INTERNAL = 70
_ATTEMPT_DIR_ENV = "JIEJIAN_IDENTITY_PREPARATION_DIR"


def _write_safe_failure(stderr: TextIO, exc: BaseException) -> None:
    """只记录异常类别和稳定代码，避免把页面内容或凭据带入日志。"""

    fields = ["IDENTITY_PREPARATION_DIAGNOSTIC", f"type={type(exc).__name__}"]
    if isinstance(exc, JiejianError):
        fields.append(f"code={exc.code}")
    elif isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        os_code = winerror if winerror is not None else exc.errno
        if os_code is not None:
            fields.append(f"os_code={os_code}")
    stderr.write(" ".join(fields) + "\n")


def execute_identity_preparation(
    *,
    stdin: BinaryIO,
    stdout: BinaryIO,
    stderr: TextIO,
    environ: Mapping[str, str] | None = None,
    adapter: IdentityPreparationBrowserAdapter | None = None,
) -> int:
    environment = os.environ if environ is None else environ
    try:
        raw = stdin.read(IDENTITY_PREPARATION_REQUEST_MAX_BYTES + 1)
        request = parse_identity_preparation_request(raw)
        controls = identity_preparation_control_paths(
            Path(environment[_ATTEMPT_DIR_ENV])
        )
    except (JiejianError, KeyError, OSError, ValueError):
        stderr.write("IDENTITY_PREPARATION_PROTOCOL_INVALID\n")
        return IDENTITY_PREPARATION_EXIT_PROTOCOL

    def write_journal(secret_refs: tuple[str, ...]) -> None:
        payload = json.dumps(
            {
                "schema_version": "1",
                "identity_id": request.identity_id,
                "secret_refs": list(secret_refs),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        temporary = controls.journal.with_name(
            f".{controls.journal.name}.tmp-{uuid4().hex}"
        )
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, controls.journal)
        finally:
            temporary.unlink(missing_ok=True)

    try:
        runner = adapter or IdentityPreparationBrowserAdapter()
        result = runner.run(
            request,
            secret_store=default_secret_store(),
            ready_callback=lambda: write_identity_preparation_marker(
                controls.ready, root=controls.root
            ),
            save_requested=lambda: valid_identity_preparation_marker(controls.save),
            cancellation_requested=lambda: valid_identity_preparation_marker(
                controls.cancel
            ),
            before_secret_write=write_journal,
            error_observer=lambda exc: _write_safe_failure(stderr, exc),
        )
        if result.result_type is IdentityPreparationResultType.PREPARED:
            write_journal(
                tuple(cookie.value_secret_ref for cookie in result.cookies)
                + ((result.bearer_secret_ref,) if result.bearer_secret_ref else ())
            )
        stdout.write(canonical_identity_preparation_json_bytes(result))
        stdout.flush()
        return IDENTITY_PREPARATION_EXIT_OK
    except Exception:
        stderr.write("IDENTITY_PREPARATION_FAILED\n")
        return IDENTITY_PREPARATION_EXIT_INTERNAL


def main() -> int:
    return execute_identity_preparation(
        stdin=sys.stdin.buffer,
        stdout=sys.stdout.buffer,
        stderr=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
