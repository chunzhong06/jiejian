# =============================================================================
# 受限 LLM Contract Candidate 服务
#
# 定位
#   脱敏 Requirement 与可选 LLM Provider 之间的不可信候选边界
#
# 职责
#   执行显式授权和预算门禁｜校验严格 JSON 输出｜持久化不可信 Candidate
#
# 边界
#   LLM 只能提出 Candidate，不得激活 Contract、执行目标或决定最终安全结论。
#
# 调用链
#   ContractWorkbench → ContractCandidateGenerator → LLMProvider / Storage
# =============================================================================

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from pydantic import ValidationError

from product.backend.core.contracts.analysis.canonical import contract_analysis_sha256
from product.backend.core.contracts.models import ContractCandidate, ContractSourceType, LLMGenerationMetadata, Requirement, SourceReference
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.redaction import redact_known_secrets
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.llm.profiles import ResolvedLLMProvider


class LLMProvider(Protocol):
    def __call__(self, prompt: str) -> str | bytes: ...


class LLMProfileResolver(Protocol):
    @property
    def available(self) -> bool: ...

    def resolve_provider(self, profile_name: str) -> ResolvedLLMProvider: ...


PROMPT_TEMPLATE_ID = "jiejian.contract_candidate"
PROMPT_TEMPLATE_VERSION = "1"
ADAPTER_VERSION = "1"
OUTPUT_MAX_BYTES = 65_536
INPUT_MAX_BYTES = 131_072
_PROMPT_TEMPLATE = (
    "Return only schema_version=1 JSON with candidates containing requirement_ids and suggestion. "
    "Use only the supplied requirements and existing CandidateSuggestion enums.\n"
    "INPUT_JSON:\n"
)
_PROMPT_TEMPLATE_SHA256 = hashlib.sha256(_PROMPT_TEMPLATE.encode("utf-8")).hexdigest()


class ContractCandidateGenerator:
    """在 provider 调用前后均保持项目/需求授权和确定性持久化边界。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        provider: LLMProvider | None = None,
        provider_id: str = "offline-provider",
        model_id: str = "offline-model",
        known_secrets: Sequence[str] = (),
        clock_us: Callable[[], int] | None = None,
        profile_resolver: LLMProfileResolver | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._provider = provider
        self._provider_id = provider_id
        self._model_id = model_id
        self._known_secrets = tuple(known_secrets)
        self._clock_us = clock_us or (lambda: 0)
        self._profile_resolver = profile_resolver

    @property
    def available(self) -> bool:
        return self._provider is not None or (
            self._profile_resolver is not None and self._profile_resolver.available
        )

    def generate(
        self,
        project_id: str,
        requirement_ids: tuple[str, ...],
        *,
        actor: str,
        profile_name: str | None = None,
    ) -> LLMGenerationResult:
        """在显式授权、输入预算和秘密检查通过后生成并保存不可信候选。"""

        # --- 阶段：验证需求归属并解析明确的 provider 配置 ---
        selected_ids = tuple(sorted(set(requirement_ids)))
        if not selected_ids or len(selected_ids) != len(requirement_ids):
            raise JiejianError(ErrorCode.LLM_REQUIREMENT_INVALID, "LLM 需求选择为空或重复")
        requirements = self._load_requirements(project_id, selected_ids)
        resolved = None
        if profile_name is not None:
            if self._profile_resolver is None:
                raise JiejianError(ErrorCode.LLM_PROVIDER_UNAVAILABLE, "LLM profile 未配置")
            resolved = self._profile_resolver.resolve_provider(profile_name)
            provider: LLMProvider = resolved
            provider_id = resolved.provider.value
            model_id = resolved.model
            known_secrets = resolved.known_secrets
            budget_limit = resolved.budget_limit_microusd
        else:
            if self._provider is None:
                raise JiejianError(ErrorCode.LLM_PROVIDER_UNAVAILABLE, "LLM provider 未配置")
            provider = self._provider
            provider_id = self._provider_id
            model_id = self._model_id
            known_secrets = self._known_secrets
            budget_limit = None
        self._validate_label(provider_id, known_secrets)
        self._validate_label(model_id, known_secrets)
        # --- 阶段：构造脱敏有界 prompt 并调用 provider ---
        input_bytes = self._build_input(requirements, known_secrets)
        prompt = _PROMPT_TEMPLATE + input_bytes.decode("utf-8")
        input_hash = hashlib.sha256(input_bytes).hexdigest()
        if budget_limit is not None and budget_limit <= 0:
            raise JiejianError(ErrorCode.LLM_BUDGET_EXCEEDED, "LLM 单次预算不可用")
        started_at_us = self._clock_us() if resolved is not None else 0
        try:
            raw_output = provider(prompt)
        except JiejianError:
            raise
        except Exception as exc:
            raise JiejianError(_map_provider_exception(exc), "LLM provider 调用失败") from None
        duration_us = (
            max(0, self._clock_us() - started_at_us) if resolved is not None else 0
        )
        output_bytes = self._output_bytes(raw_output)
        output_hash = hashlib.sha256(output_bytes).hexdigest()
        # --- 阶段：严格解析输出并持久化稳定候选 ---
        parsed = self._parse_output(output_bytes)
        candidates = self._build_candidates(
            project_id,
            selected_ids,
            parsed,
            input_hash=input_hash,
            output_hash=output_hash,
            actor=actor,
            provider_id=provider_id,
            model_id=model_id,
            profile_name=resolved.profile_name if resolved else None,
            adapter_version=resolved.adapter_version if resolved else ADAPTER_VERSION,
            prompt_version=resolved.prompt_version if resolved else PROMPT_TEMPLATE_VERSION,
            started_at_us=started_at_us,
            duration_us=duration_us,
            budget_limit_microusd=budget_limit,
        )
        candidates = self._persist(project_id, selected_ids, candidates)
        return LLMGenerationResult(
            candidates=candidates,
            input_sha256=input_hash,
            output_sha256=output_hash,
        )

    def _load_requirements(
        self, project_id: str, requirement_ids: tuple[str, ...]
    ) -> tuple[Requirement, ...]:
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.LLM_REQUIREMENT_INVALID, "LLM 需求项目不存在")
            requirements: list[Requirement] = []
            for requirement_id in requirement_ids:
                requirement = work.requirements.get(requirement_id)
                if requirement is None or requirement.project_id != project_id:
                    raise JiejianError(ErrorCode.LLM_REQUIREMENT_INVALID, "LLM 需求未授权")
                requirements.append(requirement)
            return tuple(requirements)

    def _build_input(
        self,
        requirements: tuple[Requirement, ...],
        known_secrets: Sequence[str],
    ) -> bytes:
        payload = {
            "schema_version": "1",
            "requirements": [
                {
                    "requirement_id": requirement.requirement_id,
                    "text": redact_known_secrets(requirement.text, known_secrets),
                    "security_tags": requirement.security_tags,
                }
                for requirement in requirements
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > INPUT_MAX_BYTES:
            raise JiejianError(ErrorCode.LLM_REQUIREMENT_INVALID, "LLM 输入超过大小限制")
        return encoded

    @staticmethod
    def _output_bytes(raw_output: str | bytes) -> bytes:
        if isinstance(raw_output, str):
            encoded = raw_output.encode("utf-8")
        elif isinstance(raw_output, bytes):
            encoded = raw_output
        else:
            raise JiejianError(ErrorCode.LLM_OUTPUT_INVALID, "LLM 输出类型无效")
        if len(encoded) > OUTPUT_MAX_BYTES:
            raise JiejianError(ErrorCode.LLM_OUTPUT_INVALID, "LLM 输出超过大小限制")
        try:
            encoded.decode("utf-8")
        except UnicodeDecodeError:
            raise JiejianError(ErrorCode.LLM_OUTPUT_INVALID, "LLM 输出编码无效") from None
        return encoded

    @staticmethod
    def _parse_output(raw_output: bytes) -> LLMOutput:
        try:
            payload = json.loads(raw_output.decode("utf-8"))
            if not isinstance(payload, Mapping) or payload.get("schema_version") != "1":
                raise ValueError("missing output schema version")
            return LLMOutput.model_validate_json(raw_output, strict=True)
        except (TypeError, ValueError, ValidationError, json.JSONDecodeError):
            raise JiejianError(ErrorCode.LLM_OUTPUT_INVALID, "LLM 输出不符合受控 JSON 协议") from None

    def _build_candidates(
        self,
        project_id: str,
        selected_ids: tuple[str, ...],
        output: LLMOutput,
        *,
        input_hash: str,
        output_hash: str,
        actor: str,
        provider_id: str,
        model_id: str,
        profile_name: str | None,
        adapter_version: str,
        prompt_version: str,
        started_at_us: int,
        duration_us: int,
        budget_limit_microusd: int | None,
    ) -> tuple[ContractCandidate, ...]:
        """把严格 JSON 输出投影为稳定 Candidate；未知需求或敏感值会拒绝整批。"""

        selected = set(selected_ids)
        metadata = LLMGenerationMetadata(
            provider_id=provider_id,
            model_id=model_id,
            adapter_version=adapter_version,
            prompt_template_id=PROMPT_TEMPLATE_ID,
            prompt_template_version=prompt_version,
            prompt_template_sha256=_PROMPT_TEMPLATE_SHA256,
            input_sha256=input_hash,
            output_sha256=output_hash,
            provenance_schema_version="2" if profile_name is not None else None,
            provider=provider_id if profile_name is not None else None,
            profile_name=profile_name,
            model=model_id if profile_name is not None else None,
            prompt_version=prompt_version if profile_name is not None else None,
            started_at_us=started_at_us if profile_name is not None else None,
            duration_us=duration_us if profile_name is not None else None,
            budget_limit_microusd=budget_limit_microusd,
            estimated_cost_microusd=None,
        )
        candidates: list[ContractCandidate] = []
        for item in output.candidates:
            ids = tuple(sorted(set(item.requirement_ids)))
            if (
                not ids
                or len(ids) != len(item.requirement_ids)
                or not set(ids).issubset(selected)
            ):
                raise JiejianError(ErrorCode.LLM_OUTPUT_INVALID, "LLM 输出引用了未授权需求")
            source = SourceReference(
                source_type=ContractSourceType.LLM,
                locator=f"llm:{provider_id}:{adapter_version}",
                content_sha256=output_hash,
            )
            fingerprint = contract_analysis_sha256(
                {
                    "project_id": project_id,
                    "metadata": _stable_generation_metadata(metadata),
                    "suggestion": item.suggestion,
                    "requirement_ids": ids,
                }
            )
            candidates.append(
                ContractCandidate(
                    candidate_id=f"cand_{fingerprint[:32]}",
                    project_id=project_id,
                    source=source,
                    suggestion=item.suggestion,
                    requirement_ids=ids,
                    created_by=actor,
                    created_at_us=self._clock_us(),
                    llm_metadata=metadata,
                )
            )
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise JiejianError(ErrorCode.LLM_OUTPUT_INVALID, "LLM 输出包含重复候选")
        return tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id))

    def _persist(
        self,
        project_id: str,
        requirement_ids: tuple[str, ...],
        candidates: tuple[ContractCandidate, ...],
    ) -> tuple[ContractCandidate, ...]:
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.LLM_REQUIREMENT_INVALID, "LLM 需求项目不存在")
            for requirement_id in requirement_ids:
                requirement = work.requirements.get(requirement_id)
                if requirement is None or requirement.project_id != project_id:
                    raise JiejianError(ErrorCode.LLM_REQUIREMENT_INVALID, "LLM 需求授权已变化")
            pending: list[ContractCandidate] = []
            resolved: list[ContractCandidate] = []
            for candidate in candidates:
                existing = work.contract_candidates.get(candidate.candidate_id)
                if existing is not None:
                    if not _same_generated_content(existing, candidate):
                        raise JiejianError(ErrorCode.CONTRACT_CANDIDATE_CONFLICT, "LLM Candidate ID 内容冲突")
                    resolved.append(existing)
                    continue
                pending.append(candidate)
                resolved.append(candidate)
            for candidate in pending:
                work.contract_candidates.add(candidate)
            if pending:
                work.commit()
            return tuple(sorted(resolved, key=lambda item: item.candidate_id))

    def _validate_label(self, value: str, known_secrets: Sequence[str]) -> None:
        if not value or value != value.strip() or any(ord(char) < 32 for char in value):
            raise JiejianError(ErrorCode.LLM_PROVIDER_UNAVAILABLE, "LLM provider 元数据无效")
        redacted = redact_known_secrets(value, known_secrets)
        if redacted != value:
            raise JiejianError(ErrorCode.LLM_PROVIDER_UNAVAILABLE, "LLM provider 元数据包含敏感内容")


def _map_provider_exception(exc: Exception) -> ErrorCode:
    return {
        "auth_failed": ErrorCode.LLM_AUTH_FAILED,
        "rate_limited": ErrorCode.LLM_RATE_LIMITED,
        "timeout": ErrorCode.LLM_TIMEOUT,
        "invalid_response": ErrorCode.LLM_INVALID_RESPONSE,
        "budget_exceeded": ErrorCode.LLM_BUDGET_EXCEEDED,
        "response_too_large": ErrorCode.LLM_BUDGET_EXCEEDED,
        "provider_unavailable": ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE,
        "network": ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE,
    }.get(getattr(exc, "kind", None), ErrorCode.LLM_PROVIDER_FAILED)


def _same_generated_content(left: ContractCandidate, right: ContractCandidate) -> bool:
    return _stable_candidate(left) == _stable_candidate(right)


def _stable_generation_metadata(metadata: LLMGenerationMetadata) -> dict[str, object]:
    values = metadata.model_dump(mode="json")
    for key in ("started_at_us", "duration_us", "estimated_cost_microusd"):
        values.pop(key, None)
    return values


def _stable_candidate(candidate: ContractCandidate) -> dict[str, object]:
    values = candidate.model_dump(mode="json")
    values["created_by"] = None
    values["created_at_us"] = None
    if values["llm_metadata"] is not None:
        values["llm_metadata"] = _stable_generation_metadata(candidate.llm_metadata)  # type: ignore[arg-type]
    return values


# 候选输出模型。
# LLM 候选的严格、无 provider 依赖的数据边界。

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.contracts.models import ContractCandidate
from product.backend.core.contracts.models import CandidateSuggestion


class LLMModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class LLMRuleCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    requirement_ids: tuple[str, ...] = Field(min_length=1, max_length=256)
    suggestion: CandidateSuggestion


class LLMOutput(LLMModel):
    candidates: tuple[LLMRuleCandidate, ...] = Field(min_length=1, max_length=32)


class LLMGenerationResult(LLMModel):
    candidates: tuple[ContractCandidate, ...] = Field(min_length=1, max_length=32)
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
