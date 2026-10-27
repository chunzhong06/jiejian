# 应用接入只登记受控来源，重复读取与接入不能重复创建项目。
import pytest
from product.backend.domain.errors import JiejianError

def test_connect_and_resume_share_the_same_project(core,source):
    first=core.application_understanding.connect(source,project_name='展馆')
    second=core.application_understanding.connect(source)
    assert first.project.project_id==second.project.project_id
    assert len(core.projects.list_for_display())==1
    assert core.application_understanding.get(first.project.project_id).source_root==str(source.resolve())

def test_missing_source_does_not_create_project(core,tmp_path):
    with pytest.raises(JiejianError):core.application_understanding.connect(tmp_path/'missing')
    assert core.projects.list_for_display()==[]

def test_fresh_connection_requires_explicit_operation_identity(core,source):
    with pytest.raises(JiejianError):core.application_understanding.connect(source,mode='NEW')
    assert core.projects.list_for_display()==[]

def test_archive_retains_project_identity_and_source_record(core,source):
    connected=core.application_understanding.connect(source)
    project_id=connected.project.project_id
    core.project_lifecycle.archive(project_id)
    assert core.projects.list_for_display()==[]
    assert core.projects.get(project_id).project_id==project_id
    assert core.application_understanding.get(project_id).source_root==str(source.resolve())
