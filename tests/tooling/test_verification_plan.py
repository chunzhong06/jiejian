# 验证计划按契约选择、去重、默认不执行，并在失败后停止后续集合。
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from scripts.quality.catalog import AREAS, plan
from scripts.quality.run import main

ROOT=Path(__file__).resolve().parents[2]

def test_related_areas_merge_without_duplicate_reads_or_runtime():
    commands=plan(['preparation','navigation','preparation'])
    assert commands==plan(['preparation','navigation'])
    backend=[command for command in commands if command[0]=='test']
    frontend=[command for command in commands if command[0]=='frontend-test']
    assert backend and frontend
    assert all(len(command[1:])==len(set(command[1:])) for command in backend+frontend)
    assert any(path in command for command in frontend for path in AREAS['navigation'].frontend)
    assert all(item[0]!='sample-test' for item in commands)

def test_repair_already_includes_baseline():
    assert plan(['journey','repair'])==(('sample-test','official','repair'),)

def test_catalog_selectors_point_to_actual_tests():
    for area in AREAS.values():
        for path in area.backend:assert (ROOT/path).is_file(),path
        for path in area.frontend:assert (ROOT/'product/frontend'/path).is_file(),path
        for path in area.source:assert (ROOT/path).exists(),path

def test_levels_do_not_silently_run_integration_or_runtime():
    assert all(step[0] not in {'test','sample-test'} for step in plan(['access','journey'],level=1))
    assert ('frontend-test','--types-only') in plan(['navigation'],level=1)
    assert any(step[0]=='test' for step in plan(['access'],level=3))

def test_plan_and_listing_never_execute_a_command(monkeypatch,capsys):
    execute=Mock()
    monkeypatch.setattr('scripts.quality.run.subprocess.run',execute)
    assert main([])==0
    assert main(['--area','preparation'])==0
    assert main(['--all','--plan'])==0
    assert '尚未执行' in capsys.readouterr().out
    execute.assert_not_called()

def test_execution_requires_an_explicit_range(monkeypatch):
    execute=Mock()
    monkeypatch.setattr('scripts.quality.run.subprocess.run',execute)
    with pytest.raises(SystemExit) as failure:main(['--run'])
    assert failure.value.code==2
    execute.assert_not_called()

def test_failure_stops_the_next_suite(monkeypatch):
    execute=Mock(return_value=SimpleNamespace(returncode=7))
    monkeypatch.setattr('scripts.quality.run.subprocess.run',execute)
    assert main(['--area','preparation','--run'])==7
    assert execute.call_count==1
    assert 'scripts.quality.syntax' in execute.call_args.args[0]


def test_catalog_owns_all_test_files_and_never_implicitly_enables_real_processes():
    backend={path for area in AREAS.values() for path in area.backend}
    actual={path.relative_to(ROOT).as_posix() for path in (ROOT/'tests').rglob('test_*.py') if 'runtime' not in path.relative_to(ROOT/'tests').parts[:1]}
    assert actual<=backend,sorted(actual-backend)
    frontend={path for area in AREAS.values() for path in area.frontend}
    expected={path.relative_to(ROOT/'product/frontend').as_posix() for path in (ROOT/'product/frontend/src').rglob('*') if path.is_file() and '.test.' in path.name}
    assert expected<=frontend,sorted(expected-frontend)
    for suite in plan([name for name,area in AREAS.items() if not area.journey]):
        assert '--run-level4' not in suite
        if suite[0]=='test':assert 'not level4' in suite[suite.index('-m')+1]
