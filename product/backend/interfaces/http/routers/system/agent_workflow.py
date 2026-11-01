# 本机决定与机器建议使用不同入口；控制面会话由应用中间件核对。
from typing import Literal
from fastapi import APIRouter
from product.backend.interfaces.http.envelope import ApiResponse, data_response
from product.backend.application.agent_access.tasks import (
    TaskInput, CreateCollaboration, CollaborationAction, CollaborationQuestion, CollaborationFollowup,
)
from pydantic import Field
from product.backend.application.agent_access.execution import StartAgent


class TaskDecision(TaskInput):
    accept: bool


class TaskAnswer(TaskInput):
    answer: str = Field(min_length=1, max_length=2000)


class TaskControl(TaskInput):
    action: Literal['pause', 'resume', 'cancel', 'finish']


def build_agent_workflow_router(context):
    router = APIRouter()

    @router.get('/api/collaboration/executor', response_model=ApiResponse)
    def executor(project_id: str | None = None):
        return data_response(context.agent_execution.capabilities(project_id))

    @router.post('/api/projects/{project_id}/collaboration/{task_id}/execute', response_model=ApiResponse)
    def execute(project_id: str, task_id: str, body: StartAgent):
        return data_response(context.agent_execution.start(project_id, task_id, body))

    @router.get('/api/projects/{project_id}/collaboration', response_model=ApiResponse)
    def tasks(project_id: str):
        return data_response(context.collaboration.list(project_id))

    @router.get('/api/projects/{project_id}/collaboration-active', response_model=ApiResponse)
    def current_task(project_id: str):
        return data_response(context.collaboration.current(project_id))

    @router.post('/api/projects/{project_id}/collaboration', response_model=ApiResponse)
    def create(project_id: str, body: CreateCollaboration):
        return data_response(context.collaboration.create(project_id, body))

    @router.post('/api/projects/{project_id}/collaboration-followup', response_model=ApiResponse)
    def followup(project_id: str, body: CollaborationFollowup):
        return data_response(context.collaboration.followup(project_id, body))

    @router.get('/api/projects/{project_id}/collaboration/{task_id}', response_model=ApiResponse)
    def task(project_id: str, task_id: str):
        return data_response(context.collaboration.show(project_id, task_id))

    @router.get('/api/projects/{project_id}/collaboration/{task_id}/context', response_model=ApiResponse)
    def task_context(project_id: str, task_id: str):
        return data_response(context.collaboration.context(project_id, task_id))

    @router.get('/api/projects/{project_id}/collaboration/{task_id}/activity', response_model=ApiResponse)
    def task_activity(project_id: str, task_id: str):
        return data_response(context.collaboration.activity(project_id, task_id))

    @router.post('/api/projects/{project_id}/collaboration/{task_id}/actions', response_model=ApiResponse)
    def act(project_id: str, task_id: str, body: CollaborationAction):
        return data_response(context.collaboration.act(project_id, task_id, body, actor='USER'))

    @router.post('/api/projects/{project_id}/collaboration/{task_id}/actions/{operation_id}/decision', response_model=ApiResponse)
    def decide(project_id: str, task_id: str, operation_id: str, body: TaskDecision):
        return data_response(context.collaboration.decide(project_id, task_id, operation_id, body.accept))

    @router.post('/api/projects/{project_id}/collaboration/{task_id}/actions/{operation_id}/reconcile', response_model=ApiResponse)
    def reconcile(project_id: str, task_id: str, operation_id: str):
        return data_response(context.collaboration.reconcile(project_id, task_id, operation_id))

    @router.post('/api/projects/{project_id}/collaboration/{task_id}/questions', response_model=ApiResponse)
    def ask(project_id: str, task_id: str, body: CollaborationQuestion):
        return data_response(context.collaboration.ask(project_id, task_id, body))

    @router.post('/api/projects/{project_id}/collaboration/{task_id}/questions/{question_id}', response_model=ApiResponse)
    def answer(project_id: str, task_id: str, question_id: str, body: TaskAnswer):
        return data_response(context.collaboration.answer(project_id, task_id, question_id, body.answer))

    @router.post('/api/projects/{project_id}/collaboration/{task_id}/control', response_model=ApiResponse)
    def control(project_id: str, task_id: str, body: TaskControl):
        result = context.collaboration.control(project_id, task_id, body.action)
        return data_response(result)

    @router.get('/api/projects/{project_id}/agent-context', response_model=ApiResponse)
    def read(project_id: str, stage: Literal['RULES','MATERIALS','RECORDING','RESULTS','REPAIR']='RULES',
             recording_id: str|None=None, run_id: str|None=None, case_id: str|None=None):
        return data_response(context.agent_workflow.read(project_id,stage,recording_id=recording_id,run_id=run_id,case_id=case_id))

    return router
