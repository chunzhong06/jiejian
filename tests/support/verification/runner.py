# 顺序调用正式开发入口；恢复只复用相同源码、测试、工具链和环境下完整通过的步骤。
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from tests.support.verification.catalog import inventory, plan, source_files, fingerprint
from tests.support.verification.reporting import write_report

ROOT = Path(__file__).resolve().parents[3]


def can_reuse(previous: dict, current: dict, task: dict) -> bool:
    if previous.get("plan", {}).get("environment") != current["environment"]:
        return False
    if not task.get("fingerprint"):
        return False
    return any(item.get("task") == task and item.get("status") == "PASSED" for item in previous.get("steps", []))


def execute(root: Path, output: Path, specification: dict, previous: dict | None = None) -> int:
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": "1", "status": "RUNNING", "plan": specification, "steps": [], "started_at": time.time()}
    destination = output / "report.json"
    write_report(destination, report)
    for task in specification["tasks"]:
        item = {"task": task, "status": "RUNNING"}
        report["steps"].append(item)
        if previous and can_reuse(previous, specification, task):
            item.update(status="PASSED", reused_from=previous.get("report_path", "provided-report"))
            write_report(destination, report)
            continue
        evidence = output / f"{task['id']}.json"
        environment = os.environ.copy()
        environment.update(PYTHONDONTWRITEBYTECODE="1", JIEJIAN_TEST_REPORT=str(evidence))
        command = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   str(root / "scripts/dev.ps1"), task["command"], *task["args"]]
        print(f"\n[验证步骤] {task['id']}\n", flush=True)
        started = time.monotonic()
        write_report(destination, report)
        try:
            completed = subprocess.run(command, cwd=root, env=environment, check=False)
            item.update(exit_code=completed.returncode, seconds=round(time.monotonic() - started, 3))
            if task["command"] in {"test", "frontend-test"}:
                detail = json.loads(evidence.read_text(encoding="utf-8")) if evidence.is_file() else {}
                item["status"] = ("PASSED" if detail.get("status") in {"PASSED", "COLLECTED"} else detail.get("status", "REPORT_MISSING")) if completed.returncode == 0 else "FAILED"
                item["evidence"] = evidence.name
            else:
                item["status"] = "PASSED" if completed.returncode == 0 else "FAILED"
            if fingerprint(root, source_files(root)) != specification["fingerprint"]:
                item["status"] = "INPUT_CHANGED"
        except (OSError, ValueError):
            item["status"] = "ENVIRONMENT_ERROR"
        write_report(destination, report)
        if item["status"] != "PASSED":
            report["status"] = "INCOMPLETE" if item["status"] in {"INCOMPLETE", "EMPTY", "REPORT_MISSING"} else "FAILED"
            break
    else:
        report["status"] = "PASSED"
    report["seconds"] = round(time.time() - report["started_at"], 3)
    write_report(destination, report)
    print(f"验证状态：{report['status']}；报告：{destination}", flush=True)
    return 0 if report["status"] == "PASSED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="界鉴本地测试计划、证据与恢复；不接入 CI")
    parser.add_argument("action", choices=["inventory", "plan", "run", "browser"])
    parser.add_argument("--level", choices=["L1", "L2", "L3", "L4"], default="L2")
    parser.add_argument("--area", action="append", default=[])
    parser.add_argument("--changed", action="append", default=[])
    parser.add_argument("--l5", action="append", choices=["official", "ordinary", "validation", "competition", "portable", "windows"], default=[])
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--step", action="append", default=[], help="仅执行指定计划步骤；报告明确标为局部证据")
    options = parser.parse_args()
    if options.action == "browser":
        from tests.acceptance.ui.review import run
        return run(ROOT)
    if options.action == "inventory":
        value = inventory(ROOT)
        destination = ROOT / "var/audit/testing/inventory.json"
        write_report(destination, value)
        print(f"测试文件：{len(value['files'])}；能力清单：{destination}")
        return 0
    specification = plan(ROOT, level=options.level, areas=options.area, changed=options.changed, l5=options.l5)
    if options.step:
        names = {task["id"] for task in specification["tasks"]}
        if set(options.step) - names:
            raise ValueError("UNKNOWN_PLAN_STEP")
        specification["omitted_steps"] = sorted(names - set(options.step))
        specification["tasks"] = [task for task in specification["tasks"] if task["id"] in options.step]
        specification["evidence_scope"] = "仅指定步骤的局部证据，不代表整轮 L4"
        print("本次仅执行指定步骤；先前证据需在阶段验收时分别核对。", flush=True)
    output = ROOT / "var/audit/testing" / (time.strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8])
    if options.action == "plan":
        write_report(output / "plan.json", specification)
        for task in specification["tasks"]:
            print(f"{task['id']}: {task['command']} ({len(task['args'])} 个参数)")
        print(output / "plan.json")
        return 0
    previous = None
    if options.resume:
        previous = json.loads(options.resume.read_text(encoding="utf-8"))
        if previous.get("schema_version") != "1":
            raise ValueError("TEST_REPORT_VERSION")
        previous["report_path"] = str(options.resume)
    return execute(ROOT, output, specification, previous)


if __name__ == "__main__":
    raise SystemExit(main())
