# 人工补充材料的登记、追加说明与撤回；不触达准备、执行、Evidence 或判定。
from __future__ import annotations

import time
import hashlib
from threading import RLock
from uuid import uuid4
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage.base import _canonical_json
from product.backend.workflows.supplemental_contract import SupplementalDocument, material_fingerprint, request_uuid, validate_material_payload


class SupplementalMaterialService:
    def __init__(self, uow_factory, *, clock_us=None):
        self._uow_factory = uow_factory
        self._clock = clock_us or (lambda: time.time_ns() // 1000)
        self._lock = RLock()

    @staticmethod
    def _action(work, project_id, action_id, revision=None):
        action = work.business_boundaries.action(action_id)
        if action is None or action.project_id != project_id or (revision is not None and action.current_revision != revision):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "材料必须关联本项目当前正式动作修订")

    @staticmethod
    def _document(project_id, action_id, document):
        document = SupplementalDocument.model_validate(document).model_dump(mode="json")
        if (document["project_id"], document["action_id"]) != (project_id, action_id):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "材料所属项目或动作不一致")
        return document

    def preview(self, project_id, action_id, document):
        document = self._document(project_id, action_id, document)
        with self._uow_factory() as work:
            self._action(work, project_id, action_id, document["action_revision"])
            validate_material_payload(document, work._known_secrets)
        return dict(project_id=project_id, action_id=action_id, document=document,
            fingerprint=material_fingerprint(document), record_count=len(document["records"]),
            association_status="USER_DECLARED" if document["claimed_resource_label"] else "UNCONFIRMED", usage="SUPPLEMENTAL_ONLY")

    def create(self, project_id, action_id, *, document, expected_fingerprint, request_id):
        document = self._document(project_id, action_id, document)
        fingerprint = material_fingerprint(document)
        if fingerprint != expected_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "材料预览已变化")
        return self._write(project_id, action_id, operation="create", request_id=request_id,
            payload=dict(document=document, expected_fingerprint=expected_fingerprint))

    def revise(self, project_id, action_id, material_id, *, expected_revision, request_id, **labels):
        return self._write(project_id, action_id, operation="revise", request_id=request_id,
            material_id=material_id, payload=dict(expected_revision=expected_revision, **labels))

    def withdraw(self, project_id, action_id, material_id, *, expected_revision, request_id):
        return self._write(project_id, action_id, operation="withdraw", request_id=request_id,
            material_id=material_id, payload=dict(expected_revision=expected_revision))

    def _write(self, project_id, action_id, *, operation, request_id, payload, material_id=None):
        request_id = request_uuid(request_id)
        receipt_hash = hashlib.sha256(_canonical_json(dict(operation=operation, project_id=project_id,
            action_id=action_id, material_id=material_id, payload=payload)).encode("utf-8")).hexdigest()
        with self._lock, self._uow_factory() as work:
            prior = work.supplemental_materials.receipt(project_id, request_id)
            if prior is not None:
                if prior[0] != receipt_hash:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "请求标识已用于不同材料操作")
                return prior[1]
            now = self._clock()
            if operation == "create":
                document = payload["document"]
                self._action(work, project_id, action_id, document["action_revision"])
                value = dict(document, material_id="mat_" + uuid4().hex, revision=1, received_at_us=now, updated_at_us=now, withdrawn=False)
            else:
                value = work.supplemental_materials.get(material_id)
                if value is None or (value["project_id"], value["action_id"]) != (project_id, action_id):
                    raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "本动作材料不存在")
                self._action(work, project_id, action_id)
                if value["revision"] != payload["expected_revision"] or value["withdrawn"]:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, "材料修订已变化或已经撤回")
                value.update(revision=value["revision"] + 1, updated_at_us=max(now, value["updated_at_us"]))
                if operation == "withdraw":
                    value["withdrawn"] = True
                else:
                    value.update({key: payload[key] for key in ("title", "source_label", "claimed_resource_label")})
            document = {key: value[key] for key in SupplementalDocument.model_fields if key != "schema_version"}
            document["schema_version"] = "1"
            document = SupplementalDocument.model_validate(document).model_dump(mode="json")
            value.pop("schema_version", None)
            value["fingerprint"] = material_fingerprint(document)
            validate_material_payload(document)
            work.supplemental_materials.add(value, request_id=request_id, content_fingerprint=receipt_hash)
            result = work.supplemental_materials.get(value["material_id"], value["revision"])
            work.commit()
            return result

    def list(self, project_id, action_id, *, material_id=None, limit=100, before_revision=None):
        if not 1 <= limit <= 100:
            raise JiejianError(ErrorCode.INPUT_INVALID, "材料列表上限为 100")
        if before_revision is not None and (material_id is None or type(before_revision) is not int or before_revision < 1):
            raise JiejianError(ErrorCode.INPUT_INVALID, "修订读取位置无效")
        with self._uow_factory() as work:
            self._action(work, project_id, action_id)
            if material_id is not None:
                value = work.supplemental_materials.get(material_id)
                if value is None or (value["project_id"], value["action_id"]) != (project_id, action_id):
                    raise JiejianError(ErrorCode.RECORD_NOT_FOUND, "本动作材料不存在")
            items, has_more = work.supplemental_materials.list(project_id, action_id, material_id=material_id, limit=limit, before_revision=before_revision)
            return dict(project_id=project_id, action_id=action_id, items=items, limit=limit, has_more=has_more)
