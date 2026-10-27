# 保护只读结果、精确证据引用、显式ORM登记与产品依赖方向。
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from product.backend.interfaces.http.routers.checks.results import build_results_router
from product.backend.infrastructure.storage.orm_registry import load_storage_orm_mappings, _STORAGE_ORM_MODULES
from product.backend.infrastructure.storage.base import Base

ROOT=Path(__file__).resolve().parents[2]


def test_result_routes_are_read_only_and_forward_the_exact_evidence_context():
    read=Mock(return_value={'evidence':[]})
    router=build_results_router(SimpleNamespace(check_results=SimpleNamespace(evidence_bundle=read)))
    assert router.routes and all(route.methods=={'GET'} for route in router.routes)
    endpoint=next(route.endpoint for route in router.routes if route.path.endswith('/evidence-bundle'))
    endpoint(run_id='original-run',project_id='original-project',case_id='original-case',evidence_id=['original-evidence'])
    read.assert_called_once_with('original-project','original-run','original-case',['original-evidence'])


def test_result_readers_do_not_write_facts_or_execute_target_adapters():
    forbidden={'httpx','requests','playwright','subprocess','product.backend.infrastructure.execution'}
    for relative in ['product/backend/application/checks/reading','product/backend/application/projects/repair.py']:
        owner=ROOT/relative
        for path in owner.rglob('*.py') if owner.is_dir() else [owner]:
            for node in ast.walk(ast.parse(path.read_text('utf-8-sig'))):
                imports=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                assert not [name for name in imports if any(name==item or name.startswith(item+'.') for item in forbidden)],path
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                    assert node.func.attr not in {'commit','publish','submit','execute_target','start_recording'},path


def test_storage_registration_covers_all_declared_tables_and_is_repeatable():
    modules=set()
    tables=set()
    for path in (ROOT/'product/backend/infrastructure/storage').rglob('*.py'):
        for node in ast.parse(path.read_text('utf-8-sig')).body:
            if not isinstance(node,ast.ClassDef):continue
            for statement in node.body:
                if isinstance(statement,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='__tablename__' for target in statement.targets):
                    modules.add('.'.join(path.relative_to(ROOT).with_suffix('').parts))
                    tables.add(ast.literal_eval(statement.value))
    assert modules==set(_STORAGE_ORM_MODULES)
    load_storage_orm_mappings()
    first=dict(Base.metadata.tables)
    load_storage_orm_mappings()
    assert tables==set(first)==set(Base.metadata.tables)
    assert all(Base.metadata.tables[name] is table for name,table in first.items())


def test_storage_public_exports_resolve_to_existing_objects():
    from product.backend.infrastructure import storage
    assert storage.__all__
    assert all(hasattr(storage, name) for name in storage.__all__)


def test_product_does_not_depend_on_test_or_sample_implementations():
    for root in ['product/backend','product/protocols']:
        for path in (ROOT/root).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text('utf-8-sig'))):
                imports=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                assert not [name for name in imports if name.split('.')[0] in {'tests','samples'}],path


pytestmark=[pytest.mark.level1]
