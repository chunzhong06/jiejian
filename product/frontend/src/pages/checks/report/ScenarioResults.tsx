import {ObjectTable} from '../../../shared/ui/ObjectTable'
import type {ActionResultStory} from '../../../entities/check/api/currentChecks'
import {actual,judgement,judgementLabels,owner} from '../../../entities/check/model/checks'
import {scenarioReading} from '../../../entities/check/model/scenarioReading'
import {Badge} from '../../../shared/ui/feedback'
import {text} from '../../../shared/lib/format'

export function ScenarioResults({actions,selected,onOpen}:{actions:ActionResultStory[];selected:string|null;onOpen:(id:string)=>void}){
  // 选中后的目录负责定位；实验与执行说明由相邻依据区完整呈现。
  return <ObjectTable appearance="contained" selection={selected??""} className="jj-scenario-result-table" data-compact={Boolean(selected)} aria-label="逐项业务场景结果">
    <thead><tr><th scope="col">{selected?'业务实验与检查结果':'业务实验'}</th>{!selected&&<><th scope="col">资源归属</th><th scope="col">本次预期与实际结果</th><th scope="col" className="jj-table-state">检查结果</th></>}</tr></thead>
    <tbody>{actions.map(action=>{
      const context=action.scenario_context,resource=action.fact_comparison.resource_id??'未确认编号',reading=scenarioReading(action)
      return <tr key={action.case_id} data-selected={selected===action.case_id}>
        <th scope="row"><button type="button" className="jj-object-select" data-case={action.case_id} data-directory-id={action.case_id} aria-pressed={selected===action.case_id} aria-label={'查看'+reading.title+'，资源'+text(resource)+(reading.batch?'，'+reading.batch:'')+'的依据'} onClick={()=>onOpen(action.case_id)}>{selected&&<span className="jj-scenario-selected-state"><Badge tone={judgement(action)}>{judgementLabels[judgement(action)]}</Badge></span>}<strong>{reading.title}</strong><small>测试资源：<span>{text(resource)}</span></small>{!selected&&reading.labels.length>0&&<small>{reading.labels[0].value}</small>}{reading.batch&&<small>{reading.batch}</small>}</button></th>
        {!selected&&<><td className="jj-scenario-owner" data-label="资源归属">{owner(action)}的资源</td><td className="jj-scenario-observation" data-label="本次预期与实际结果">{context?.expected_effect==='ABSENT'?'不应产生受保护效果':'应产生完整业务效果'}<small>{action.fact_comparison.effects.slice(0,2).map(actual).join('；')||'尚无可读取的业务观察'}{action.fact_comparison.effects.length>2&&`；另有 ${action.fact_comparison.effects.length-2} 项效果，可查看依据`}</small></td></>}
        {!selected&&<td className="jj-table-state"><Badge tone={judgement(action)}>{judgementLabels[judgement(action)]}</Badge></td>}
      </tr>
    })}</tbody>
  </ObjectTable>
}
