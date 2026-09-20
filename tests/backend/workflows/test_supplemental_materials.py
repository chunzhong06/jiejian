# 验证补充材料只保存人工修订与幂等收据，不形成执行事实；全部使用离线 fixture。
from copy import deepcopy
from uuid import uuid4
from functools import partial
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from product.backend.core.errors import JiejianError
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.storage.supplemental_materials import SupplementalMaterialRepository
from product.backend.workflows.supplemental_contract import SupplementalDocument
from product.backend.workflows.supplemental_contract import material_fingerprint
from product.backend.workflows.supplemental_materials import SupplementalMaterialService
from product.backend.api.routers.supplemental_materials import build_supplemental_material_router
from tests.fixtures.action_preparation import build_preparation_harness


@pytest.fixture
def material(tmp_path):
    harness = build_preparation_harness(tmp_path)
    document = dict(schema_version="1", project_id=harness.project_id, action_id=harness.action.action_id,
        action_revision=1, title="人工导出记录", source_label="用户整理", claimed_resource_label=None,
        records=[dict(recorded_at_us=0, resource_label="交付包", event_label="用户记录已导出")])
    yield harness, document
    harness.close()


def create(harness, document, request_id=None):
    service = harness.core.supplemental_materials
    preview = service.preview(harness.project_id, harness.action.action_id, document)
    return service.create(harness.project_id, harness.action.action_id, document=document,
        expected_fingerprint=preview["fingerprint"], request_id=request_id or str(uuid4()))


def test_preview_append_replay_withdraw_preserve_execution_facts(material):
    harness, document = material
    service = harness.core.supplemental_materials
    project, action = harness.project_id, harness.action.action_id
    before = harness.core.preparation.get(project)
    key = str(uuid4())
    first = create(harness, document, key)
    assert create(harness, document, key) == first
    assert first["revision"] == 1 and first["usage"] == "SUPPLEMENTAL_ONLY"
    second = service.revise(project, action, first["material_id"], expected_revision=1, request_id=str(uuid4()),
        title="补充说明", source_label="用户整理", claimed_resource_label="交付包")
    assert second["records"] == first["records"] and second["association_status"] == "USER_DECLARED"
    withdrawn = service.withdraw(project, action, first["material_id"], expected_revision=2, request_id=str(uuid4()))
    assert withdrawn["withdrawn"] and withdrawn["revision"] == 3
    history = service.list(project, action, material_id=first["material_id"])
    assert [item["revision"] for item in history["items"]] == [3, 2, 1]
    assert history["items"][-1] == first
    page = service.list(project, action, material_id=first["material_id"], limit=2)
    assert [item["revision"] for item in page["items"]] == [3, 2] and page["has_more"]
    older = service.list(project, action, material_id=first["material_id"], limit=2, before_revision=2)
    assert older["items"] == [first] and not older["has_more"]
    assert harness.core.preparation.get(project) == before
    with harness.core.uow_factory() as work:
        assert work.runs.list_for_project(project) == ()
        assert work.jobs.list_for_project(project) == ()


def test_conflicts_scope_and_stale_revision_rejected(material):
    harness, document = material
    key = str(uuid4())
    first = create(harness, document, key)
    changed = dict(document, title="另一份材料")
    with pytest.raises(JiejianError) as error:
        create(harness, changed, key)
    assert error.value.code == "STATE_PRECONDITION"
    with pytest.raises(JiejianError):
        create(harness, dict(document, project_id="other"))
    with pytest.raises(JiejianError):
        create(harness, dict(document, action_revision=2))
    with pytest.raises(JiejianError):
        harness.core.supplemental_materials.list("other", document["action_id"], material_id=first["material_id"])
    with pytest.raises(JiejianError):
        harness.core.supplemental_materials.withdraw(document["project_id"], document["action_id"], first["material_id"],
            expected_revision=2, request_id=str(uuid4()))


@pytest.mark.parametrize("text_value", ["Bearer abcdef", "token=abcdef", "credentials: abcdef", "-----BEGIN PRIVATE KEY-----", "<script>alert(1)</script>"])
def test_secret_text_rejected_before_storage(material, text_value):
    harness, document = material
    with pytest.raises((JiejianError, ValidationError)):
        create(harness, dict(document, title=text_value))
    assert harness.core.supplemental_materials.list(harness.project_id, document["action_id"])["items"] == []


def test_unknown_fields_budget_and_known_secret(material):
    harness, document = material
    with pytest.raises(ValidationError):
        SupplementalDocument.model_validate(dict(document, credentials="hidden"))
    oversized = dict(document, records=[dict(recorded_at_us=0, resource_label="中" * 128, event_label="中" * 256)] * 100)
    with pytest.raises(JiejianError):
        SupplementalDocument.model_validate(oversized)
    factory = harness.core.uow_factory
    def known():
        work = factory()
        work._known_secrets = ("opaque-sensitive-value",)
        return work
    service = SupplementalMaterialService(known)
    with pytest.raises(JiejianError):
        service.preview(harness.project_id, document["action_id"], dict(document, title="opaque-sensitive-value"))
    secret_document = dict(document, title="opaque-sensitive-value")
    with pytest.raises(JiejianError):
        service.create(harness.project_id, document["action_id"], document=secret_document,
            expected_fingerprint=material_fingerprint(secret_document), request_id=str(uuid4()))


def test_bounded_latest_list_and_empty_optional_label(material):
    harness, document = material
    first = create(harness, dict(document, claimed_resource_label=""))
    assert first["association_status"] == "UNCONFIRMED"
    create(harness, dict(document, title="第二份"))
    page = harness.core.supplemental_materials.list(harness.project_id, document["action_id"], limit=1)
    assert len(page["items"]) == 1 and page["has_more"] and page["limit"] == 1


def test_receipt_and_revision_roll_back_together(material, monkeypatch):
    harness, document = material
    original = SupplementalMaterialRepository.add
    def fail(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("injected after receipt")
    monkeypatch.setattr(SupplementalMaterialRepository, "add", fail)
    key = str(uuid4())
    with pytest.raises(RuntimeError):
        create(harness, document, key)
    with harness.core.uow_factory() as work:
        assert work.supplemental_materials.receipt(harness.project_id, key) is None
        assert work.supplemental_materials.list(harness.project_id, document["action_id"])[0] == []


def test_material_api_exact_contract_and_bound(material):
    harness, document = material
    app = FastAPI()
    app.include_router(build_supplemental_material_router(harness.core))
    path = f"/api/projects/{harness.project_id}/actions/{document['action_id']}/supplemental-materials"
    with TestClient(app) as client:
        preview = client.post(path + "/preview", json={"document": document})
        assert preview.status_code == 200
        first = client.post(path, json=dict(document=document, expected_fingerprint=preview.json()["data"]["fingerprint"], request_id=str(uuid4())))
        assert first.status_code == 200
        assert first.json()["data"]["usage"] == "SUPPLEMENTAL_ONLY"
        history_path = path + "/" + first.json()["data"]["material_id"] + "/revisions"
        assert client.get(history_path + "?before_revision=1").json()["data"]["items"] == []
        assert client.get(history_path + "?before_revision=0").status_code == 422
        assert client.get(path + "?limit=101").status_code == 422
        assert client.post(path + "/preview", json={"document": document, "path": "file.json"}).status_code == 422
