import {ObjectTable} from '../../../shared/ui/ObjectTable'
import type {ActionResultStory} from '../../../entities/check/api/currentChecks'
import {actual,judgement,judgementLabels,owner,subject} from '../../../entities/check/model/checks'
import {Badge} from '../../../shared/ui/feedback'
import {text} from '../../../shared/lib/format'

export function ScenarioResults({actions,selected,onOpen}:{actions:ActionResultStory[];selected:string|null;onOpen:(id:string)=>void}){
  return <ObjectTable appearance="contained" selection={selected??""} className="jj-scenario-result-table" data-compact={Boolean(selected)} aria-label="逐项业务场景结果">
    <thead><tr><th>实验与资源</th>{!selected&&<><th>操作账号与归属</th><th>本次预期与实际结果</th></>}<th scope="col" className="jj-table-state">检查结果</th></tr></thead>
    <tbody>{actions.map(action=>{
      const context=action.scenario_context,resource=action.fact_comparison.resource_id??'未确认编号'
      return <tr key={action.case_id} data-selected={selected===action.case_id}>
        <th scope="row"><button type="button" className="jj-object-select" aria-pressed={selected===action.case_id} onClick={()=>onOpen(action.case_id)}>{text(resource)}<small>{context?text(context.experiment_label)+' · '+text(context.invocation_label):text(action.display_name)}{context&&context.item_count>1&&` · 第 ${context.item_index} / ${context.item_count} 项`}</small></button></th>
        {!selected&&<><td>{subject(action)}<small>{owner(action)}的资源</small></td><td>{context?.expected_effect==='ABSENT'?'不应产生受保护效果':'应产生完整业务效果'}<small>{action.fact_comparison.effects.slice(0,2).map(actual).join('；')||text(action.judgement)}{action.fact_comparison.effects.length>2&&`；另有 ${action.fact_comparison.effects.length-2} 项效果，可查看依据`}</small></td></>}
        <td className="jj-table-state"><Badge tone={judgement(action)}>{judgementLabels[judgement(action)]}</Badge></td>
      </tr>
    })}</tbody>
  </ObjectTable>
}
