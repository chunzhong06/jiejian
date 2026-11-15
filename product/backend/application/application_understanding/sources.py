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

    def summary(self, project_id):
        """概览只返回数量；来源仍由严格 reader 接受，不计算无消费者的逐请求引用。"""
        with self._uow() as work:
            self._project(work, project_id)
            sources = work.api_sources.latest(project_id)
            return dict(project_id=project_id, source_count=len(sources),
                request_count=sum(len(source.requests) for source in sources))

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

    def annotate(self, project_id, source_id, item_id, *, label, action_id, expected_revision, expected_source_revision=None):
        with self._uow() as work:
            work.acquire_write_lock()
            source, request = self._request(work, project_id, source_id, item_id)
            if expected_source_revision is not None and source.revision != expected_source_revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '接口来源已变化，请重新核对这条请求')
            if action_id is not None:
                action = work.business_boundaries.action(action_id)
                if action is None or action.project_id != project_id:
                    raise JiejianError(ErrorCode.INPUT_INVALID, '只能关联本应用的业务动作')
            previous = next((item for item in work.api_sources.annotations(project_id)
                if (item['source_id'], item['item_id']) == (source_id, item_id)), None)
            current = work.application_understanding.get(project_id)
            updated = self._source_candidate(current, source, request, decision=CandidateDecision.CONFIRMED) if action_id is not None else current
            if previous is not None and (previous['label'], previous['action_id']) == (label, action_id) and updated == current:
                return previous
            if (0 if previous is None else previous['revision']) != expected_revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '人工说明已变化，请重新读取')
            result = dict(source_id=source_id, item_id=item_id, label=label, action_id=action_id,
                revision=expected_revision + 1)
            work.api_sources.annotate(project_id, source_id, item_id, result)
            if updated != current:
                work.application_understanding.replace(updated)
            work.commit()
            return result

    def propose_action(self, project_id, source_id, item_id, *, expected_revision, decision=None, expected_source_revision=None):
        """普通候选入口及本机明确排除共用事务；不创建权限或替代提案批准。"""
        with self._uow() as work:
            work.acquire_write_lock()
            source, request = self._request(work, project_id, source_id, item_id)
            current = work.application_understanding.get(project_id)
            if expected_source_revision is not None and source.revision != expected_source_revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '接口来源已变化，核对决定尚未保存')
            if decision == 'REJECTED':
                identity = candidate_id('action', request.method+' '+request.path)
                linked = any(identity in binding.action_candidate_ids for root in work.business_boundaries.list_actions(project_id)
                    if (binding := work.business_boundaries.action_binding(root.action_id,root.current_revision)) is not None)
                annotation = next((item for item in work.api_sources.annotations(project_id)
                    if (item['source_id'],item['item_id']) == (source_id,item_id)), None)
                if linked or annotation is not None and annotation['action_id'] is not None:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '这条线索仍关联正式业务操作，请先在原规则与业务关联中核对，不能以排除线索代替变更要求')
            updated = self._source_candidate(current, source, request,
                decision=None if decision is None else CandidateDecision(decision))
            if updated == current:
                return current
            if current.revision != expected_revision:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '应用已变化，请重新读取')
            work.application_understanding.replace(updated)
            work.commit()
            return updated

    def _source_candidate(self, current, source, request, *, decision=None):
        key = request.method + ' ' + request.path
        if len(key) > 256 and decision is None:
            raise JiejianError(ErrorCode.INPUT_INVALID, '此路径过长，请先整理为可维护的资源参数模板')
        identity = candidate_id('action', key)
        previous = next((item for item in current.action_candidates if item.candidate_id == identity), None)
        evidence = CandidateEvidence(relative_path=f'api-sources/{source.source_id}', line_start=1, line_end=1,
            detector='API_SOURCE', symbol=request.pointer,
            content_sha256=hashlib.sha256(encode_json(request.model_dump(mode='json'))).hexdigest())
        same = previous is not None and evidence in previous.evidence and not previous.stale
        if same and (decision is None or previous.decision == decision):
            return current
        # 新内容不能继承旧排除；明确重新关联或排除才记录本次决定。
        selected = decision if decision is not None else (previous.decision if same else CandidateDecision.PROPOSED)
        candidate = (ActionCandidate(**(previous.model_dump() | dict(evidence=tuple(e for e in previous.evidence
            if (e.relative_path,e.symbol) != (evidence.relative_path,evidence.symbol)) + (evidence,),
            stale=False, decision=selected))) if previous else ActionCandidate(candidate_id=identity,
            canonical_key=key if len(key)<=256 else 'api-source:'+identity, display_name=request.label, confidence=CandidateConfidence.MEDIUM,
            evidence=(evidence,), decision=selected))
        actions = tuple(candidate if item.candidate_id == identity else item for item in current.action_candidates)
        if previous is None:
            actions = (*actions,candidate)
        return ApplicationUnderstanding(**(current.model_dump() | dict(action_candidates=actions,
            revision=current.revision+1, updated_at_us=max(current.updated_at_us,self._clock()))))

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
