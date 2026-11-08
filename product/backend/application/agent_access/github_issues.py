"""从已发布事实准备工单，通过协作操作的持久回执执行一次明确批准的发送。"""
from __future__ import annotations

from pydantic import Field, field_validator

from product.backend.application.agent_access.tasks import TaskInput
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.integrations.github import GitHubIssues
from product.backend.infrastructure.secrets.refs import credential_ref


class IssueSource(TaskInput):
    run_id: str = Field(pattern=r'^run_[0-9a-f]{32}$')
    case_id: str = Field(pattern=r'^case_[0-9a-f]{32}$')


class IssueDelivery(IssueSource):
    repository: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}$')
    credential_profile: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
    expected_draft_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')

    @field_validator('repository')
    @classmethod
    def repository_path(cls,value):
        if value.split('/')[1] in {'.','..'}:raise ValueError('repository must name a concrete GitHub repository')
        return value


class IssueCollaboration:
    def __init__(self, stories, secrets, *, projects=None, adapter=None):
        self.stories,self.secrets=stories,secrets
        self.projects=projects
        self.adapter=adapter or GitHubIssues()

    def draft(self, project, source):
        story=self.stories.build(source.run_id,project_id=project,include_repair=False)
        item=next((value for value in story.actions if value.case_id==source.case_id),None)
        if item is None:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND,'没有找到当前应用的准确检查事项')
        application=self.projects.get(project).name if self.projects is not None else '当前应用'
        title='跟进“'+item.display_name+'”的权限检查结果'
        description='\n\n'.join(['界鉴对“'+application+'”的“'+item.display_name+'”进行了检查。'+item.judgement.rstrip('。')+'。',
            '请按已确认的访问要求检查实现，并保留原问题和正常业务对照。修改后再次验证，修复情况由新的检查事实确认。',
            '这张工单用于协作跟进。关闭工单不会改变界鉴中的检查结论。'])
        body=description+'\n\n<details>\n<summary>原检查记录</summary>\n\n应用：'+project+'\n\n运行：'+source.run_id+'\n\n事项：'+source.case_id+'\n\n</details>'
        return dict(title=title[:200],body=body,description=description,draft_fingerprint=boundary_sha256(dict(title=title[:200],body=body)),run_id=source.run_id,case_id=source.case_id,
                    boundary='仅含公开摘要和准确引用；不包含会话、请求正文、源码正文或证据文件')

    @staticmethod
    def _marker(project, command, operation):
        fingerprint=boundary_sha256(dict(project_id=project,**command.model_dump()))
        return '<!-- jiejian:'+project+':'+operation+':'+fingerprint+' -->'

    def _token(self, profile):
        value=self.secrets.read(credential_ref('github',profile))
        if not value:
            raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE,'GitHub受控凭据尚未配置；未发送工单')
        return value

    def describe(self, project, command):
        draft=self._reviewed(project,command)
        return [dict(label='目标仓库',value=command.repository),dict(label='工单标题',value=draft['title']),
                dict(label='将发送的正文',value=draft['description']),
                dict(label='外部写入',value='仅创建这一张工单；结果未知时只查询原关联，不重新创建')]

    def _reviewed(self, project, command):
        draft=self.draft(project,command)
        if draft['draft_fingerprint']!=command.expected_draft_fingerprint:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'工单内容已变化，请重新核对将发送的准确正文')
        return draft

    def send(self, project, command, operation):
        draft=self._reviewed(project,command)
        return self.adapter.create(command.repository,self._token(command.credential_profile),draft['title'],draft['body'],
                                   self._marker(project,command,operation))

    def reconcile(self, project, operation):
        command=IssueDelivery.model_validate(operation['arguments'])
        self.draft(project,command)
        return self.adapter.reconcile(command.repository,self._token(command.credential_profile),
                                      self._marker(project,command,operation['operation_id']))
