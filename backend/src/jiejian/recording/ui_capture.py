# =============================================================================
# Recording UI 动作采集
#
# 定位
#   浏览器页面脚本与 Recording EventCollector 之间的最小元数据桥接
#
# 职责
#   初始化动作监听｜提取稳定定位信息｜阻止输入值和 secret 回传
#
# 调用链
#   RecordingEventCollector → install_ui_capture → browser binding / UI action callback
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from playwright.sync_api import BrowserContext

_BINDING_NAME = "__jiejianRecordUI"

_INIT_SCRIPT = r"""
(() => {
  if (globalThis.__jiejianUICaptureInstalled) return;
  Object.defineProperty(globalThis, "__jiejianUICaptureInstalled", {value: true});

  const cssEscape = value => globalThis.CSS?.escape
    ? globalThis.CSS.escape(value)
    : value.replace(/[^A-Za-z0-9_-]/g, "\\$&");
  const locator = element => {
    if (!(element instanceof Element)) return "unknown";
    const testId = element.getAttribute("data-testid");
    if (testId) return `[data-testid="${cssEscape(testId)}"]`;
    if (element.id) return `#${cssEscape(element.id)}`;
    const name = element.getAttribute("name");
    if (name) return `${element.tagName.toLowerCase()}[name="${cssEscape(name)}"]`;
    const parts = [];
    for (let node = element; node && node.nodeType === 1 && parts.length < 8; node = node.parentElement) {
      const siblings = node.parentElement
        ? [...node.parentElement.children].filter(item => item.tagName === node.tagName)
        : [];
      const suffix = siblings.length > 1 ? `:nth-of-type(${siblings.indexOf(node) + 1})` : "";
      parts.unshift(`${node.tagName.toLowerCase()}${suffix}`);
    }
    return parts.join(" > ") || "unknown";
  };
  const emit = (kind, target) => {
    const element = target instanceof Element ? target : null;
    if (!element || typeof globalThis.__jiejianRecordUI !== "function") return;
    const payload = {
      kind,
      element_locator: locator(element),
      field_name: element.getAttribute("name") || element.id || null,
      input_type: element instanceof HTMLInputElement ? (element.type || "text") : null,
    };
    void globalThis.__jiejianRecordUI(payload).catch(() => undefined);
  };
  addEventListener("click", event => emit("click", event.target), true);
  addEventListener("input", event => emit("input_change", event.target), true);
  addEventListener("submit", event => emit("submit", event.target), true);
})();
"""


def install_ui_capture(
    context: BrowserContext,
    callback: Callable[[Mapping[str, Any], Mapping[str, Any]], None],
) -> None:
    """在任何页面脚本执行前安装受限 binding 和捕获监听器。"""

    context.expose_binding(_BINDING_NAME, callback)
    context.add_init_script(script=_INIT_SCRIPT)
