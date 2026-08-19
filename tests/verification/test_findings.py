from __future__ import annotations

import pytest

from product.backend.core.verification.findings import FindingIdentity


def _identity(**changes):
    values = {
        "project_id": "finding-project",
        "permission_intent": ("rule:foreign-read", "kind:foreign_read"),
        "subject_class": ("role:member", "tenant:tenant-a"),
        "action": "get",
        "resource_class": ("type:document", "tenant:tenant-a"),
        "resource_relation": ("relation:foreign",),
        "problem_category": "foreign-read",
    }
    return FindingIdentity(**(values | changes))


def test_finding_id_is_stable_without_run_case_or_time() -> None:
    first = _identity()
    second = _identity()
    assert first.finding_id() == second.finding_id()
    assert first.stable_key_sha256() == second.stable_key_sha256()


@pytest.mark.parametrize(
    "field,value",
    [
        ("project_id", "other-project"),
        ("permission_intent", ("rule:other", "kind:foreign_read")),
        ("subject_class", ("role:member", "tenant:tenant-b")),
        ("action", "patch"),
        ("resource_class", ("type:account", "tenant:tenant-a")),
        ("resource_relation", ("relation:owns",)),
        ("problem_category", "side-effect"),
    ],
)
def test_finding_id_does_not_merge_distinct_identity_dimensions(field, value) -> None:
    assert _identity().finding_id() != _identity(**{field: value}).finding_id()


def test_finding_identity_rejects_secret_like_tokens() -> None:
    with pytest.raises(ValueError, match="non-secret"):
        _identity(problem_category="authorization-token")
