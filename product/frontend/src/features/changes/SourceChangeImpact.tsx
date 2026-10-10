// 按登记时的精确权限修订组织影响；关联分类来自服务端，不推算权限结论或裁剪检查范围。
import { Button, Drawer, Spin } from 'antd'
import { useContext, useEffect, useState, type ReactNode } from 'react'
import type { SourceChangeViewDto } from '../../api/changes/sourceChanges'
import { ruleDetailsApi, type RuleDetails } from '../../api/boundaries/ruleDetails'
import { preparationApi, type PermissionReference, type PreparationItem, type PreparationView } from '../../api/preparation/preparation'
import { ApiError } from '../../api/http'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import { WorkPageVisible } from '../../shared/runtime/visibility'

type Impact = SourceChangeViewDto['assessment']['payload']['action_impacts'][number]
type RuleRow = { reference: PermissionReference; impact?: Impact }
const referenceKey = (value: PermissionReference) => `${value.intent_id}:${value.revision}:${value.intent_hash}`
const revalidationCopy = {
  READY: ['核对检查准备', '核对本批所需材料，准备完成后再开始检查。'],
  NO_BASELINE: ['先核对源码记录', '缺少修改前的源码记录，暂不能比较本批变化。'],
  SOURCE_STALE: ['先核对当前源码', '登记后源码再次变化，需要核对并登记新的批次。'],
  POLICY_STALE: ['先核对权限版本', '登记后权限已更新，本批记录仍保留原要求。'],
  MAPPING_REVIEW_REQUIRED: ['先复核实现对应', '需要确认业务动作在当前源码中对应的实现。'],
} as const

function RuleImpactRow({ row, projectId, state, onBasis }: { row: RuleRow; projectId: string; state: SourceChangeViewDto['revalidation']['status']; onBasis: (row: RuleRow, rule: RuleDetails | null) => void }) {
  const [rule, setRule] = useState<RuleDetails | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let current = true
    setRule(null); setFailed(false)
    // 指定 revision 的现有 reader 会解析该修订的角色与动作；禁止失败后退回最新规则。
    void ruleDetailsApi.read(projectId, row.reference.intent_id, row.reference.revision).then(value => {
      if (value.project_id !== projectId || value.intent_id !== row.reference.intent_id || value.revision !== row.reference.revision ||
        row.impact && (value.action_id !== row.impact.action_id || value.action_revision !== row.impact.action_revision)) throw new ApiError('STATE_PRECONDITION', '登记权限的修订关联不一致。')
      if (current) setRule(value)
    }).catch(() => { if (current) setFailed(true) })
    return () => { current = false }
  }, [projectId, row.reference.intent_id, row.reference.revision, row.reference.intent_hash, row.impact?.action_id, row.impact?.action_revision, attempt])
  const label = state === 'NO_BASELINE' ? '暂不能判断关联' : state === 'SOURCE_STALE' || state === 'POLICY_STALE' ? '当前关联待核对'
    : row.impact?.classification === 'DIRECTLY_AFFECTED' ? '实现来源有改动' : row.impact?.classification === 'NO_DIRECT_EVIDENCE' ? '暂未发现直接关联' : '实现对应需要复核'
  return <div className="change-rule-row" role="row">
    <div role="cell" className="change-rule-requirement">{rule ? <><StatusBadge kind="rule" tone={rule.expectation === 'ALLOW' ? 'success' : 'danger'}>{rule.expectation === 'ALLOW' ? '允许' : '禁止'}</StatusBadge><div><p>{rule.sentence}</p><small>规则修订 {rule.revision}</small></div></> : <div><p>{failed ? '暂时无法读取登记时的权限要求' : '正在读取登记时的权限要求…'}</p>{failed && <Button onClick={() => setAttempt(value => value + 1)}>重新读取规则</Button>}</div>}</div>
    <div role="cell" className="change-rule-association"><strong>{label}</strong>{state !== 'NO_BASELINE' && <Button type="link" onClick={() => onBasis(row, rule)}>{['SOURCE_STALE', 'POLICY_STALE'].includes(state) ? '查看登记时的依据' : '查看关联依据'}</Button>}</div>
  </div>
}

export function SourceChangeImpact({ projectId, change, action, onNavigate, onSource }: { projectId: string; change: SourceChangeViewDto; action: ReactNode; onNavigate: (path: string) => void; onSource: () => void }) {
  const [showOther, setShowOther] = useState(false)
  const [basis, setBasis] = useState<{ row: RuleRow; rule: RuleDetails | null } | null>(null)
  const [preparation, setPreparation] = useState<PreparationView | null>(null)
  const [preparationFailed, setPreparationFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const state = change.revalidation.status
  const visible = useContext(WorkPageVisible)
  useEffect(() => { if (!visible) setBasis(null) }, [visible])
  const preparationBasis = JSON.stringify(change.revalidation.preparation_gaps)
  useEffect(() => {
    let current = true
    setPreparation(null); setPreparationFailed(false)
    if (state === 'READY') void preparationApi.get(projectId).then(value => {
      if (value.project_id !== projectId) throw new ApiError('STATE_PRECONDITION', '准备材料所属应用不一致。')
      if (current) setPreparation(value)
    }).catch(() => { if (current) setPreparationFailed(true) })
    return () => { current = false }
  }, [projectId, change.manifest.change_id, state, preparationBasis, attempt])
  const payload = change.assessment.payload
  const rows = payload.permission_refs.map(reference => ({ reference, impact: payload.action_impacts.find(item => item.permission_refs.some(value => referenceKey(value) === referenceKey(reference))) }))
  const unknown = ['NO_BASELINE', 'SOURCE_STALE', 'POLICY_STALE'].includes(state)
  const attention = rows.filter(row => unknown || row.impact?.classification !== 'NO_DIRECT_EVIDENCE')
  const other = rows.filter(row => !unknown && row.impact?.classification === 'NO_DIRECT_EVIDENCE')
  const rowElements = (items: RuleRow[]) => items.map(row => <RuleImpactRow key={referenceKey(row.reference)} row={row} projectId={projectId} state={state} onBasis={(selected, rule) => setBasis({ row: selected, rule })}/>)
  const materialGroups: Array<[string, PreparationItem[]]> = preparation ? [
    ['真实账号', preparation.actions.flatMap(item => [item.identity_requirements])],
    ['动作录制', preparation.actions.map(item => item.execution)],
    ['测试资源', preparation.actions.flatMap(item => item.resources)],
    ['结果证明', preparation.actions.flatMap(item => item.effect_evidence)],
    ['恢复方式', preparation.actions.map(item => item.recovery)],
  ] : []
  const materialLabel = (items: PreparationItem[]) => !items.length ? '无此项要求' : items.every(item => item.status === 'NOT_REQUIRED') ? '无需准备' : items.every(item => ['SATISFIED', 'NOT_REQUIRED'].includes(item.status)) ? '可沿用' : items.some(item => item.status === 'STALE') ? '需复核' : '待准备'
  const [title, description] = revalidationCopy[state]
  return <>
    <div className="change-impact-layout">
      <section className="change-rule-impact" aria-label="权限影响"><h2>可能涉及的权限</h2>
        {rows.length ? <div role="table" aria-label="按权限规则查看影响" className="change-rule-table">
          <div role="row" className="change-rule-head"><span role="columnheader">登记时已确认的要求</span><span role="columnheader">{unknown ? '与当前源码的关联' : '与本批改动的关联'}</span></div>
          {rowElements(attention)}
          {!!other.length && (attention.length===0 ? <div role="rowgroup">{rowElements(other)}</div> : <div role="rowgroup"><div className="change-other-heading"><Button type="link" aria-expanded={showOther} aria-controls="change-other-rules" onClick={() => setShowOther(value => !value)}>{showOther ? '收起' : '展开'}暂未发现直接关联的权限 · {other.length} 条</Button><span>仍纳入完整检查</span></div><div id="change-other-rules" hidden={!showOther}>{showOther && rowElements(other)}</div></div>)}
        </div> : <p className="editorial-muted">本批没有已确认的权限引用。</p>}
        <p className="change-impact-note">{unknown ? '登记时的依据仅对应原批次。' : ''}是否符合权限要求，由正式检查判断。</p>
      </section>
      <aside className="change-preparation" aria-label="本批检查准备"><h2>{title}</h2>
        {state !== 'READY' && <p>{description}</p>}
        {state === 'READY' && (preparation ? <dl>{materialGroups.map(([label, items]) => <div key={label}><dt>{label}</dt><dd className={materialLabel(items)==='需复核'?'material-review-required':undefined}>{materialLabel(items)}</dd></div>)}</dl> : preparationFailed ? <p role="status">材料状态暂时无法读取。<Button onClick={() => setAttempt(value => value + 1)}>重新读取材料</Button></p> : <Spin aria-label="正在读取本批材料"/>)}
        <div className="change-preparation-action">{state === 'READY' ? action : <><Button type="primary" onClick={() => state === 'POLICY_STALE' || state === 'MAPPING_REVIEW_REQUIRED' ? onNavigate('/permissions') : onSource()}>{state === 'POLICY_STALE' ? '核对当前权限' : state === 'MAPPING_REVIEW_REQUIRED' ? '复核实现对应' : '核对源码记录'}</Button>{action}</>}</div>
      </aside>
    </div>
    <Drawer title="关联依据" open={Boolean(basis)} onClose={() => setBasis(null)} width={640}>
      {basis && <div className="change-basis"><h3>{basis.rule?.action_label ?? '登记时的业务动作'}</h3>{basis.rule && <p>{basis.rule.sentence}</p>}
        {basis.row.impact?.relevant_paths.length ? <><h4>对应的变化文件</h4><ul className="delivery-file-list">{basis.row.impact.relevant_paths.map(path => <li key={path}><code>{path}</code></li>)}</ul></> : <p>{basis.row.impact?.classification === 'NO_DIRECT_EVIDENCE' ? '登记的实现来源未直接对应本批变化。' : '当前没有可核对的文件关联，需要复核实现对应。'}</p>}
        {!!basis.rule?.effects.length && <><h4>保护的业务结果</h4>{basis.rule.effects.map(effect => <p key={effect.effect_id}>{effect.label}</p>)}</>}
      </div>}
    </Drawer>
  </>
}
