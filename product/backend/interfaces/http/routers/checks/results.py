# 当前发布结果的只读故事、证据索引及完整文档；不触发修复、重算或目标请求。
from fastapi import APIRouter, Query
from typing import Annotated

from product.backend.interfaces.http.envelope import ApiResponse, data_response
from product.backend.bootstrap import ApplicationCore


def build_results_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/runs/{run_id}/repair-contracts",response_model=ApiResponse)
    def repair_contracts(run_id: str):
        return data_response([item.model_dump(mode="json") for item in context.check_repairs.contracts(run_id)])

    @router.get("/api/runs/{run_id}/result-story", response_model=ApiResponse)
    def get_result_story(run_id: str):
        return data_response(context.check_story.build(run_id).model_dump(mode="json"))

    @router.get("/api/runs/{run_id}/evidence", response_model=ApiResponse)
    def list_evidence(run_id: str):
        return data_response([item.model_dump(mode="json") for item in context.check_results.evidence_index(run_id)])

    @router.get('/api/runs/{run_id}/evidence-bundle', response_model=ApiResponse)
    def evidence_bundle(run_id: str, project_id: str, case_id: str, evidence_id: Annotated[list[str], Query(min_length=1,max_length=32)]):
        return data_response(context.check_results.evidence_bundle(project_id,run_id,case_id,evidence_id))

    @router.get("/api/runs/{run_id}/evidence/{evidence_id}", response_model=ApiResponse)
    def get_evidence(run_id: str, evidence_id: str):
        return data_response(context.check_results.evidence(run_id, evidence_id).model_dump(mode="json"))

    @router.get('/api/runs/{run_id}/evidence/{evidence_id}/records',response_model=ApiResponse)
    def evidence_records(run_id:str,evidence_id:str,case_id:str,project_id:str):
        return data_response(context.check_results.evidence_records(run_id,evidence_id,case_id,project_id=project_id).model_dump(mode='json'))

    @router.get('/api/runs/{run_id}/evidence/{evidence_id}/records/{record_id}',response_model=ApiResponse)
    def evidence_record(run_id:str,evidence_id:str,record_id:str,case_id:str,project_id:str):
        return data_response(context.check_results.evidence_records(run_id,evidence_id,case_id,project_id=project_id,record_id=record_id).model_dump(mode='json'))

    return router
