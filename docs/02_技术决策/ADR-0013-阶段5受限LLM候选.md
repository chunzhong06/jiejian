# ADR-0013：阶段 5.3 受限 LLM 候选

## 状态

已采纳（2026-08-11）。

## 背景

阶段 5.1/5.2 已建立 Requirement、Candidate、ContractVersion 和确定性分析链。阶段 5.3 需要允许用户显式选择需求后生成待确认 LLM Candidate，但不能让模型输出绕过既有 assessment、REVIEW 或 ACTIVE 门禁。

## 决策

1. Application 只定义最小 provider Callable；默认 provider 为空且完全离线，不引入 SDK、网络配置或模型依赖。Domain 只定义严格输出模型，不依赖 provider。
2. 生成服务只读取调用方明确选择、且属于当前 Project 的已存 Requirement。送模输入为有界规范 JSON，经过 `redact_known_secrets`/通用脱敏；不包含 source locator、源码、Flow 原始请求、环境变量或秘密引用值。
3. 输出只接受 `schema_version=1`、`extra=forbid`、有界候选条数/大小的 JSON。每条输出只能包含授权 `requirement_ids` 与现有 `ContractRule`；Markdown、未知字段、越权需求、重复候选和非法 Rule 均拒绝。
4. LLM Candidate 必须携带 `LLMGenerationMetadata`：provider/model、adapter、prompt template 身份与 hash、规范 input/output hash。非 LLM Candidate 不得携带该 metadata。数据库迁移 `0005_stage5_llm_candidate_metadata` 以可空 JSON 列向前演进，旧 Candidate 读取为 `None`。
5. Candidate ID 由项目、生成 metadata、规则和需求引用确定；provider 调用在数据库事务之外，返回后重新校验需求归属并在单事务中幂等持久化。同 ID 同生成内容复用，不同内容稳定冲突。原始 prompt/响应永不落盘。
6. LLM Candidate 继续进入现有候选合并、确定性 assessment 和人工治理链；模型不可用、调用失败或输出非法只返回稳定脱敏错误，不改变无模型时的核心治理能力。

## 影响与迁移

新增独立 `application/llm_candidates.py`、`domain/llm_candidates.py` 和 `0005` 向前迁移。不改变 Runner/Worker/Verification/Verdict、状态机、API、CLI 或 GUI。0004 既有非 LLM Candidate 无损读取。

## 回滚

停用 LLM 生成服务即可回到5.2；数据库保留可空 metadata 列，不删除既有 Candidate。无破坏性数据回写。
