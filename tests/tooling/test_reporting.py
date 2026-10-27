# 验证报告遇到短暂文件占用可完成原子发布，持续拒绝时保留旧报告和待发布内容。
import json
from importlib.util import module_from_spec, spec_from_file_location
from types import SimpleNamespace
import pytest
from scripts.quality import pytest_reporter


@pytest.mark.parametrize('persistent',[False,True])
def test_report_publication_handles_file_access_without_corrupting_previous_result(tmp_path,persistent):
    spec=spec_from_file_location('isolated_reporter',pytest_reporter.__file__)
    reporter=module_from_spec(spec)
    spec.loader.exec_module(reporter)
    blocked=True
    class PublicationPath(type(tmp_path)):
        def replace(self,target):
            nonlocal blocked
            if persistent or blocked:
                blocked=False
                raise PermissionError('file in use')
            return super().replace(target)
    destination=PublicationPath(tmp_path/'result.json')
    destination.write_text('{"status":"previous"}',encoding='utf-8')
    reporter.destination=destination
    reporter.state={'status':'current','cases':[]}
    reporter.time=SimpleNamespace(sleep=lambda _:None)
    if persistent:
        with pytest.raises(PermissionError):reporter.save()
        assert json.loads(destination.read_text('utf-8'))['status']=='previous'
        assert json.loads(destination.with_suffix('.tmp').read_text('utf-8'))['status']=='current'
    else:
        reporter.save()
        assert json.loads(destination.read_text('utf-8'))=={'status':'current','cases':[]}
        assert not destination.with_suffix('.tmp').exists()


def test_report_parameter_identifiers_do_not_expose_parameter_values():
    public=pytest_reporter.public_node('test_module.py::test_login[private-token]')
    assert public.startswith('test_module.py::test_login[')
    assert 'private-token' not in public
    assert public==pytest_reporter.public_node('test_module.py::test_login[private-token]')
    assert public!=pytest_reporter.public_node('test_module.py::test_login[other-token]')
