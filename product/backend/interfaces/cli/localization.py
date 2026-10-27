# 将 Click/Typer 的框架标题和参数错误收敛为界鉴自己的中文命令行表面。

from __future__ import annotations

import re
from collections.abc import Callable

from typer import _click, rich_utils


class ChineseHelpFormatter(_click.HelpFormatter):
    """只替换框架生成的用法前缀，命令与参数名保持协议原文。"""

    def write_usage(
        self,
        prog: str,
        args: str = "",
        prefix: str | None = None,
    ) -> None:
        super().write_usage(prog, args, prefix or "用法：")


def _translate_framework_message(message: str) -> str:
    translations: tuple[tuple[str, str], ...] = (
        (r"^No such command '([^']+)'\.$", r"没有名为“\1”的命令。"),
        (r"^No such option: (.+)$", r"没有这个选项：\1"),
        (r"^Missing argument '([^']+)'\.$", r"缺少必需参数“\1”。"),
        (r"^Missing option '([^']+)'\.$", r"缺少必需选项“\1”。"),
        (r"^Missing parameter: (.+)$", r"缺少必需参数：\1"),
        (r"^Got unexpected extra argument \((.+)\)$", r"存在无法识别的额外参数（\1）。"),
        (r"^Invalid value for (.+): (.+)$", r"\1 的值无效：\2"),
        (r"^Invalid value: (.+)$", r"参数值无效：\1"),
        (r"^Missing command\.$", "缺少命令。"),
    )
    translated = message
    for pattern, replacement in translations:
        translated = re.sub(pattern, replacement, translated)
        if translated != message:
            break
    return re.sub(
        r"\. Did you mean (.+)\?$",
        r"。你是否想输入 \1？",
        translated,
    )


def _localized_formatter(
    original: Callable[[_click.ClickException], str],
) -> Callable[[_click.ClickException], str]:
    def format_message(error: _click.ClickException) -> str:
        return _translate_framework_message(original(error))

    return format_message


def configure_cli_localization() -> None:
    """在当前界鉴进程内本地化帮助和用法错误，不改写 Typer/Click 安装包。"""

    _click.Context.formatter_class = ChineseHelpFormatter
    rich_utils.ARGUMENTS_PANEL_TITLE = "参数"
    rich_utils.OPTIONS_PANEL_TITLE = "选项"
    rich_utils.COMMANDS_PANEL_TITLE = "命令"
    rich_utils.ERRORS_PANEL_TITLE = "错误"
    rich_utils.RICH_HELP = "输入 [blue]'{command_path} {help_option}'[/] 查看帮助。"
    exception_types = (
        _click.exceptions.UsageError,
        _click.exceptions.BadParameter,
        _click.exceptions.MissingParameter,
        _click.exceptions.NoSuchOption,
        _click.exceptions.BadOptionUsage,
        _click.exceptions.BadArgumentUsage,
    )
    for exception_type in exception_types:
        if exception_type.__dict__.get("_jiejian_localized", False):
            continue
        exception_type.format_message = _localized_formatter(  # type: ignore[method-assign]
            exception_type.format_message
        )
        exception_type._jiejian_localized = True  # type: ignore[attr-defined]


__all__ = ["ChineseHelpFormatter", "configure_cli_localization"]
