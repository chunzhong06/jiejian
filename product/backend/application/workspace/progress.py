# 从已有应用事实和持久操作投影接入能力及可继续任务，不探测目标或重放操作。
from urllib.parse import urlencode
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.errors import ErrorCode, JiejianError


class ApplicationProgress:
    def __init__(self, uow_factory, identity_preparations):
        self._uow, self._logins = uow_factory, identity_preparations

    @staticmethod
    def _project(work, project_id):
        project = work.projects.get(project_id)
        understanding = work.application_understanding.get(project_id)
        if project is None or understanding is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, '应用不存在')
        return understanding

    def readiness(self, project_id):
        # 汇总已有核验记录，不访问目标；AVAILABLE/CONFIGURED 不等于本次完整检查可执行。
        with self._uow() as work:
            understanding = self._project(work, project_id)
            sources = work.proof_sources.preparation_references(project_id)
            loaded = work.runtime_loads.latest(project_id)
            current_runtime = (loaded is not None and loaded.source_fingerprint == understanding.source_fingerprint
                and work.runtime_loads.receipt(loaded.load_id) is not None)
            facts = dict(project_id=project_id, revision=understanding.revision,
                source_fingerprint=understanding.source_fingerprint,
                endpoint=understanding.confirmed_endpoint,
                endpoint_checked_at_us=understanding.endpoint_last_checked_at_us,
                analysis_completed_at_us=understanding.analysis_completed_at_us)
            items = [
                dict(key='source', label='读取应用源码', state='READY' if understanding.analysis_completed_at_us else 'NEEDS_ACTION',
                    detail='已完成授权范围内的分析' if understanding.analysis_completed_at_us else '确认读取范围后分析源码', destination='/application'),
                dict(key='endpoint', label='连接运行中的应用', state='READY' if understanding.endpoint_reachable else 'NEEDS_ACTION',
                    detail='按上次地址核验记录' if understanding.endpoint_reachable else '确认运行地址后核验连接', destination='/application'),
                dict(key='runtime', label='受控运行与执行记录', state='AVAILABLE' if current_runtime else 'UNVERIFIED',
                    detail='已有对应源码的受控运行记录' if current_runtime else '完整执行证明目前支持受控本地 Node ESM 应用', destination='/application'),
                dict(key='proof', label='证明实际业务结果', state='CONFIGURED' if any(item['adoption_json'] for item in sources) else 'NEEDS_ACTION',
                    detail='已配置的来源仍须通过本次材料核验' if sources else '为业务结果配置来源并核对读取范围', destination='/preparation?proof_sources=1'),
            ]
            return dict(**facts, basis_fingerprint=boundary_sha256(facts), items=items)

    def activity(self, project_id):
        # 只投影可继续的位置，打开入口不会重新提交任务；清理缺口即使在 Job 终态后仍需保留。
        with self._uow() as work:
            understanding = self._project(work, project_id)
            items = []
            for job in work.jobs.active_for_project(project_id):
                phase = 'CANCELLING' if job.cancel_requested_at_us is not None else job.state.value
                if job.identity_preparation_id:
                    row = work.identity_preparations.get(job.identity_preparation_id)
                    value = self._logins._view(row, job)
                    label, destination, phase = '继续账号登录', '/preparation?identities=1&preparation_id=' + value.preparation_id, value.status.value
                elif job.run_id:
                    label, destination = '查看本次检查', '/reports?run_id=' + job.run_id
                elif job.recording_id:
                    recording = work.recordings.get(job.recording_id)
                    if recording is None:
                        raise JiejianError(ErrorCode.STORAGE_STATE, '录制任务关联不完整')
                    kind = {'TARGET':'execution','OBSERVATION':'evidence','RECOVERY':'recovery'}[recording.purpose.value]
                    label = '继续操作录制'
                    destination = '/preparation?' + urlencode(dict(action_id=recording.business_action_id,
                        material_kind=kind, member_id=recording.effect_id if kind=='evidence' else recording.resource_owner_test_identity_id,
                        recording_id=job.recording_id))
                elif job.runtime_load_id:
                    label, destination = '查看应用启动', '/application'
                else:
                    label, destination = '查看材料核对', '/preparation'
                items.append(dict(id=job.job_id, kind=job.operation_type, label=label, phase=phase,
                    destination=destination, updated_at_us=job.updated_at_us))
            for batch in work.preparation_batches.active(project_id):
                items.append(dict(id=batch['operation_id'], kind='PREPARATION_BATCH', label='继续材料准备',
                    phase=batch['state'], destination='/preparation', updated_at_us=batch['updated_at_us']))
            for row in work.identity_preparations.list(project_id=project_id):
                if row['phase'] == 'CLEANUP_REQUIRED' and not any(item['id'] == row['job_id'] for item in items):
                    items.append(dict(id=row['job_id'],kind='IDENTITY_PREPARATION',label='登录临时资源待清理',
                        phase='CLEANUP_REQUIRED',destination='/preparation?identities=1&preparation_id='+row['preparation_id'],updated_at_us=row['updated_at_us']))
            # 仅保留当前认证代次的中断入口；显式开始新登录或重置账号后，旧失败不再占据任务区。
            for identity in work.test_identities.list_for_project(project_id):
                generation, preparation_id = work.test_identities.preparation_owner(identity.identity_id)
                if preparation_id is None:
                    continue
                row = work.identity_preparations.get(preparation_id)
                if row['authentication_generation'] != generation:
                    continue
                value = self._logins._view(row, work.jobs.get(row['job_id']))
                if value.status.value == 'FAILED' and not value.cleanup_required:
                    items.append(dict(id=row['job_id'], kind='IDENTITY_PREPARATION', label='查看登录中断',
                        phase='FAILED', destination='/preparation?identities=1&preparation_id='+preparation_id,
                        updated_at_us=row['updated_at_us']))
            return dict(project_id=project_id, revision=understanding.revision, items=items[:32])
