// 单规则工作面分开呈现规则、材料与已发生检查；历史修订不冒充当前有效规则。
import {Alert,Button,Spin} from 'antd'
import {useEffect,useState} from 'react'
import {ruleDetailsApi,type RuleDetails} from '../../api/ruleDetails'
import {EditorialHeader,EditorialPage} from '../../shared/ui/Editorial'
import {StatusBadge} from '../../shared/ui/StatusBadge'
import {TaskActionBar} from '../../shared/ui/TaskActionBar'
import {formatTimestamp} from '../../app/presentation'
import '../preparation/proof-sources.css'

const materialLabels:Record<string,string> = {SATISFIED:'已具备',NEEDS_USER:'待补齐',STALE:'需要更新',BLOCKED:'需要处理',NOT_REQUIRED:'无需准备'}
const verdictLabels:Record<string,string> = {SAFE:'符合要求',VULNERABLE:'发现禁止后果',INCONCLUSIVE:'证据尚不足',SKIPPED:'本项未执行',ERROR:'执行未完成'}
export function RuleDetailsPanel({projectId,intentId,revision,onBack,onEdit,onNavigate}:{projectId:string;intentId:string;revision?:number;onBack:()=>void;onEdit:(actionId:string,intentId:string)=>void;onNavigate?:(path:string)=>void}) {
  const [value,setValue] = useState<RuleDetails>(),[error,setError] = useState(false),[epoch,setEpoch] = useState(0)
  useEffect(() => {let current = true;setValue(undefined);setError(false)
    void ruleDetailsApi.read(projectId,intentId,revision).then(next => {
      if(next.project_id!==projectId || next.intent_id!==intentId || (revision!==undefined && next.revision!==revision)) throw new Error('rule mismatch')
      if(current)setValue(next)
    }).catch(() => {if(current)setError(true)})
    return () => {current=false}
  },[projectId,intentId,revision,epoch])
  if(error)return <EditorialPage><EditorialHeader title="这条规则暂时无法读取"/><p>指定的应用或规则修订无法核对，未跳转到其他规则。</p><TaskActionBar back={{label:'返回权限列表',onClick:onBack}} primary={{label:'重新读取',onClick:()=>setEpoch(item=>item+1)}}/></EditorialPage>
  if(!value)return <EditorialPage><Spin/>正在读取这条规则…</EditorialPage>
  const latest = value.latest_result
  return <EditorialPage label="单条权限规则">
    <EditorialHeader eyebrow={`权限要求 / 规则修订 ${value.revision}`} title={value.action_label} status={<StatusBadge kind="rule" tone={value.expectation==='ALLOW'?'success':'danger'}>{value.expectation==='ALLOW'?'允许':'禁止'}</StatusBadge>}><p className="rule-sentence">{value.sentence}</p></EditorialHeader>
    <div className="proof-toolbar"><Button type="link" onClick={onBack}>返回权限列表</Button>{value.current && <Button onClick={()=>onEdit(value.action_id,value.intent_id)}>修改这条规则</Button>}</div>
    {!value.current && <Alert type="info" message="这是保留的历史修订" description="当前权限已经变化，以下显示这个修订的原约定与历史记录。"/>}
    <section className="rule-detail-axes" aria-label="规则、材料与检查分别呈现">
      <div><p className="editorial-eyebrow">规则</p><strong>{value.current?'已由你确认':'历史规则'}</strong><p className="editorial-muted">{formatTimestamp(value.approval.approved_at_us)}</p></div>
      <div><p className="editorial-eyebrow">检查材料</p><strong>{!value.current?'查看历史引用':value.preparation_complete?'可进入完整检查':'仍有材料待准备'}</strong><p className="editorial-muted">材料齐备本身不产生权限结论。</p></div>
      <div><p className="editorial-eyebrow">已发布结果</p><strong>{latest ? latest.applies_to_current_implementation?'有对应当前实现的记录':'有历史记录，当前实现未核验':'本次读取未找到对应记录'}</strong><p className="editorial-muted">按本条规则的精确修订关联。</p></div>
    </section>
    <section className="rule-detail-proof"><h2>这条规则怎样检查</h2><p>{value.expectation==='DENY'?'用不应获准的账号执行这项业务，并保留合法账号的正常对照。':'用这条规则对应的合法账号执行这项业务。'}随后独立读取真实业务结果。</p>
      {value.effects.map(effect=><div key={effect.effect_id}><strong>{effect.label}</strong><p className="editorial-muted">{effect.description}</p></div>)}
    </section>
    {!!value.materials.length && <section className="proof-checks"><div className="proof-section-heading"><h2>已有材料与缺口</h2><Button type="link" onClick={()=>onNavigate?.(value.preparation_url)}>查看检查材料</Button></div><ul>{value.materials.map(item=><li key={item.key}><strong>{item.label}</strong><StatusBadge kind="preparation" tone={['SATISFIED','NOT_REQUIRED'].includes(item.status)?'neutral':'warning'}>{materialLabels[item.status]??'状态待确认'}</StatusBadge></li>)}</ul></section>}
    <section className="rule-detail-results"><h2>本条规则的检查记录</h2>{latest ? <><p className="editorial-muted">{formatTimestamp(latest.created_at_us)} · {latest.applies_to_current_implementation?'源码与运行实例对应':'当时的实现；不代表当前实现已验证'}</p>
      {latest.cases.map((item,index)=><div key={item.case_id} className="proof-toolbar"><span>检查项 {index+1}</span><StatusBadge kind="verdict" tone={item.verdict==='SAFE'?'success':item.verdict==='VULNERABLE'?'danger':'warning'}>{verdictLabels[item.verdict]??'尚无判断'}</StatusBadge><Button type="link" onClick={()=>onNavigate?.(`/tests?run_id=${latest.run_id}&case_id=${item.case_id}&project_id=${projectId}`)}>查看结果与证据</Button></div>)}</> : <p className="editorial-muted">{value.history_has_more?'最近 25 次记录中未找到这一修订的结果，可继续查看检查历史。':'尚未找到这条规则修订的可读结果。'}</p>}
      {value.unreadable_history && <Alert type="warning" message="部分历史记录无法完整核对，未将其作为本条规则的结论。"/>}
    </section>
    <details className="proof-technical"><summary>查看确认依据</summary><p>{value.approval.reason}</p><p className="editorial-muted">{value.approval.approved_by} · 修订 {value.revision}</p></details>
    <TaskActionBar back={{label:'返回权限列表',onClick:onBack}} primary={value.current && onNavigate ? {label:value.preparation_complete?'查看完整检查预览':'继续准备材料',onClick:()=>onNavigate(value.preparation_complete?value.check_url:value.preparation_url)}:undefined}/>
  </EditorialPage>
}
