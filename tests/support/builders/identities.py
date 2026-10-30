# 构造独立账号数据库、受控秘密替身与角色读取器，供账号用例测试共用。
from __future__ import annotations
from tests.support.secrets import MemorySecrets
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from product.backend.domain.applications.models import (
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
    candidate_id,
)
from product.backend.domain.lifecycle import ProjectStatus
from product.backend.domain.boundaries.entities import BusinessActor, boundary_sha256
from tests.support.builders.checks.assurance import actor
from product.backend.infrastructure.storage.applications.projects import ProjectRecord
from product.backend.infrastructure.storage.unit_of_work import StorageUnitOfWork
from product.backend.infrastructure.storage.db import (
    create_session_factory,
    create_sqlite_engine,
    prepare_database,
)
from product.backend.application.test_identities.service import (
    TestIdentityService as IdentityService,
)


PROJECT_ID = "sample-project"


ROLE_ID = candidate_id("role", "owner")


ACTOR_ID = "bar_" + "1" * 32


ENDPOINT = "http://127.0.0.1:8865"


FINGERPRINT = "a" * 64


class FakeSecretStore(MemorySecrets):
    # 只对本次测试的内存引用注入删除失败，用于核对补偿重试，不接触当前用户的系统凭据。
    def __init__(self) -> None:
        super().__init__()
        self.fail_delete = False

    def delete(self, secret_ref: str) -> None:
        if self.fail_delete:
            raise OSError("blocked")
        super().delete(secret_ref)


def application_understanding(
    *, endpoint: str = ENDPOINT, revision: int = 3
) -> ApplicationUnderstanding:
    return ApplicationUnderstanding(
        project_id=PROJECT_ID,
        source_root="D:/sample",
        confirmed_endpoint=endpoint,
        endpoint_source_fingerprint=FINGERPRINT,
        endpoint_confirmed_at_us=2,
        endpoint_last_checked_at_us=2,
        endpoint_reachable=True,
        role_candidates=(
            RoleCandidate(
                candidate_id=ROLE_ID,
                canonical_key="owner",
                display_name="所有者",
                confidence=CandidateConfidence.HIGH,
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.MANUAL,
            ),
        ),
        revision=revision,
        created_at_us=1,
        updated_at_us=2,
    )


def build_identity_service(tmp_path: Path) -> tuple[IdentityService, FakeSecretStore, object]:
    database = tmp_path / "var" / "data" / "jiejian.db"
    prepare_database(database)
    factory = create_session_factory(create_sqlite_engine(database))
    with StorageUnitOfWork(factory) as work:
        work.projects.add(
            ProjectRecord(
                project_id=PROJECT_ID,
                name="样例应用",
                status=ProjectStatus.DRAFT,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        work.application_understanding.add(application_understanding())
        revision = actor().model_copy(update={"project_id": PROJECT_ID, "display_name": "所有者"})
        revision = revision.model_copy(
            update={"semantic_fingerprint": boundary_sha256(revision.semantic_payload())}
        )
        work.business_boundaries.add_actor_revision(revision)
        work.business_boundaries.add_actor(
            BusinessActor(
                actor_id=ACTOR_ID,
                project_id=PROJECT_ID,
                current_revision=1,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        work.commit()
    store = FakeSecretStore()
    service = IdentityService(
        partial(StorageUnitOfWork, factory),
        secret_store=store,
        clock_us=lambda: 10,
    )
    return service, store, factory


def boundary_reader(factory):
    def view(project_id):
        with StorageUnitOfWork(factory) as work:
            root = work.business_boundaries.actor(ACTOR_ID)
            current = work.business_boundaries.actor_revision(ACTOR_ID, root.current_revision)
            return SimpleNamespace(actors=(current,))

    return SimpleNamespace(view=view)
