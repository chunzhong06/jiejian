# 在已有进程闸门放行后核对受控副本并生成回执，再运行明确的 Python 入口。
from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

from product.backend.infra.runtime.process.controlled.artifact import read_runtime_manifest, verify_runtime_artifact
from product.protocols.runtime.runtime_identity import RuntimeLaunchReceipt, runtime_manifest_fingerprint


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()
    manifest = read_runtime_manifest(parsed.manifest)
    source_root = parsed.manifest.parent / "source"
    if Path.cwd().resolve() != source_root.resolve():
        raise ValueError("runtime artifact working directory mismatch")
    if os.environ.get("JIEJIAN_RUNTIME_FINGERPRINT") != manifest.interpreter_fingerprint:
        raise ValueError("runtime interpreter identity mismatch")
    verify_runtime_artifact(source_root, manifest)
    receipt = RuntimeLaunchReceipt(instance_id=manifest.instance_id,
        manifest_fingerprint=runtime_manifest_fingerprint(manifest), process_id=os.getpid(),
        source_fingerprint=manifest.source_fingerprint, interpreter_fingerprint=manifest.interpreter_fingerprint)
    # 独立启动只允许一个回执；旧回执不能被新进程覆盖成同一实例。
    with (parsed.manifest.parent / "started.json").open("x", encoding="utf-8") as stream:
        stream.write(receipt.model_dump_json())
    arguments = parsed.arguments[1:] if parsed.arguments[:1] == ["--"] else parsed.arguments
    sys.argv = [manifest.entry_module, *arguments]
    sys.path.insert(0, str(source_root.resolve()))
    # 用已核对的绝对入口文件，避免同名 site-package 成为实际启动对象。
    runpy.run_path(str(source_root / f"{manifest.entry_module}.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
