# Runtime Worker 拥有的通用业务记录端口；应用只有有限业务操作能力，不能写数据库或清除历史。
from __future__ import annotations

import hashlib
import hmac
from importlib import import_module
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import secrets
from threading import Thread
from urllib.parse import unquote, urlsplit

from pydantic import TypeAdapter

from product.backend.infra.observers.adapters.json_source import strict_json
from product.backend.infra.observers.records.transaction_store import TransactionRecordStore, RecordStoreError
from product.protocols.runtime.transaction_records import RecordKey, RecordSeed, RecordTransaction
from product.protocols.runtime.transaction_records import RecordProviderReference, RecordProofRequest
from product.protocols.runtime.node_runtime import ProjectId


def record_store_path(var_dir: Path, project_id: str) -> Path:
    TypeAdapter(ProjectId).validate_python(project_id, strict=True)
    return var_dir.resolve() / "data" / "transaction-records" / project_id / "records.journal"


def record_provider_fingerprint() -> str:
    """冻结产品记录组件本身的实现身份；与任何接入应用的文件名、角色或业务无关。"""
    from product.backend.infra.observers.records import transaction_store
    from product.protocols.runtime import transaction_records
    record_capabilities = import_module('product.backend.infra.runtime.process.records.record_capabilities')
    exclusive_file = import_module('product.backend.infra.runtime.process.exclusive_file')
    digest = hashlib.sha256()
    for module in (transaction_store, transaction_records, record_capabilities, exclusive_file):
        path = Path(module.__file__)
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    digest.update(Path(__file__).read_bytes())
    digest.update((Path(__file__).parents[1] / 'controlled' / 'node_target.mjs').read_bytes())
    return digest.hexdigest()


class OwnedRecordServer:
    """仅在 Runtime Worker 中启动；能力令牌只放入受控 Node 宿主环境，不写持久文件。"""

    def __init__(self, var_dir: Path, project_id: str, instance_id: str):
        self.store = TransactionRecordStore(record_store_path(var_dir, project_id))
        self.var_dir = var_dir
        self.token = secrets.token_urlsafe(32)
        self.read_token = secrets.token_urlsafe(32)
        self.control_token = secrets.token_urlsafe(32)
        self.instance_id = instance_id
        self.fingerprint = record_provider_fingerprint()
        self.collections: set[str] = set()
        from product.backend.infra.runtime.process.records.record_capabilities import save_record_capability
        try:
            save_record_capability(var_dir, instance_id, self.read_token)
        except BaseException:
            self.store.close()
            raise
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def reply(self, code, body):
                raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                try:
                    control = self.path in {'/scope/open','/scope/close'}
                    capability = owner.control_token if control else owner.token
                    if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + capability):
                        return self.reply(403, {"error": "RECORD_ACCESS_DENIED"})
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 98304 or self.headers.get("Transfer-Encoding"):
                        return self.reply(413, {"error": "RECORD_INPUT_LIMIT"})
                    data = strict_json(self.rfile.read(size), 98304)
                    if self.path == '/scope/open' and set(data) == {'request_nonce','request_digest'}:
                        result = owner.store.open_scope(data['request_nonce'],data['request_digest'])
                    elif self.path == '/scope/close' and set(data) == {'scope_id','complete'} and type(data['complete']) is bool:
                        result = owner.store.close_scope(data['scope_id'],data['complete'])
                    elif self.path == "/resource/seed":
                        command = RecordSeed.model_validate_json(json.dumps(data,allow_nan=False))
                        result = owner.store.seed(command)
                        owner.collections.add(command.collection)
                    elif self.path == "/resource/read" and set(data) == {"collection", "resource_id"}:
                        collection = TypeAdapter(RecordKey).validate_python(data["collection"], strict=True)
                        resource = TypeAdapter(RecordKey).validate_python(data["resource_id"], strict=True)
                        result = owner.store.read(collection, resource)
                    elif self.path == "/resource/transact":
                        command = RecordTransaction.model_validate_json(json.dumps(data,allow_nan=False))
                        if command.scope_id is None:
                            raise RecordStoreError('RECORD_SCOPE_REQUIRED')
                        result = owner.store.transact(command)
                    else:
                        return self.reply(404, {"error": "RECORD_OPERATION_UNSUPPORTED"})
                    return self.reply(200, {"data": result.model_dump(mode="json")})
                except RecordStoreError as error:
                    return self.reply(409, {"error": str(error)})
                except (ValueError, TypeError, OSError):
                    return self.reply(400, {"error": "RECORD_INPUT_INVALID"})
                except Exception:
                    return self.reply(503, {"error": "RECORD_STORE_UNAVAILABLE"})

            def do_GET(self):
                try:
                    if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + owner.read_token):
                        return self.reply(403, {'error':'RECORD_READ_DENIED'})
                    parsed = urlsplit(self.path)
                    parts = parsed.path.split('/')
                    if parsed.query or parsed.fragment or parts[:3] != ['', 'proof', 'read'] or len(parts) not in {5,6}:
                        return self.reply(404, {'error':'RECORD_READ_UNSUPPORTED'})
                    command = RecordProofRequest(collection=unquote(parts[3]), resource_id=unquote(parts[4]),
                        request_nonce=unquote(parts[5]) if len(parts)==6 else None)
                    result = owner.store.proof_view(command.collection, command.resource_id, request_nonce=command.request_nonce)
                    return self.reply(200, {'data':result.model_dump(mode='json')})
                except RecordStoreError as error:
                    return self.reply(409, {'error':str(error)})
                except (ValueError, TypeError):
                    return self.reply(400, {'error':'RECORD_INPUT_INVALID'})
                except Exception:
                    return self.reply(503, {'error':'RECORD_STORE_UNAVAILABLE'})

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        except BaseException:
            self.store.close()
            from product.backend.infra.runtime.process.records.record_capabilities import discard_record_capability
            discard_record_capability(var_dir, instance_id)
            raise
        self.server.daemon_threads = True
        self.thread = Thread(target=self.server.serve_forever, name="transaction-records", daemon=True)
        self.thread.start()

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def reference(self, project_id, owner_identity):
        from product.backend.infra.runtime.process.tree import kernel_process_created_at
        created = kernel_process_created_at(owner_identity, os.getpid())
        if created is None:
            raise RecordStoreError("RECORD_OWNER_UNCONFIRMED")
        return RecordProviderReference(project_id=project_id, instance_id=self.instance_id,
            owner_tree_name=owner_identity['name'], owner_process_id=os.getpid(),
            owner_process_created_at=created, port=self.server.server_port,
            implementation_fingerprint=self.fingerprint)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.store.close()
        from product.backend.infra.runtime.process.records.record_capabilities import discard_record_capability
        discard_record_capability(self.var_dir, self.instance_id)
