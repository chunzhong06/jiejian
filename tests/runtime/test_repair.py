# 复验场景独立建立基线，精确引用漏洞原题并核对修复及正常功能。
import pytest
from tests.support.browser_review import report_ready, capture_workflow

pytestmark=[pytest.mark.runtime,pytest.mark.repair]

def test_rule_problem_is_verified_against_its_original_check(official,runtime_server,browser_page):
    baseline=official.check('BASELINE')
    assert baseline.status['run']['verdict']=='PASS'
    change=official.load('VULNERABLE')
    problem=official.check('VULNERABLE',change)
    assert problem.status['run']['lifecycle']=='COMPLETED'
    assert problem.status['run']['verdict']=='BLOCK'
    assert any(item['breakpoint'] for item in problem.story['actions'])
    fixed_change=official.load('FIXED',repair=problem)
    fixed=official.check('FIXED',fixed_change)
    assert fixed.status['run']['lifecycle']=='COMPLETED'
    assert fixed.status['run']['verdict']=='PASS'
    assert fixed.status['result_integrity']=='VALID'
    assert fixed.story['repair_verification']['status']=='VERIFIED'
    browser_page.goto(runtime_server.origin+'/#/reports?run_id='+fixed.run_id,wait_until='domcontentloaded')
    report_ready(browser_page,evidence_label='查看本次依据')
    browser_page.screenshot(path=str(runtime_server.output/'repair-report.png'),full_page=True)
    capture_workflow(browser_page, runtime_server.origin, runtime_server.output, fixed.run_id,
        evidence_label='查看本次依据')
