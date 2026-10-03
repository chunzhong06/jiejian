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

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.core.verification.permissions`、`product.backend.infra.storage.base`、`product.protocols`、`pydantic`、`re`、`sqlalchemy`、`sqlalchemy.exc`、`sqlalchemy.orm`、`time`、`typing`

### `product/backend/infra/storage/results/finalizations.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/finalizations.py) · Python AST；作用域内import不表示每次调用均执行。

- `class FindingFinalizationState`
- `class BaseReportFinalizationState`
- `class RunFinalizationRow`
- `class RunFinalizationRecord`
- `RunFinalizationRecord.validate_state_fields(self) -> RunFinalizationRecord`
- `class RunFinalizationRepository`
- `RunFinalizationRepository.add(self, record) -> None`
- `RunFinalizationRepository.get(self, run_id) -> RunFinalizationRecord &#124; None`
- `RunFinalizationRepository.list_for_runs(self, run_ids) -> tuple[RunFinalizationRecord, ...]`
- `RunFinalizationRepository.save(self, record) -> None`
- `RunFinalizationRepository.ensure_initial(self, run_id, publication_sha256, now_us) -> RunFinalizationRecord`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.infra.storage.base`、`pydantic`、`sqlalchemy`、`sqlalchemy.orm`、`typing`

### `product/backend/infra/storage/results/findings.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/findings.py) · Python AST；作用域内import不表示每次调用均执行。

- `class FindingRow`
- `class FindingOccurrenceRow`
- `class FindingRecord`
- `class FindingOccurrenceRecord`
- `class FindingRepository`
- `FindingRepository.add(self, record) -> None`
- `FindingRepository.get(self, finding_id) -> FindingRecord &#124; None`
- `FindingRepository.list_for_project(self, project_id) -> tuple[FindingRecord, ...]`
- `FindingRepository.touch(self, finding_id, updated_at_us) -> None`
- `FindingRepository.add_occurrence(self, record) -> None`
- `FindingRepository.get_occurrence(self, finding_id, run_id) -> FindingOccurrenceRecord &#124; None`
- `FindingRepository.latest_occurrence(self, finding_id) -> FindingOccurrenceRecord &#124; None`
- `FindingRepository.list_occurrences_for_run(self, run_id) -> tuple[FindingOccurrenceRecord, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/results/gating.py`

[打开源码](../../../../../../../product/backend/infra/storage/results/gating.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RegressionBaselineRow`
- `class GateResultRow`
- `class RegressionBaselineRecord`
- `class GateResultRecord`
- `class GatingRepository`
- `GatingRepository.add_baseline(self, record) -> None`
- `GatingRepository.get_baseline(self, baseline_id) -> RegressionBaselineRecord &#124; None`
- `GatingRepository.get_baseline_for_run(self, project_id, accepted_run_id) -> RegressionBaselineRecord &#124; None`
- `GatingRepository.add_gate_result(self, record) -> None`
- `GatingRepository.get_gate_result(self, gate_result_id) -> GateResultRecord &#124; None`
- `GatingRepository.get_gate_result_for_input(self, baseline_id, run_id, policy_version, input_hash) -> GateResultRecord &#124; None`
- `GatingRepository.latest_gate_result(self, baseline_id, run_id) -> GateResultRecord &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

<!-- GENERATED:END -->
