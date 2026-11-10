"""应用环境的配置与选择，不发出目标请求，不把部署声明当作核验结果。"""
import time
from product.backend.application.onboarding.discovery import canonical_folder

from product.backend.domain.applications.models import ApplicationUnderstanding
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.lifecycle import ProjectStatus
from product.backend.infrastructure.storage import ProjectRecord
from product.protocols.web.environment import EnvironmentDocument, FrozenEnvironment


class ApplicationEnvironments:
    def __init__(self, uow_factory, *, control_origin=None, clock_us=None, impact_reader=None):
        self._uow, self._control = uow_factory, control_origin
        self._impact_reader = impact_reader
        self._clock = clock_us or (lambda: time.time_ns() // 1000)

    def create_application(self, *, operation_id, name):
        project_id = 'app_' + operation_id
        with self._uow() as work:
            work.acquire_write_lock()
            previous = work.projects.get(project_id)
            if previous is not None:
                if previous.name != name or previous.status is ProjectStatus.ARCHIVED:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '此创建操作已对应其他应用配置')
                return previous
            if not name.strip() or len(name) > 128:
                raise JiejianError(ErrorCode.INPUT_INVALID, '应用名称需为 1—128 个字符',
                    details={'field_errors':[{'field':'name','reason':'INVALID'}]}).not_accepted()
            now = self._clock()
            project = ProjectRecord(project_id=project_id, name=name, status=ProjectStatus.DRAFT,
                created_at_us=now, updated_at_us=now)
            work.projects.add(project)
            work.application_understanding.add(ApplicationUnderstanding(project_id=project_id,
                created_at_us=now, updated_at_us=now))
            work.commit()
            return project

    def context(self, project_id):
        with self._uow() as work:
            current = work.application_understanding.get(project_id)
            if current is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, '应用不存在')
            latest = work.environments.latest(project_id)
            return dict(project_id=project_id, revision=current.revision,
                active_environment=current.environment,
                confirmed_endpoint=current.confirmed_endpoint,endpoint_reachable=current.endpoint_reachable,
                endpoint_checked_at_us=current.endpoint_last_checked_at_us,
                environments=latest, source_available=current.source_root is not None)

    def attach_source(self, project_id, *, source_root, expected_revision):
        directory = str(canonical_folder(source_root))
        with self._uow() as work:
            work.acquire_write_lock()
            current = work.application_understanding.get(project_id)
            if current is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, '应用不存在')
            if current.source_root == directory:
                return current
            if current.source_root is not None or current.revision != expected_revision or work.jobs.active_for_project(project_id):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '应用已变化、已有关联源码或仍有活动任务')
            updated = ApplicationUnderstanding(**(current.model_dump() | dict(source_root=directory,
                revision=current.revision+1, updated_at_us=max(current.updated_at_us,self._clock()))))
            work.application_understanding.replace(updated)
            work.commit()
            return updated

    def save(self, project_id, configuration, *, expected_revision):
        if configuration.target.base_url == self._control:
            raise JiejianError(ErrorCode.SELF_TARGET_FORBIDDEN, '不能将界鉴控制面设为受检应用')
        with self._uow() as work:
            work.acquire_write_lock()
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, '应用不存在')
            previous = next(iter(work.environments.latest(project_id, configuration.environment_id)), None)
            if previous is not None and previous.configuration == configuration:
                return previous
            actual = 0 if previous is None else previous.configuration.revision
            if actual != expected_revision or configuration.revision != actual + 1:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '环境已变化，请读取当前修订')
            document = EnvironmentDocument(project_id=project_id, configuration=configuration, created_at_us=self._clock())
            work.environments.add(document)
            work.commit()
            return document

    def activation_preview(self, project_id, environment_id, *, revision):
        with self._uow() as work:
            return self._activation_preview(work, project_id, environment_id, revision)

    def _activation_preview(self, work, project_id, environment_id, revision):
        current = work.application_understanding.get(project_id)
        document = work.environments.revision(project_id, environment_id, revision)
        if current is None or document is None:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '应用或检查连接修订不存在')
        # 有效性说明来自准备所有者，未知时保留未知；本预览不创建任务或连接目标。
        materials = dict(state='UNKNOWN', items=None) if self._impact_reader is None else self._impact_reader(project_id, work)
        result = dict(project_id=project_id, expected_revision=current.revision,
            previous=None if current.environment is None else current.environment.model_dump(mode='json'), previous_endpoint=current.confirmed_endpoint,
            chosen=document.configuration.model_dump(mode='json'), changed=current.environment != document.configuration,
            materials=materials, retained=['已确认的权限要求', '已保存的来源与流程修订', '已有检查报告'],
            can_activate=not bool(work.jobs.active_for_project(project_id)))
        return result | dict(impact_fingerprint=boundary_sha256(result))

    def activate(self, project_id, environment_id, *, revision, expected_revision, impact_fingerprint=None):
        with self._uow() as work:
            work.acquire_write_lock()
            current = work.application_understanding.get(project_id)
            if current is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, '应用不存在')
            document = work.environments.revision(project_id, environment_id, revision)
            chosen = None if document is None else document.configuration
            if chosen is None:
                raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '环境修订不存在')
            if current.environment == chosen:
                return current
            if current.revision != expected_revision or work.jobs.active_for_project(project_id):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '应用已变化或仍有活动任务，请刷新后切换环境')
            if impact_fingerprint is not None:
                reviewed = self._activation_preview(work, project_id, environment_id, revision)
                if reviewed['impact_fingerprint'] != impact_fingerprint:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '连接或材料已变化，请重新查看切换影响').not_accepted()
            values = current.model_dump()
            values.update(environment=chosen, confirmed_endpoint=None, endpoint_source_fingerprint=None,
                endpoint_confirmed_at_us=None, endpoint_last_checked_at_us=None, endpoint_reachable=None,
                revision=current.revision + 1, updated_at_us=max(current.updated_at_us, self._clock()))
            updated = ApplicationUnderstanding(**values)
            work.application_understanding.replace(updated)
            work.commit()
            return updated
