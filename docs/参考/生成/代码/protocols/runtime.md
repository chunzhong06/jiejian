# 自动代码参考：protocols/runtime

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/protocols/runtime/__init__.py`

[打开源码](../../../../../product/protocols/runtime/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/protocols/runtime/frontend_assets.py`

[打开源码](../../../../../product/protocols/runtime/frontend_assets.py) · Python AST；作用域内import不表示每次调用均执行。

- `class FrontendAsset`
- `FrontendAsset.relative_path(self)`
- `class FrontendAssetManifest`
- `FrontendAssetManifest.unique_entry(self)`

静态import / dot-source：`pydantic`、`typing`

### `product/protocols/runtime/node_runtime.py`

[打开源码](../../../../../product/protocols/runtime/node_runtime.py) · Python AST；作用域内import不表示每次调用均执行。

- `class NodeRuntimeManifest`
- `NodeRuntimeManifest.validate_entry(cls, value)`
- `NodeRuntimeManifest.validate_manifest(self)`
- `class NodeRuntimeLoadRequest`
- `class NodeRuntimeReference`
- `class NodeRuntimeLoadReceipt`
- `class NodeRuntimeCorrespondence`
- `node_document_fingerprint(document) -> str`

静态import / dot-source：`__future__`、`hashlib`、`json`、`product.protocols.runtime.runtime_identity`、`pydantic`、`typing`

### `product/protocols/runtime/portable_release.py`

[打开源码](../../../../../product/protocols/runtime/portable_release.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PortableReleaseManifest`

静态import / dot-source：`product.protocols.runtime.runtime_identity`、`pydantic`、`typing`

### `product/protocols/runtime/runtime_identity.py`

[打开源码](../../../../../product/protocols/runtime/runtime_identity.py) · Python AST；作用域内import不表示每次调用均执行。

- `MAX_MANIFEST_BYTES`
- `MAX_ARTIFACT_BYTES`
- `class RuntimeModel`
- `class RuntimeFile`
- `RuntimeFile.safe_path(cls, value) -> str`
- `runtime_source_fingerprint(files) -> str`
- `class RuntimeLaunchManifest`
- `RuntimeLaunchManifest.validate_manifest(self)`
- `runtime_manifest_fingerprint(manifest) -> str`
- `class RuntimeLaunchReceipt`
- `class ControlledRuntimeReference`
- `class RuntimeCorrespondence`
- `receipt_matches(manifest, receipt, owned_process_id) -> bool`

静态import / dot-source：`__future__`、`hashlib`、`json`、`pydantic`、`typing`

### `product/protocols/runtime/transaction_records.py`

[打开源码](../../../../../product/protocols/runtime/transaction_records.py) · Python AST；作用域内import不表示每次调用均执行。

- `bounded_record_data(value)`
- `class RecordChange`
- `RecordChange.safe_path(cls, value)`
- `RecordChange.bounded_value(cls, value)`
- `class RecordSeed`
- `RecordSeed.bounded_data(cls, value)`
- `class RecordTransaction`
- `class RecordSnapshot`
- `class RecordTransition`
- `class RecordOperation`
- `class RecordProviderReference`
- `class RecordProofRequest`
- `class RecordRequestScope`
- `class RecordProofView`

静态import / dot-source：`__future__`、`json`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`pydantic`、`typing`

<!-- GENERATED:END -->
