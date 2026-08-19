# Artifact Check 隔离进程入口；stdout/stderr 不承载扫描内容。

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import ArtifactCheckRequestV1, ArtifactScanResultV1
from .scanner import scan_artifact


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m jiejian.artifacts.worker")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        request = ArtifactCheckRequestV1.model_validate_json(arguments.request.read_bytes(), strict=True)
        result = scan_artifact(request)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_bytes(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
