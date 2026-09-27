// 实现定位单独选择，不改变业务定义与权限语义。
import { Alert, Select, Typography } from "antd"
import type { BoundaryMaintenanceDraftDto } from "../../../api/businessBoundaries"
import { AssistantPanel } from "../../assistant/AssistantPanel"
import { confidenceLabels } from "../draft/boundaryLabels"
export function ImplementationSelector({ kind, item, draft, onChange }: {
  kind: 'ROLE' | 'ACTION'
  item: { actor_id?: string | null; action_id?: string | null; source_candidate_ids?: string[] }
  draft: BoundaryMaintenanceDraftDto
  onChange: (values: string[]) => void
}) {
  const identity = kind === 'ROLE' ? item.actor_id : item.action_id
  const inspection = draft.implementation_inspections.find((value) => kind === 'ROLE'
    ? 'actor_id' in value && value.actor_id === identity
    : 'action_id' in value && value.action_id === identity)
  const candidates = draft.candidate_options.filter((value) => value.candidate_kind === kind)
  const selected = item.source_candidate_ids ?? []
  const missingEvidence = candidates.some((candidate) => selected.includes(candidate.candidate_id) && !candidate.evidence_available)
  return <details className="boundary-candidate-basis" open={Boolean(inspection?.binding_exists && inspection.status !== 'CURRENT')}>
    <summary>当前代码实现{inspection ? ` · ${implementationLabel(inspection.status)}` : ''}</summary>
    <Typography.Paragraph type="secondary">推荐项来自 HIGH/MEDIUM 候选；LOW 只列在“其他可能”中。候选无需先确认，最终仍以本次提案批准为准。</Typography.Paragraph>
    <Select
      mode="multiple"
      aria-label="当前代码实现来源"
      value={selected}
      options={candidates.map((candidate) => ({
        value: candidate.candidate_id,
        label: `${candidate.confidence === 'LOW' ? '其他可能 · ' : ''}${candidate.display_name} · ${confidenceLabels[candidate.confidence]}`,
      }))}
      onChange={onChange}
      style={{ width: '100%' }}
      placeholder="尚未选择可验证的代码实现"
    />
    {missingEvidence && <Alert type="info" showIcon message="这条线索没有可验证源码证据，只能帮助描述业务，不能证明当前代码实现。" />}
    {identity && <AssistantPanel projectId={draft.project_id} surface="implementation-mapping" focus={kind === 'ROLE' ? { business_actor_id: identity } : { business_action_id: identity }} title="理解当前代码实现候选" actionLabel="解释候选" />}
  </details>
}

function implementationLabel(status: string) { return status === "CURRENT" ? "当前有效" : status === "MISSING" ? "缺少可验证证据" : "需要重新确认" }
