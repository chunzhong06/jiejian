# 验证普通 API 经真实 CHECK Worker/Runner 发布结果，历史与证据读取只消费同一发布事实。
from pathlib import Path
import time
import pytest

from tests.fixtures.secrets import InMemorySecretStore
from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.runtime_environment import runtime_identity_environment

pytestmark = [pytest.mark.e2e, pytest.mark.database, pytest.mark.process, pytest.mark.slow]


def test_api_worker_runner_publication_reaches_current_story_and_history(tmp_path):
    root = Path(__file__).resolve().parents[2]
    var_dir = tmp_path / 'var'
    app = create_app(var_dir, start_worker=True, official_sample_root=root / 'samples/web/collaboration_space',
        secret_store=InMemorySecretStore(), environ=runtime_identity_environment(var_dir))
    with TestClient(app) as client:
        started = client.post('/api/experience/official-sample/start', json={'schema_version':'1', 'consent':True})
        assert started.status_code == 200, started.text
        assert started.json()['data']['scenario_version'] == 'BASELINE'
        project = started.json()['data']['project_id']
        proposal_response = client.post('/api/experience/official-sample/boundary-proposal')
        assert proposal_response.status_code == 200, proposal_response.text
        proposal = proposal_response.json()['data']['proposal']
        approved = client.post(f"/api/projects/{project}/business-boundaries/proposals/{proposal['proposal_id']}/approve",
            json={'schema_version':'1', 'expected_fingerprint':proposal['proposal_fingerprint'], 'reason':'确认受控示例的业务规则'})
        assert approved.status_code == 200, approved.text
        prepared = client.post('/api/experience/official-sample/prepare')
        assert prepared.status_code == 200 and prepared.json()['data']['scenario_prepared'], prepared.text
        preview = client.get(f'/api/projects/{project}/check-preview').json()['data']
        assert preview['can_execute'] is True and preview['case_count'] == 3
        submitted = client.post(f'/api/projects/{project}/runs', json={'schema_version':'2',
            'expected_plan_fingerprint':preview['plan_fingerprint'], 'idempotency_key':'api-worker-publication'})
        assert submitted.status_code == 202, submitted.text
        run_id = submitted.json()['data']['run']['run_id']
        deadline = time.monotonic() + 90
        while True:
            response = client.get(f'/api/runs/{run_id}')
            assert response.status_code == 200
            status = response.json()['data']
            if status['run']['lifecycle'] not in {'QUEUED','RUNNING'}:
                break
            assert time.monotonic() < deadline, {'run':status['run'], 'job':status['job'], 'integrity':status['result_integrity']}
            time.sleep(0.1)
        assert status['run']['lifecycle'] == 'COMPLETED', status
        assert status['result_integrity'] == 'VALID' and status['run']['verdict'] == 'PASS'
        story = client.get(f'/api/runs/{run_id}/result-story').json()['data']
        assert story['run_id'] == run_id and story['verdict'] == 'PASS'
        deny = [item for item in story['actions'] if item['permission']['expectation'] == 'DENY']
        # 起始同步实现先授权；异步优化后的 AUTHORIZATION_LATE 由完整开发演练另行验证。
        assert len(deny) == 1 and deny[0]['repair_requirement'] is None
        assert len(story['actions']) == 3
        for item in story['actions']:
            expected = 'ABSENT' if item['permission']['expectation'] == 'DENY' else 'CONFIRMED'
            effects = item['fact_comparison']['effects']
            assert effects and all(effect['observed_state'] == expected for effect in effects)
        index = client.get(f'/api/runs/{run_id}/evidence').json()['data']
        refs = {item['evidence_id'] for item in index}
        assert refs
        for item in story['actions']:
            for source in item['evidence_explanations']:
                assert set(source['evidence_refs']).issubset(refs)
        for ref in refs:
            evidence = client.get(f'/api/runs/{run_id}/evidence/{ref}')
            assert evidence.status_code == 200 and evidence.json()['data']['run_id'] == run_id
        history = client.get(f'/api/projects/{project}/check-history').json()['data']
        assert [item['status']['run']['run_id'] for item in history['items']] == [run_id]
        assert client.get(f'/api/runs/{run_id}/result-story').json()['data'] == story
