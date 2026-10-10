# 自动代码参考：backend/infra/storage/results

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/results/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/storage/results/check_publications.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/check_publications.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckPublicationRow`
- `class CheckPublicationRecord`
- `class CheckPublicationRepository`
- `CheckPublicationRepository.get(self, run_id) -> CheckPublicationRecord &#124; None`
- `CheckPublicationRepository.add(self, record) -> None`

静态import / dot-source：`product.backend.infra.storage.base`、`pydantic`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/results/evidence.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/evidence.py) · Python AST；作用域内import不表示每次调用均执行。

- `class EvidenceIndexRow`
- `class EvidenceIndexRecord`
- `EvidenceIndexRecord.validate_content_address_and_path(self) -> EvidenceIndexRecord`
- `class EvidenceIndexRepository`
- `EvidenceIndexRepository.add(self, record) -> None`
- `EvidenceIndexRepository.list_for_run(self, run_id) -> tuple[EvidenceIndexRecord, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.identifiers`、`product.backend.infra.storage.base`、`product.protocols`、`pydantic`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/results/finalizations.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/finalizations.py) · Python AST；作用域内import不表示每次调用均执行。

- `class FindingFinalizationState`
- `class BaseReportFinalizationState`
- `class RunFinalizationRow`
- `class RunFinalizationRecord`
- `RunFinalizationRecord.validate_state_fields(self) -> RunFinalizationRecord`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.infra.storage.base`、`pydantic`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/results/findings.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/findings.py) · Python AST；作用域内import不表示每次调用均执行。

- `class FindingRow`
- `class FindingOccurrenceRow`
- `class FindingRecord`
- `class FindingOccurrenceRecord`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/results/gating.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/gating.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RegressionBaselineRow`
- `class GateResultRow`
- `class RegressionBaselineRecord`
- `class GateResultRecord`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/results/rule_history.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/rule_history.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuleCheckIndexRow`
- `class RuleHistoryRunRow`
- `class RuleHistoryCoverageRow`
- `class RuleHistoryReceiptRow`
- `class RuleHistoryRepository`
- `RuleHistoryRepository.index(self, project_id, run_id, manifest_hash, created_at_us, permissions, error_code)`
- `RuleHistoryRepository.coverage(self, project_id)`
- `RuleHistoryRepository.save_coverage(self, value)`
- `RuleHistoryRepository.receipt(self, project_id, operation_id)`
- `RuleHistoryRepository.save_receipt(self, value)`
- `RuleHistoryRepository.missing(self, project_id)`
- `RuleHistoryRepository.unreadable(self, project_id)`
- `RuleHistoryRepository.upper(self, project_id)`
- `RuleHistoryRepository.scan(self, project_id, cursor, upper, limit)`
- `RuleHistoryRepository.runs(self, project_id, reference, limit, before_time, before_run)`
- `RuleHistoryRepository.rules(self, project_id, limit, after, include_archived)`

静态import / dot-source：`__future__`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`、`作用域内：sqlalchemy`

<!-- GENERATED:END -->
