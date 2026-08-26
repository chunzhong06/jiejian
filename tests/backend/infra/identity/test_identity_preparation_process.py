# 验证身份准备进程日志只保留可诊断稳定代码，不泄露异常正文。

from __future__ import annotations

from io import StringIO

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.identity.process import (
    _write_safe_failure,
)


def test_safe_failure_log_keeps_only_error_type_and_stable_code() -> None:
    output = StringIO()

    _write_safe_failure(
        output,
        JiejianError(
            ErrorCode.IDENTITY_PREPARATION_FAILED,
            "secret-value-must-not-appear",
        ),
    )

    assert output.getvalue() == (
        "IDENTITY_PREPARATION_DIAGNOSTIC "
        "type=JiejianError code=IDENTITY_PREPARATION_FAILED\n"
    )


def test_safe_failure_log_keeps_windows_error_number() -> None:
    output = StringIO()

    error = OSError(1312, "secret-value-must-not-appear")
    _write_safe_failure(output, error)

    rendered = output.getvalue()
    assert rendered.startswith("IDENTITY_PREPARATION_DIAGNOSTIC type=")
    assert rendered.endswith(" os_code=1312\n")
    assert "secret-value-must-not-appear" not in rendered
