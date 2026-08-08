from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml

from jiejian.errors import ErrorCode, JiejianError
from jiejian.inputs import load_contract, load_project_bundle


def test_project_validation_is_offline(
    stage1_project_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = stage1_project_factory(34567)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: pytest.fail("离线校验不得解析 DNS"),
    )
    bundle = load_project_bundle(path)
    assert bundle.project.id == "test-project-1"


def test_project_reference_cannot_escape_project_directory(
    stage1_project_factory,
) -> None:
    path = stage1_project_factory(34567)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["flow"] = "../outside.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(JiejianError) as captured:
        load_project_bundle(path)
    assert captured.value.code == ErrorCode.INPUT_PATH.value


def test_yaml_rejects_duplicate_keys_and_unsafe_tags(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        'schema_version: "1"\ncontract:\n  id: first\n  id: second\n',
        encoding="utf-8",
    )
    with pytest.raises(JiejianError) as captured:
        load_contract(duplicate)
    assert captured.value.code == ErrorCode.INPUT_FILE.value

    unsafe = tmp_path / "unsafe.yaml"
    unsafe.write_text(
        'schema_version: "1"\ncontract: !!python/object/apply:os.system ["echo bad"]\n',
        encoding="utf-8",
    )
    with pytest.raises(JiejianError) as captured:
        load_contract(unsafe)
    assert captured.value.code == ErrorCode.INPUT_FILE.value


def test_yaml_rejects_anchors_and_unknown_project_fields(
    stage1_project_factory,
) -> None:
    path = stage1_project_factory(34567)
    original = path.read_text(encoding="utf-8")
    path.write_text(f"shared: &shared value\n{original}", encoding="utf-8")
    with pytest.raises(JiejianError) as captured:
        load_project_bundle(path)
    assert captured.value.code == ErrorCode.INPUT_FILE.value

    path.write_text(f"unexpected: value\n{original}", encoding="utf-8")
    with pytest.raises(JiejianError) as captured:
        load_project_bundle(path)
    assert captured.value.code == ErrorCode.INPUT_INVALID.value


def test_contract_schema_requires_explicit_version_and_known_fields(tmp_path: Path) -> None:
    invalid = tmp_path / "contract.yaml"
    invalid.write_text(
        "contract:\n  id: ownership\n  unexpected: true\n",
        encoding="utf-8",
    )
    with pytest.raises(JiejianError) as captured:
        load_contract(invalid)
    assert captured.value.code == ErrorCode.INPUT_INVALID.value
