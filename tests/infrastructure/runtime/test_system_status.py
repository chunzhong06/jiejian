from pathlib import Path

import pytest

from product.backend.infrastructure.runtime import system_status


def test_summary_does_not_run_deep_probes(monkeypatch, tmp_path):
    browser = tmp_path / 'browser.exe'
    browser.touch()
    monkeypatch.setenv('JIEJIAN_PLAYWRIGHT_EXECUTABLE', str(browser))
    monkeypatch.setattr(system_status, 'runtime_environment_details', lambda: pytest.fail('deep probe in summary'))
    monkeypatch.setattr(system_status, 'frontend_asset_identity', lambda _: pytest.fail('hashing in summary'))
    view = system_status.SystemRuntimeView(None, lambda: {'worker': 'running'})
    assert view.summary()['browser'] == 'available'
    browser.unlink()
    assert view.summary()['browser'] == 'unavailable'


def test_diagnostics_snapshot_is_explicitly_refreshed_and_export_is_allowlisted(monkeypatch):
    probes = []
    secret = 'private-token-and-personal-path'
    def probe():
        probes.append(1)
        return {'python': {'ok': True, 'executable': secret, 'package_origins': {'private': secret}},
                'playwright': {'status': 'available', 'chromium_executable': secret}, 'runtime_mode': 'portable'}
    monkeypatch.setattr(system_status, 'runtime_environment_details', probe)
    monkeypatch.setattr(system_status, 'frontend_asset_identity', lambda _: {'status': 'CONFIRMED', 'build_id': 'a' * 64})
    view = system_status.SystemRuntimeView(Path('.'), lambda: {'worker': 'running'})
    first = view.inspect()
    assert view.inspect()['checked_at'] == first['checked_at']
    assert len(probes) == 1
    assert secret not in str(first)
    assert 'environment' not in first
    assert view.inspect(refresh=True)['checked_at'] >= first['checked_at']
    assert len(probes) == 2


def test_diagnostics_build_replacement_invalidates_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(system_status, 'runtime_environment_details', lambda: {
        'python': {'ok': True}, 'playwright': {'status': 'available'}, 'runtime_mode': 'source'})
    builds = []
    monkeypatch.setattr(system_status, 'frontend_asset_identity', lambda _: builds.append(1) or {'status': 'CONFIRMED'})
    view = system_status.SystemRuntimeView(tmp_path, lambda: {'worker': 'running'})
    view.inspect()
    (tmp_path/'frontend-manifest.json').write_text('new actual build', encoding='utf-8')
    assert view.summary()['diagnostics_stale']
    view.inspect()
    assert not view.summary()['diagnostics_stale']
    assert len(builds) == 2
