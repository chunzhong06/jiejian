"""环境与接口来源的控制面适配；导入不执行目标请求或外部脚本。"""
from typing import Literal
from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool
from product.backend.interfaces.http.body import read_bounded_body
from pydantic import Field, ValidationError
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.interfaces.http.envelope import ApiModel, ApiResponse, data_response
from product.protocols.web.environment import FrozenEnvironment


class CreateApplication(ApiModel):
    operation_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    name: str = Field(min_length=1, max_length=128)


class SaveEnvironment(ApiModel):
    configuration: FrozenEnvironment
    expected_revision: int = Field(ge=0)


class AttachSource(ApiModel):
    source_root: str = Field(min_length=1, max_length=32768)
    expected_revision: int = Field(ge=0)


class ActivateEnvironment(ApiModel):
    revision: int = Field(ge=1)
    expected_revision: int = Field(ge=0)


class ImportPreview(ApiModel):
    kind: Literal['OPENAPI', 'HAR', 'POSTMAN']
    raw: str = Field(min_length=2, max_length=4_194_304, repr=False)
    source_id: str | None = Field(default=None, pattern=r'^src_[0-9a-f]{32}$')


class ImportAccept(ApiModel):
    candidate_id: str = Field(pattern=r'^imp_[0-9a-f]{32}$')
    source_id: str = Field(pattern=r'^src_[0-9a-f]{32}$')
    name: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=0)
    expected_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')


class SourceAnnotation(ApiModel):
    label: str = Field(min_length=1, max_length=256)
    action_id: str | None = Field(default=None, pattern=r'^bac_[0-9a-f]{32}$')
    expected_revision: int = Field(ge=0)


class SourceProposal(ApiModel):
    expected_revision: int = Field(ge=0)


def build_workbench_router(context):
    router = APIRouter()

    @router.post('/api/applications', response_model=ApiResponse)
    def create_application(body: CreateApplication):
        return data_response(context.application_environments.create_application(**body.model_dump()), status_code=201)

    @router.get('/api/projects/{project_id}/environments', response_model=ApiResponse)
    def environments(project_id: str):
        return data_response(context.application_environments.context(project_id))

    @router.put('/api/projects/{project_id}/source-directory', response_model=ApiResponse)
    def attach_source(project_id: str, body: AttachSource):
        return data_response(context.application_environments.attach_source(project_id, **body.model_dump()))

    @router.post('/api/projects/{project_id}/environments', response_model=ApiResponse)
    async def save_environment(project_id: str, request: Request):
        # 在 HTTP 边界使用 JSON 模式，保留严格协议中数组到元组的解析契约。
        raw = await read_bounded_body(request, limit=32768, message='环境配置过大')
        try:
            body = SaveEnvironment.model_validate_json(raw)
        except ValidationError:
            raise JiejianError(ErrorCode.INPUT_INVALID, '环境配置格式不正确') from None
        return data_response(await run_in_threadpool(context.application_environments.save, project_id, body.configuration, expected_revision=body.expected_revision))

    @router.post('/api/projects/{project_id}/environments/{environment_id}/activate', response_model=ApiResponse)
    def activate_environment(project_id: str, environment_id: str, body: ActivateEnvironment):
        return data_response(context.application_environments.activate(project_id, environment_id, **body.model_dump()))

    @router.get('/api/projects/{project_id}/api-sources', response_model=ApiResponse)
    def sources(project_id: str, source_id: str | None = Query(default=None, pattern=r'^src_[0-9a-f]{32}$')):
        return data_response(context.application_sources.context(project_id, source_id))

    @router.get('/api/projects/{project_id}/api-sources/summary', response_model=ApiResponse)
    def source_summary(project_id: str):
        return data_response(context.application_sources.summary(project_id))

    @router.post('/api/projects/{project_id}/api-sources/preview', response_model=ApiResponse)
    def preview_source(project_id: str, body: ImportPreview):
        return data_response(context.application_sources.preview(project_id, **body.model_dump()))

    @router.get('/api/projects/{project_id}/api-sources/{source_id}/revisions/{revision}',response_model=ApiResponse)
    def source_revision(project_id:str,source_id:str,revision:int):
        return data_response(context.application_sources.revision(project_id,source_id,revision))

    @router.post('/api/projects/{project_id}/api-sources/accept', response_model=ApiResponse)
    def accept_source(project_id: str, body: ImportAccept):
        return data_response(context.application_sources.accept(project_id, **body.model_dump()))

    @router.put('/api/projects/{project_id}/api-sources/{source_id}/requests/{item_id}', response_model=ApiResponse)
    def annotate_source(project_id: str, source_id: str, item_id: str, body: SourceAnnotation):
        return data_response(context.application_sources.annotate(project_id, source_id, item_id, **body.model_dump()))

    @router.post('/api/projects/{project_id}/api-sources/{source_id}/requests/{item_id}/candidate', response_model=ApiResponse)
    def source_candidate(project_id: str, source_id: str, item_id: str, body: SourceProposal):
        return data_response(context.application_sources.propose_action(project_id, source_id, item_id, **body.model_dump()))

    return router
