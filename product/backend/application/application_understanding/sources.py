"""导入只形成可审阅请求与业务候选，采用场景和批准权限仍由原用例负责。"""
import hashlib
import time
from product.backend.application.application_understanding.imports import normalize_source
from product.backend.domain.applications.models import (ActionCandidate, ApplicationUnderstanding,
    CandidateConfidence, CandidateDecision, CandidateEvidence, candidate_id)
from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.codec import encode_json
from product.protocols.preparation.api_source import ApiSourceDocument, ApiImportDocument


class ApplicationSources:
    def __init__(self, uow_factory, *, clock_us=None):
        self._uow, self._clock = uow_factory, clock_us or (lambda: time.time_ns() // 1000)

    def context(self, project_id, source_id=None):
        with self._uow() as work:
            self._project(work, project_id)
            latest = work.api_sources.latest(project_id, source_id)
            return dict(project_id=project_id, sources=latest,
                annotations=tuple(item for item in work.api_sources.annotations(project_id)
                    if source_id is None or item['source_id'] == source_id),
                request_references=tuple(dict(source_id=source.source_id,revision=source.revision,item_id=item.item_id,
                    request_fingerprint=hashlib.sha256(encode_json(item.model_dump(mode='json'))).hexdigest())
                    for source in latest for item in source.requests))

    def revision(self, project_id, source_id, revision):
        with self._uow() as work:
            self._project(work,project_id)
            return work.api_sources.revision(project_id, source_id, revision)

    def preview(self, project_id, *, raw, kind, source_id=None):
        requests, warnings = normalize_source(raw, kind)
        digest = hashlib.sha256(encode_json(dict(kind=kind, requests=[item.model_dump(mode='json') for item in requests],
            warnings=warnings))).hexdigest()
        identity = 'imp_' + hashlib.sha256((project_id+digest).encode()).hexdigest()[:32]
        with self._uow() as work:
            work.acquire_write_lock()
            self._project(work, project_id)
            if work.api_sources.import_document(project_id, identity) is None:
                work.api_sources.add_import(ApiImportDocument(candidate_id=identity, project_id=project_id, kind=kind,
                    requests=requests, warnings=warnings, fingerprint=digest))
                work.commit()
        return self.preview_candidate(project_id, candidate_id=identity, source_id=source_id)

    def preview_candidate(self, project_id, *, candidate_id, source_id=None):
        with self._uow() as work:
            self._project(work, project_id)
            candidate = work.api_sources.import_document(project_id, candidate_id)
            if candidate is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '净化后的导入候选不存在')
            previous = next(iter(work.api_sources.latest(project_id, source_id)), None) if source_id is not None else None
        requests, warnings = candidate.requests, candidate.warnings
        before = {} if previous is None else {item.item_id:item for item in previous.requests}
        after = {item.item_id:item for item in requests}
        return dict(candidate_id=candidate_id, kind=candidate.kind, requests=requests, warnings=warnings, fingerprint=candidate.fingerprint,
            previous_revision=0 if previous is None else previous.revision,
            added=tuple(sorted(after.keys() - before.keys())), removed=tuple(sorted(before.keys() - after.keys())),
            changed=tuple(sorted(key for key in after.keys() & before.keys() if after[key] != before[key])))

    def accept(self, project_id, *, candidate_id, name, source_id, expected_revision, expected_fingerprint):
        preview = self.preview_candidate(project_id, candidate_id=candidate_id, source_id=source_id)
        kind = preview['kind']
        if preview['fingerprint'] != expected_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '导入内容已变化，请重新审阅')
        with self._uow() as work:
            work.acquire_write_lock()
            self._project(work, project_id)
            previous = next(iter(work.api_sources.latest(project_id, source_id)), None) if source_id is not None else None
            if previous is not None and previous.kind == kind and previous.name == name and previous.requests == preview['requests']:
                return previous
            if (0 if previous is None else previous.revision) != expected_revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '来源已更新，请重新查看差异')
            document = ApiSourceDocument(source_id=source_id, project_id=project_id, revision=expected_revision + 1,
                kind=kind, name=name, requests=preview['requests'], warnings=preview['warnings'], created_at_us=self._clock())
            work.api_sources.add(document)
            # 来源变化只使实现线索待复核，不改人工名称或正式权限规则。
            current = work.application_understanding.get(project_id)
            old = {} if previous is None else {item.pointer:item for item in previous.requests}
            new = {item.pointer:item for item in document.requests}
            actions = tuple(item.model_copy(update=dict(stale=True,
                decision=CandidateDecision.REVIEW_REQUIRED if item.decision is CandidateDecision.CONFIRMED else item.decision))
                if any(e.detector == 'API_SOURCE' and e.relative_path == f'api-sources/{source_id}'
                    and old.get(e.symbol) != new.get(e.symbol) for e in item.evidence) else item
                for item in current.action_candidates)
            if actions != current.action_candidates:
                work.application_understanding.replace(current.model_copy(update=dict(action_candidates=actions,
                    revision=current.revision+1,updated_at_us=max(current.updated_at_us,self._clock()))))
            work.commit()
            return document

    def annotate(self, project_id, source_id, item_id, *, label, action_id, expected_revision):
        with self._uow() as work:
            work.acquire_write_lock()
            self._request(work, project_id, source_id, item_id)
            if action_id is not None:
                action = work.business_boundaries.action(action_id)
                if action is None or action.project_id != project_id:
                    raise JiejianError(ErrorCode.INPUT_INVALID, '只能关联本应用的业务动作')
            previous = next((item for item in work.api_sources.annotations(project_id)
                if (item['source_id'], item['item_id']) == (source_id, item_id)), None)
            if previous is not None and (previous['label'], previous['action_id']) == (label, action_id):
                return previous
            if (0 if previous is None else previous['revision']) != expected_revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '人工说明已变化，请重新读取')
            result = dict(source_id=source_id, item_id=item_id, label=label, action_id=action_id,
                revision=expected_revision + 1)
            work.api_sources.annotate(project_id, source_id, item_id, result)
            work.commit()
            return result

    def propose_action(self, project_id, source_id, item_id, *, expected_revision):
        with self._uow() as work:
            work.acquire_write_lock()
            source, request = self._request(work, project_id, source_id, item_id)
            current = work.application_understanding.get(project_id)
            key = request.method + ' ' + request.path
            if len(key) > 256:
                raise JiejianError(ErrorCode.INPUT_INVALID, '此路径过长，请先整理为可维护的资源参数模板')
            identity = candidate_id('action', key)
            previous = next((item for item in current.action_candidates if item.candidate_id == identity), None)
            evidence = CandidateEvidence(relative_path=f'api-sources/{source_id}', line_start=1, line_end=1,
                detector='API_SOURCE', symbol=request.pointer,
                content_sha256=hashlib.sha256(encode_json(request.model_dump(mode='json'))).hexdigest())
            if previous is not None and evidence in previous.evidence and not previous.stale:
                return current
            if current.revision != expected_revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '应用已变化，请重新读取')
            candidate = (previous.model_copy(update=dict(evidence=tuple(e for e in previous.evidence
                if e.relative_path != evidence.relative_path) + (evidence,), stale=False)) if previous else
                ActionCandidate(candidate_id=identity, canonical_key=key, display_name=request.label,
                    confidence=CandidateConfidence.MEDIUM, evidence=(evidence,)))
            actions=tuple(candidate if item.candidate_id == identity else item for item in current.action_candidates)
            if previous is None:
                actions=(*actions,candidate)
            updated = ApplicationUnderstanding(**(current.model_dump() | dict(action_candidates=actions,
                revision=current.revision + 1, updated_at_us=max(current.updated_at_us, self._clock()))))
            work.application_understanding.replace(updated)
            work.commit()
            return updated

    @staticmethod
    def _project(work, project_id):
        if work.projects.get(project_id) is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, '应用不存在')

    def _request(self, work, project_id, source_id, item_id):
        self._project(work, project_id)
        source = next(iter(work.api_sources.latest(project_id, source_id)), None) if source_id is not None else None
        request = None if source is None else next((item for item in source.requests if item.item_id == item_id), None)
        if request is None:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '当前来源中没有此请求')
        return source, request
