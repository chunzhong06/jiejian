# =============================================================================
# Verification 输入边界测试
#
# 定位
#   证明 Project、Flow 和 Contract 在进入领域模型前受到离线、路径和 YAML 安全约束
#
# 职责
#   保护离线校验｜拒绝目录逃逸与危险 YAML｜固定 schema_version 和未知字段规则
#
# 调用链
#   pytest → load_project_bundle / load_contract → verification.inputs
# =============================================================================

from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml

from jiejian.errors import ErrorCode, JiejianError
from jiejian.verification.inputs import load_contract, load_project_bundle


def test_project_validation_is_offline(
    stage1_project_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """证明项目校验只读取本地输入；失败表示加载阶段错误地开始了解析网络地址。"""

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
    """证明项目内 Flow 引用不能越出项目目录；失败表示路径逃逸边界被破坏。"""

    path = stage1_project_factory(34567)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["flow"] = "../outside.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(JiejianError) as captured:
        load_project_bundle(path)
    assert captured.value.code == ErrorCode.INPUT_PATH.value


def test_yaml_rejects_duplicate_keys_and_unsafe_tags(tmp_path: Path) -> None:
    """证明重复键不能掩盖配置，危险 YAML 标签也不能构造任意 Python 对象。"""

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
    """证明项目输入拒绝 YAML 锚点和未声明字段，避免隐式复用或拼写错误被接受。"""

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
    """证明 Contract 必须显式声明受支持版本，且不能携带模型未知字段。"""

    invalid = tmp_path / "contract.yaml"
    invalid.write_text(
        "contract:\n  id: ownership\n  unexpected: true\n",
        encoding="utf-8",
    )
    with pytest.raises(JiejianError) as captured:
        load_contract(invalid)
    assert captured.value.code == ErrorCode.INPUT_INVALID.value
