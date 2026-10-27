# 一个基础场景验证真实准备、冻结提交、发布结果及两套主题的读取路径。
import pytest
from tests.support.browser_review import capture_workflow

pytestmark=[pytest.mark.runtime,pytest.mark.baseline]

def test_prepared_permissions_produce_a_readable_report(official,runtime_server,browser_page):
    result=official.check('BASELINE')
    assert result.preview['case_count']==5
    assert result.status['run']['lifecycle']=='COMPLETED'
    assert result.status['run']['verdict']=='PASS'
    assert result.status['result_integrity']=='VALID'
    assert result.story['project_id']==official.project_id
    assert result.story['verdict']=='PASS'
    capture_workflow(browser_page,runtime_server.origin,runtime_server.output,result.run_id)
