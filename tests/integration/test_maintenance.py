# 清理只能使用当前冻结计划，不将未登记文件或未知操作当作删除授权。
import pytest
from product.backend.domain.errors import JiejianError
from product.backend.infrastructure.maintenance.service import LocalMaintenanceService
from product.backend.infrastructure.runtime.generated_files import register_generated_file

def owned_cache(service):
    path=service.paths.assistant_cache/'cached-answer.json'
    path.write_text('{}',encoding='utf-8')
    assert register_generated_file(service.paths.root,path,'assistant-cache')
    return path

def test_unregistered_temporary_file_survives_a_plan(tmp_path):
    service=LocalMaintenanceService(tmp_path/'instance')
    file=service.paths.temp/'business-material.txt'
    file.write_text('retained material',encoding='utf-8')
    cache=owned_cache(service)
    plan=service.preview('clear-all')
    service.execute(plan['plan_id'])
    assert file.read_text('utf-8')=='retained material'
    assert not cache.exists()

def test_unknown_plan_cannot_delete_anything(tmp_path):
    service=LocalMaintenanceService(tmp_path/'instance')
    with pytest.raises(JiejianError):service.execute('unknown-plan')

def test_unknown_category_is_rejected(tmp_path):
    service=LocalMaintenanceService(tmp_path/'instance')
    with pytest.raises(JiejianError):service.preview('delete-everything')

def test_repeated_execution_returns_the_original_receipt(tmp_path):
    service=LocalMaintenanceService(tmp_path/'instance')
    owned_cache(service)
    plan=service.preview('clear-all')
    first=service.execute(plan['plan_id'])
    assert service.execute(plan['plan_id'])==first

def test_explicit_empty_selection_is_not_cleanup_authorization(tmp_path):
    service=LocalMaintenanceService(tmp_path/'instance')
    cache=owned_cache(service)
    plan=service.preview('clear-all')
    with pytest.raises(JiejianError):service.execute(plan['plan_id'],item_ids=[])
    assert cache.exists()
