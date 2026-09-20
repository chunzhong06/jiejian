# 以临时仓库核对 Git 元数据；所有写入只用于构造测试数据，生产 reader 始终只读。
import os
import subprocess

from product.backend.infra.source_identity import inspect_git_source


def git(root, *args):
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                          cwd=root, env=env, capture_output=True, check=True).stdout


def test_repository_content_changes_do_not_require_head_changes(tmp_path, monkeypatch):
    from product.backend.infra import source_identity
    actual_git = source_identity._git
    # 这份 fixture 不含 attributes；隔离机器预装的 LFS 配置，专测原生状态与 CRLF。
    monkeypatch.setattr(source_identity, "_git", lambda root, *args: (1, b"") if args[0] == "config" else actual_git(root, *args))
    git(tmp_path, "init", "--quiet")
    (tmp_path / "source.py").write_text("value = 1\n", encoding="utf-8")
    unborn = inspect_git_source(tmp_path)
    assert unborn.status == "UNBORN" and unborn.head is None
    git(tmp_path, "add", "source.py")
    git(tmp_path, "commit", "--quiet", "-m", "fixture")
    index_before = (tmp_path / ".git/index").read_bytes()
    clean = inspect_git_source(tmp_path)
    assert clean.status == "AVAILABLE" and clean.has_local_changes is False
    assert (tmp_path / ".git/index").read_bytes() == index_before
    (tmp_path / "source.py").write_text("value = 2\n", encoding="utf-8")
    dirty = inspect_git_source(tmp_path)
    assert dirty.head == clean.head and dirty.has_local_changes is True
    assert (tmp_path / ".git/index").read_bytes() == index_before


def test_plain_directory_and_unavailable_git_are_distinct(tmp_path, monkeypatch):
    # fixture 目录使用发现边界，避免从测试工作树的父仓库借用 Git 身份。
    monkeypatch.setenv("GIT_DIR", "ignored")
    from product.backend.infra import source_identity
    monkeypatch.setattr(source_identity, "_git", lambda *args: (128, b""))
    isolated = tmp_path / "source"
    isolated.mkdir()
    # 父目录属于仓库时不可把失败谎称为没有使用 Git。
    value = inspect_git_source(isolated)
    assert value.status in {"NOT_A_REPOSITORY", "UNAVAILABLE"}
    def unavailable(*args):
        raise FileNotFoundError("private command path")
    monkeypatch.setattr(source_identity, "_git", unavailable)
    assert inspect_git_source(isolated).model_dump() == {"status": "UNAVAILABLE", "head": None, "has_local_changes": None}


def test_changed_head_during_observation_is_unavailable(tmp_path, monkeypatch):
    from product.backend.infra import source_identity
    calls = iter([(0, b"true"), (0, b"a" * 40), (1, b""), (0, b""), (0, b"b" * 40)])
    monkeypatch.setattr(source_identity, "_git", lambda *args: next(calls))
    assert inspect_git_source(tmp_path).status == "UNAVAILABLE"


def test_configured_filters_never_execute_during_read(tmp_path, monkeypatch):
    from product.backend.infra import source_identity
    calls = []
    def metadata(root, *args):
        calls.append(args)
        if args[0] == "config":
            return 0, b"filter.custom.clean"
        if "--is-inside-work-tree" in args:
            return 0, b"true"
        return 0, b"a" * 40
    monkeypatch.setattr(source_identity, "_git", metadata)
    result = inspect_git_source(tmp_path)
    assert result.status == "AVAILABLE" and result.has_local_changes is None
    assert not any(args[0] == "status" for args in calls)
