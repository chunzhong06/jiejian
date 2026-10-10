// 证据阅读只展示服务端封存投影；切换对象后废弃迟到响应，缺失精确记录不能回退到其他记录。
import {Alert,Button,Spin} from 'antd'
import {useEffect,useRef,useState} from 'react'
import {currentChecksApi,type EvidenceRecordIndex,type EvidenceRecordView,type EvidenceRecordLink} from '../../../api/checks/currentChecks'
import {ApiError} from '../../../api/http'
import {StatusBadge} from '../../../shared/ui/StatusBadge'
import {AgentAssistEntry} from '../../../shared/ui/AgentAssistEntry'

export type EvidenceSelection={proof?:string;observer?:string;phase?:string;event?:string;record?:string}
const display=(value:unknown)=>value===null||value===undefined?'未保存':typeof value==='boolean'?value?'是':'否':String(value)

export function EvidenceVerification({projectId,runId,caseId,actionId,evidenceId,selection,onError,onRecordChange,onNavigate,verifiedIndex}: {
  projectId:string;runId:string;caseId:string;actionId:string;evidenceId:string;selection:EvidenceSelection
  onError:(error:ApiError)=>void;onRecordChange?:(id:string)=>void;onNavigate?:(path:string)=>void
  verifiedIndex?:EvidenceRecordIndex
}) {
  const [index,setIndex]=useState<EvidenceRecordIndex>(),[detail,setDetail]=useState<EvidenceRecordView>(),[selected,setSelected]=useState<string>(),[loading,setLoading]=useState(true),[failed,setFailed]=useState(false)
  const latest=useRef({onError,onRecordChange});latest.current={onError,onRecordChange}
  const origin=JSON.stringify(selection)
  const matches=(value:Omit<EvidenceRecordIndex,'records'>)=>value.project_id===projectId&&value.run_id===runId&&value.case_id===caseId&&value.action_id===actionId&&value.evidence_id===evidenceId
  useEffect(()=>{
    let stopped=false;setIndex(undefined);setDetail(undefined);setSelected(undefined);setLoading(true);setFailed(false)
    void (verifiedIndex?Promise.resolve(verifiedIndex):currentChecksApi.evidenceRecords(projectId,runId,evidenceId,caseId)).then(value=>{
      if(stopped)return
      if(!matches(value))throw new ApiError('ARTIFACT_MANIFEST','证据记录与当前检查项不一致。')
      const wanted=JSON.parse(origin) as EvidenceSelection
      const candidates=value.records.filter(item=>wanted.record?item.record_id===wanted.record:wanted.event?item.kind==='TRACE'&&item.event_id===wanted.event:
        item.kind==='OBSERVATION'&&(!wanted.proof||item.proof_fingerprint===wanted.proof)&&(!wanted.observer||item.observer_id===wanted.observer)&&(!wanted.phase||item.phase===wanted.phase))
      // 目录中的证明默认定位最终观察；明确阶段、节点和深链必须准确匹配。
      const first=candidates.find(item=>item.phase==='EVENTUAL')??candidates.find(item=>item.phase==='AFTER')??candidates[0]??
        (!wanted.record&&!wanted.event&&!wanted.proof&&!wanted.observer&&!wanted.phase?value.records.find(item=>item.kind==='OUTCOME'):undefined)
      if(!first)throw new ApiError('RECORD_NOT_FOUND','没有找到这项选择对应的封存记录。')
      setIndex(value);setSelected(first.record_id)
    }).catch(error=>{if(!stopped){setFailed(true);setLoading(false);latest.current.onError(error as ApiError)}})
    return()=>{stopped=true}
  },[projectId,runId,caseId,actionId,evidenceId,origin,verifiedIndex])
  useEffect(()=>{
    if(!selected||!index)return
    let stopped=false;setDetail(undefined);setLoading(true);setFailed(false)
    void currentChecksApi.evidenceRecord(projectId,runId,evidenceId,caseId,selected).then(value=>{
      if(stopped)return
      if(!matches(value)||value.record.record_id!==selected)throw new ApiError('ARTIFACT_MANIFEST','读取的片段与所选记录不一致。')
      setDetail(value)
    }).catch(error=>{if(!stopped){setFailed(true);latest.current.onError(error as ApiError)}}).finally(()=>{if(!stopped)setLoading(false)})
    return()=>{stopped=true}
  },[projectId,runId,caseId,actionId,evidenceId,selected,index])
  const open=(id:string)=>{if(!index?.records.some(item=>item.record_id===id))return;setSelected(id);latest.current.onRecordChange?.(id)}
  const links=(items:EvidenceRecordLink[])=>items.map(item=><Button key={item.record_id} type="link" aria-pressed={selected===item.record_id} onClick={()=>open(item.record_id)}>{item.label}</Button>)
  return <section className="evidence-verification" aria-label="怎样验证这项要求">
    {loading&&<div role="status"><Spin size="small"/> 正在核对这条记录的出处</div>}
    {failed&&<Alert type="error" showIcon message="无法读取这条准确记录，请返回原检查核对。"/>}
    {detail&&!failed&&<>
      <header><div><p className="editorial-eyebrow">{detail.published_judgement}</p><h3>{detail.record.label}</h3><p>{detail.summary}</p></div><StatusBadge kind="lifecycle" tone="neutral">{detail.role==='SUPPORTING'?'辅助记录':'业务证据'}</StatusBadge></header>
      <div className="evidence-verification-sections">{detail.verification.map(section=><section key={section.key}><h4>{section.title}</h4><p>{section.text}</p>
        <details><summary>核对这段说明的出处</summary><p className="evidence-location">{section.source.logical_file} · {section.source.pointer}</p><code>{section.source.sha256}</code><pre className="check-evidence-json">{JSON.stringify(section.fragment,null,2)}</pre>{links((index?.records??[]).filter(item=>section.record_refs.includes(item.record_id)&&item.record_id!==selected))}</details>
      </section>)}</div>
      {detail.values.length>0&&<section className="evidence-record-values"><h4>记录中的具体值</h4><dl>{detail.values.map((item,n)=><div key={n}><dt>{item.label}</dt><dd>{'before' in item?<><span>之前：{display(item.before)}</span><span>之后：{display(item.after)}</span></>:display(item.value)}</dd></div>)}</dl></section>}
      {detail.related_records.length>0&&<section className="evidence-related" aria-label="对应的原始记录"><h4>对应的原始记录</h4>{links(detail.related_records)}</section>}
      <details className="evidence-technical"><summary>打开这条封存片段</summary><p className="evidence-location">{detail.location.logical_file} · {detail.location.pointer}</p><code>{detail.location.sha256}</code><pre className="check-evidence-json">{JSON.stringify(detail.fragment,null,2)}</pre></details>
      <AgentAssistEntry projectId={projectId} contextKey={`${runId}:${caseId}:${evidenceId}:${selected}`} requiredLevel="READ" title="帮助理解这条证据" description="协助请求会携带当前记录的位置。界鉴的验证说明和结论保持原样。"
        returnTo={`/tests?run_id=${runId}&case_id=${caseId}&tab=records&evidence_id=${evidenceId}&record_id=${selected}`} onNavigate={onNavigate??(()=>{})}
        loadContext={async()=>{const current=await currentChecksApi.evidenceRecord(projectId,runId,evidenceId,caseId,selected!);if(!matches(current)||current.record.record_id!==selected)throw new ApiError('ARTIFACT_MANIFEST','记录位置不一致。');return {projectId,revisionKey:current.location.sha256,
          requestText:`请通过jiejian_evidence_show读取project_id=${projectId}、run_id=${runId}、case_id=${caseId}、evidence_id=${evidenceId}、record_ref=${selected}。按封存记录解释如何验证及为何这样判断，保留缺口，不更改结论或执行新的检查。`}}}/>
    </>}
  </section>
}
