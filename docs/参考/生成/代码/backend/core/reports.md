# 自动代码参考：backend/core/reports

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/reports/__init__.py`

[打开源码](../../../../../../product/backend/core/reports/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/reports/models.py`

[打开源码](../../../../../../product/backend/core/reports/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `_REPORT_CSS`
- `render_json(report) -> bytes`
- `render_html(report) -> bytes`
- `render_sarif(report) -> bytes`
- `render_junit(report) -> bytes`
- `render_format(report, output_format) -> bytes`

静态import / dot-source：`__future__`、`datetime`、`html`、`json`、`product.protocols.report`、`xml.sax.saxutils`

### `product/backend/core/reports/repair.py`

[打开源码](../../../../../../product/backend/core/reports/repair.py) · Python AST；作用域内import不表示每次调用均执行。

- `_FINDING_ID_PATTERN`
- `_INTENT_ID_PATTERN`
- `_PUBLIC_ID_PATTERN`
- `_REASON_CODE`
- `class RepairModel`
- `class RepairContractReference`
- `class RepairIntentIdentity`
- `class RepairAllowControlIdentity`
- `class RepairRegressionControlIdentity`
- `RepairRegressionControlIdentity.validate_effects(cls, values) -> tuple[str, ...]`
- `class RepairEvidenceStandard`
- `RepairEvidenceStandard.validate_requirements(cls, values) -> tuple[str, ...]`
- `class RepairContract`
- `RepairContract.validate_original_intents(cls, values) -> tuple[RepairIntentIdentity, ...]`
- `RepairContract.validate_sorted_unique(cls, values) -> tuple[str, ...]`
- `RepairContract.validate_contract(self) -> RepairContract`
- `RepairContract.reference(self) -> RepairContractReference`
- `class RepairRequirementView`
- `class RepairVerificationStatus`
- `class RepairPathKind`
- `class RepairPathVerification`
- `RepairPathVerification.validate_evidence_refs(cls, values) -> tuple[str, ...]`
- `RepairPathVerification.validate_reason_codes(cls, values) -> tuple[str, ...]`
- `class RepairVerification`
- `RepairVerification.validate_reason_codes(cls, values) -> tuple[str, ...]`
- `RepairVerification.validate_path_results(self) -> RepairVerification`
- `repair_contract_fingerprint(contract) -> str`

静态import / dot-source：`__future__`、`enum`、`hashlib`、`json`、`product.backend.core.identifiers`、`pydantic`、`re`、`typing`

<!-- GENERATED:END -->
