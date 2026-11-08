import time

from pydantic import BaseModel, ConfigDict, Field

from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.checks.selection import permission_key, resolve_selected_permissions
from product.backend.domain.errors import ErrorCode, JiejianError
from product.protocols.checks.execution_request import PermissionReference


class SaveCheckRoutine(BaseModel):
    """跨界接受规则选择；保存动作不提交检查，也不携带可复用的就绪状态。"""
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    name: str = Field(default='常用检查', min_length=1, max_length=80)
    selected_permissions: list[PermissionReference] | None = Field(default=None, min_length=1, max_length=4096)


class CheckRoutines:
    """承接旧保存范围并拥有完整方案修订；就绪与结论仍由原检查服务计算。"""
    def __init__(self, uow_factory, boundaries, checks):
        self.uow, self.boundaries = uow_factory, boundaries
        from product.backend.application.checks.routine_execution import RoutineExecution
        self.revisions = RoutineExecution(uow_factory, boundaries, checks)

    def list(self, project):
        boundary = self.boundaries.view(project)
        current = {permission_key(item) for item in boundary.permission_intents if item.effective_state.value == 'ACTIVE'}
        with self.uow() as work:
            values = work.check_routines.list(project)
        result = []
        for value in values:
            selected = value['selected_permissions']
            stale = [] if selected is None else [item['intent_id'] for item in selected
                if (item['intent_id'], item['revision'], item['intent_hash']) not in current]
            result.append({key:item for key,item in value.items() if key!='request_fingerprint'} | dict(
                current=not stale, stale_intents=stale, mode='ALL' if selected is None else 'SELECTED'))
        return result

    def save(self, project, command):
        routine = 'csp_'+command.operation_id
        fingerprint = boundary_sha256(command.model_dump(mode='json'))
        with self.uow() as work:
            work.acquire_write_lock()
            existing = next((item for item in work.check_routines.list(project) if item['routine_id']==routine), None)
            if existing:
                # 回执先于当前规则校验：原保存已经成功时，规则后续变化不能抹掉该事实。
                if existing['request_fingerprint'] != fingerprint:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '原保存请求已用于其他检查范围')
                return {key:value for key,value in existing.items() if key!='request_fingerprint'}
            boundary = self.boundaries.view(project, work=work)
            if command.selected_permissions is not None:
                resolve_selected_permissions(boundary.permission_intents, command.selected_permissions)
            value = dict(schema_version='1', routine_id=routine, project_id=project, name=command.name,
                selected_permissions=None if command.selected_permissions is None else [item.model_dump(mode='json') for item in command.selected_permissions],
                created_at_us=time.time_ns()//1000, request_fingerprint=fingerprint)
            work.check_routines.save(value)
            work.commit()
        return {key:item for key,item in value.items() if key!='request_fingerprint'}

    def delete(self, project, routine):
        with self.uow() as work:
            work.acquire_write_lock()
            if work.routine_revisions.latest(project, routine) is not None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '完整检查方案保留不可变修订，不能按旧范围删除')
            work.check_routines.delete(project, routine)
            work.commit()
