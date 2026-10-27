# 验证跨仓储事务没有提交时不会发布业务变化。
import pytest

def test_uncommitted_transaction_does_not_publish_changes(core,source):
    connection=core.application_understanding.connect(source)
    project_id=connection.project.project_id
    with core.uow_factory() as work:
        project=work.projects.get(project_id)
        work.projects.replace(type(project)(**{**project.model_dump(),'name':'未提交的名称'}))
    assert core.projects.get(project_id).name!='未提交的名称'

pytestmark=[pytest.mark.level3]
