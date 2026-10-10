// 在五类原材料行内解释准备建议；代码线索仅说明建立办法，不替代实际核验或正式批准。
import { useEffect, useState } from 'react'
import { Button } from 'antd'
import type { MaterialSuggestion, MaterialSuggestionKind, PreparationSuggestionView, SuggestionItemView } from '../../../api/preparation/preparationSuggestions'
import './materials.css'

export type MaterialSuggestionEntry = { item: MaterialSuggestion; view: SuggestionItemView }
export const materialSuggestionNames: Record<MaterialSuggestionKind, string> = {
  identity: '真实账号', execution: '动作录制', resource: '测试资源', evidence: '结果证明', recovery: '恢复方式',
}
export function materialSuggestionEntries(value?: PreparationSuggestionView | null): MaterialSuggestionEntry[] {
  return value?.suggestion.content.items.flatMap(item => {
    const view = value.items.find(row => row.item_id === item.item_id)
    return view ? [{ item, view }] : []
  }) ?? []
}
function label(entry: MaterialSuggestionEntry) {
  const target = entry.view.resolved_target
  return [target.action_label, target.actor_label, target.effect_label].filter(Boolean).join(' · ')
}

export function MaterialSuggestionNotes({ entries, allEntries = entries }: { entries: MaterialSuggestionEntry[]; allEntries?: MaterialSuggestionEntry[] }) {
  if (!entries.length) return null
  return <section className="material-suggestion-notes" aria-label="这项材料的整理建议">
    <h3>整理建议</h3>
    {entries.map(({ item, view }) => {
      const material = item.material
      const explanation = material.kind === 'identity' ? material.account_requirement : material.kind === 'resource' ? material.resource_concept
        : material.kind === 'evidence' ? material.observable_result : material.kind === 'recovery' ? material.expected_state : null
      const steps = material.kind === 'execution' ? material.normal_steps : material.kind === 'resource' ? material.preparation_steps : []
      const dependencies = item.depends_on.map(id => allEntries.find(row => row.item.item_id === id)).filter((row): row is MaterialSuggestionEntry => Boolean(row))
      return <article key={item.item_id} className="material-suggestion-item">
        <div className="material-suggestion-content"><p className="editorial-muted">{label({ item, view })}</p>
        <strong>{item.description}</strong>
        {explanation && explanation !== item.description && <p>{explanation}</p>}
        {steps.length > 0 && <ol>{steps.map((step, index) => <li key={index}>{step}</li>)}</ol>}
        {material.kind === 'resource' && material.fields.length > 0 && <dl>{material.fields.map((field, index) => <div key={index}><dt>{field.field}</dt><dd>{field.requirement}</dd></div>)}</dl>}
        {material.kind === 'evidence' && material.field_hints.length > 0 && <p>需要核对：{material.field_hints.join('、')}。</p>}
        {item.gap && item.gap !== item.description && item.gap !== explanation && <p>还缺什么：{item.gap}</p>}
        {dependencies.length > 0 && <p>先准备：{dependencies.map(row => `${materialSuggestionNames[row.item.material.kind]}（${label(row)}）`).join('、')}。</p>}
        </div><aside className="material-suggestion-basis" aria-label="准备分工与依据"><p className="editorial-muted">{item.handler === 'USER' ? '这一步需要你操作。' : item.handler === 'AGENT' ? '可交给 Agent 协助准备，完成后仍需按原流程核对。' : '所需条件齐备后，由界鉴按原流程核对。'}</p>
        <details><summary>查看整理依据</summary><p>{item.source.explanation}</p>
          {item.source.classification === 'SOURCE_CANDIDATE' && view.current && view.source_locations.length > 0
            ? <><ul>{view.source_locations.map((source, index) => <li key={index}><code>{source.relative_path}:{source.line_start}{source.line_end !== source.line_start ? `–${source.line_end}` : ''}</code>{source.symbol && ` · ${source.symbol}`}</li>)}</ul><p className="editorial-muted">这些位置来自已授权的源码分析。实际运行结果需在正式检查中采集。</p></>
            : <p className="editorial-muted">{item.source.classification === 'HYPOTHESIS' ? '这是待核对的准备办法，尚未确认代码对应。' : '当前源码对应需要重新核对，原建议仅供回看。'}</p>}
        </details></aside>
      </article>
    })}
  </section>
}

export function UnboundMaterialSuggestions({ entries, allEntries, returnKind, projectId, onNavigate }: {
  entries: MaterialSuggestionEntry[]; allEntries: MaterialSuggestionEntry[]; returnKind?: string | null; projectId: string; onNavigate: (path: string) => void
}) {
  const [expanded, setExpanded] = useState<string | null | undefined>(returnKind)
  useEffect(() => { setExpanded(returnKind) }, [returnKind])
  if (!entries.length) return null
  const candidates = [...new Set(entries.map(entry => entry.item.target.kind === 'CANDIDATE' ? `${entry.item.target.candidate_id}:${entry.item.target.revision}` : ''))]
  const only = candidates.length === 1 && candidates[0] ? entries[0].item.target : undefined
  const query = new URLSearchParams({ project_id: projectId })
  if (only?.candidate_id && only.revision) { query.set('candidate', only.candidate_id); query.set('revision', String(only.revision)) }
  return <section className="material-unbound-suggestions" aria-label="尚待规则核对的材料建议">
    <div className="material-suggestion-heading"><div><h2>先整理材料怎样准备</h2><p className="editorial-muted">以下建议尚未对应到当前已批准的动作，可先查看建立办法。</p></div><Button onClick={() => onNavigate(`/permissions?${query}`)}>核对规则</Button></div>
    <div className="material-table" role="table" aria-label="预先整理的材料">
      <div className="material-table-head" role="row"><span role="columnheader">材料</span><span role="columnheader">当前情况</span><span role="columnheader">适用内容</span><span role="columnheader">操作</span></div>
      {(Object.entries(materialSuggestionNames) as Array<[MaterialSuggestionKind, string]>).map(([kind, title]) => {
        const rows = entries.filter(entry => entry.item.material.kind === kind)
        return <div key={kind} className="material-group"><div className="material-row" role="row">
          <span role="cell" className="material-row-title">{title}</span><span role="cell">{rows.length ? '待规则核对' : '尚无建议'}</span>
          <span role="cell" className="material-row-summary">{[...new Set(rows.map(label))].join('、') || '未收到这类材料的整理内容'}</span>
          <span role="cell"><Button type="link" disabled={!rows.length} aria-expanded={expanded === kind} onClick={() => setExpanded(value => value === kind ? undefined : kind)}>{expanded === kind ? '收起' : '查看'}</Button></span>
        </div>{expanded === kind && <div className="material-row-detail"><MaterialSuggestionNotes entries={rows} allEntries={allEntries}/></div>}</div>
      })}
    </div>
  </section>
}
