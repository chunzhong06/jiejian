// 当前结果展示测试共用的冻结事实，不发起真实检查。
import type { CheckObservation, CheckOutcome, CheckStatus, ResultStory } from '../../api/currentChecks'
const ready = { project_id: 'p1', can_execute: true, plan_fingerprint: 'f'.repeat(64), action_count: 1, case_count: 2, actions: [], gaps: [] }
const status = (patch: Partial<CheckStatus> = {}): CheckStatus => ({ run: { run_id: 'r1', project_id: 'p1', lifecycle: 'COMPLETED', verdict: 'BLOCK', plan_fingerprint: ready.plan_fingerprint, policy_epoch: 3, created_at_us: 1780000000000000, finished_at_us: 1780000001000000 }, job: null, progress: null, result_integrity: 'VALID', ...patch })
const observation: CheckObservation = { effect_id: 'e1', proof_fingerprint: 'proof', observer_id: 'source', level: 'VERDICT_REQUIRED', phase: 'AFTER', state: 'CONFIRMED', closure: 'CLOSED', complete: true, reliable: true, correlated: true, authoritative: true, window_start_us: 100, window_end_us: 200, correlation_refs: [], reason_codes: [] }
const source = { source_label: '资源状态', source_location: '/projects/export', observed_fact: observation, supports_claim: '交付包已经生成', does_not_prove: '不能单独证明接口权限检查正确', evidence_refs: ['ev1'] }
const outcome: CheckOutcome = { execution_outcome: 'DENIED', http_status: 403, actual_identity_status: 'UNKNOWN', baseline_trusted: true, recovery_verified: true, run_correlated: true, resource_correlated: true }
const story = (): ResultStory => ({ run_id: 'r1', project_id: 'p1', verdict: 'BLOCK', judgement: '确认禁止的交付包已经生成', policy_epoch: 3, claim_boundary: ['仅覆盖本次规则'], technical_references: [], actions: [{
  action_id: 'a1', action_revision: 1, display_name: '导出资料', case_id: 'c1', permission: { expectation: 'DENY', relation: 'OTHER_ROLE' }, judgement: '本项已确认越权后果',
  fact_comparison: { planned_identity: { identity_id: 'i1', actor_id: 'actor1', label: '计划成员', actor_label: '成员', verification_status: 'PLANNED', namespace: null, application_subject_id: null }, verified_actual_identity: { identity_id: null, actor_id: null, actor_label: null, label: null, verification_status: 'UNKNOWN', namespace: null, application_subject_id: null }, http_surface: outcome, http_explanation: '业务请求被明确拒绝', effects: [{ effect_id: 'e1', business_label: '完整交付包', resource_concept: '项目', observed_state: 'CONFIRMED', judgement: '业务交付包已确认生成', evidence_refs: ['ev1'] }], allow_control: { case_id: 'c2', verdict: 'SAFE', evidence_refs: ['ev2'] } },
  breakpoint: { breakpoint_type: 'AUTHORIZATION_LATE', precision: 'VIOLATION_ONLY', first_violation_event_id: null, range_start_event_id: null, range_end_event_id: null, evidence_refs: ['ev1'] },
  decisive_proof_chain: [source], evidence_explanations: [source], claim_boundary: [], repair_requirement: null, technical_references: [],
}] })

export { ready, status, observation, source, outcome, story }

