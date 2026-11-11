"""同一次对应核验仍读实际身份，但不为只消费执行器摘要再哈希解释器。"""
from types import SimpleNamespace
from tests.support.builders.runtime.node_runtime import node_runtime_input
from product.backend.infrastructure.runtime.process.controlled import node_owned
from product.backend.infrastructure.runtime.process.controlled.npm import execution_fingerprint
from product.protocols.runtime.node_runtime import NodeRuntimeManifest


def test_correspondence_hashes_the_interpreter_once_and_still_rejects_a_changed_identity(tmp_path, monkeypatch):
    node, artifact, request = node_runtime_input(tmp_path, 18765)
    manifest = NodeRuntimeManifest.model_validate_json((artifact/'launch.json').read_bytes())
    reference = SimpleNamespace(project_id=manifest.project_id, instance_id=manifest.instance_id,
        process_id=123, process_created_at='created', port=manifest.port,
        manifest_fingerprint=request.manifest_fingerprint, source_fingerprint=manifest.source_fingerprint,
        execution_fingerprint=execution_fingerprint(artifact, manifest))
    monkeypatch.setattr(node_owned, 'kernel_process_created_at', lambda *args: 'created')
    monkeypatch.setattr(node_owned, 'ipv4_listeners', lambda port: (('127.0.0.1',123),))
    digests=[]
    def digest(path):
        digests.append(path)
        return manifest.interpreter_fingerprint
    monkeypatch.setattr(node_owned, '_digest', digest)
    assert node_owned.node_corresponds(tmp_path/'var', reference, node)
    assert digests == [node]
    monkeypatch.setattr(node_owned, '_digest', lambda path: '0'*64)
    assert not node_owned.node_corresponds(tmp_path/'var', reference, node)
