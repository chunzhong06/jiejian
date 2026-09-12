# 解释入口只消费严格发布故事；模型禁用或越权输出不得改变确定性结论。
from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.workflows.assistant.current_surfaces import PreparationAssistantSurfaceResolver
from product.backend.workflows.assistant.service import AssistantService
from product.backend.workflows.assistant.templates import parse_assistant_result
from product.backend.workflows.checks.results import CheckResultReader
from product.backend.workflows.checks.story import CheckStoryBuilder
from tests.backend.infra.runtime.jobs.test_check_publication import package_parts, NOW


def resolver(parts):
    var_dir, factory, _, directory, _ = parts
    CheckPublisher(var_dir, factory, clock_us=lambda: NOW + 20).publish(directory)
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    story = CheckStoryBuilder(reader)
    surfaces = PreparationAssistantSurfaceResolver(business_boundaries=None, application_understanding=None,
        preparation=None, recording_lifecycle=None, uow_factory=factory, check_story=story)
    return surfaces, story


def test_disabled_result_assistant_reads_published_facts_without_model_or_cache_writes(package_parts, monkeypatch):
    surfaces, builder = resolver(package_parts)
    var_dir, _, job, _, _ = package_parts
    settings = SimpleNamespace(enabled=False, default_profile_name=None)
    profiles = SimpleNamespace(get_settings=lambda: settings)
    service = AssistantService(var_dir, surfaces=surfaces, llm_profiles=profiles)
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled explanation must not call provider or write cache")
    monkeypatch.setattr(service._cache, "write_success", forbidden)
    before = builder.build(job.run_id)
    view = service.get_result(job.run_id)
    assert view.status.value == "DISABLED"
    assert service.generate_result(job.run_id).status.value == "DISABLED"
    assert {entity.entity_id for entity in view.entities} == {item.case_id for item in before.actions}
    assert builder.build(job.run_id) == before


@pytest.mark.parametrize("field", ["verdict", "breakpoint_type", "location", "precision", "evidence", "repair_requirement"])
@pytest.mark.parametrize("nested", [False, True])
def test_current_result_explanation_rejects_structured_fact_rewrites(package_parts, field, nested):
    surfaces, builder = resolver(package_parts)
    job = package_parts[2]
    before = builder.build(job.run_id)
    value = surfaces.resolve_result(job.run_id).surface_input
    suggestion = dict(kind="EXPLANATION", entity_ids=[value.entities[0].entity_id], explanation="说明已有检查结果。")
    payload = dict(schema_version="1", template_id=value.template_id.value, template_version="1", suggestions=[suggestion])
    (suggestion if nested else payload)[field] = "replacement"
    with pytest.raises(JiejianError) as captured:
        parse_assistant_result(payload, surface_input=value)
    assert captured.value.code == ErrorCode.LLM_INVALID_RESPONSE.value
    assert builder.build(job.run_id) == before
