// 候选待办按当前责任分层；收起人的后续决定不改变服务端阻塞和正式批准门槛。
import {Button} from 'antd'
import type {RuleCandidateView} from '../../api/boundaries/ruleCandidates'
import {StatusBadge} from '../../shared/ui/StatusBadge'

export function CandidateWorkPlan({value,busy,copied,onCopy,onRead,onReview}: {
  value:RuleCandidateView;busy:boolean;copied:boolean;onCopy:()=>void;onRead:()=>void;onReview:()=>void
}) {
  const tasks=value.next_tasks??[]
  const agent=tasks.filter(item=>item.handler==='AGENT')
  const human=tasks.filter(item=>item.handler==='USER')
  const capability=tasks.filter(item=>item.handler==='CAPABILITY')
  const confirmed=(value.scope_review??[]).filter(item=>item.status==='CONFIRMED').length+(value.boundary_reviews??[]).filter(item=>item.status==='RESOLVED').length+(value.scenario_decisions??[]).filter(item=>['SELECT','DISMISS'].includes(item.status)).length
  const copy=<Button key="copy" type={copied?'default':'primary'} disabled={busy} onClick={onCopy}>{copied?'再次复制修正请求':'复制修正请求'}</Button>
  const read=<Button key="read" type={copied?'primary':'default'} disabled={busy} onClick={onRead}>读取修正后的候选</Button>
  return <section className="candidate-work-plan" aria-label="本轮整理进度">
    <header><div><span className="editorial-eyebrow">当前候选 · 修订 {value.candidate.revision}</span><h2>先让 Agent 把草稿整理好</h2><p>先修正明确错误和缺少的说明。整理完成后，你再确认需要选择的业务含义。</p></div><StatusBadge kind="rule">尚未批准</StatusBadge></header>
    <ol className="candidate-work-path" aria-label="后续流程"><li aria-current="step"><strong>Agent 修正草稿</strong><span>当前待办</span></li><li><strong>你核对业务要求</strong><span>只确认范围和真实歧义</span></li><li><strong>审阅最终稿</strong><span>批准后准备材料并检查</span></li></ol>
    <div className="candidate-work-focus"><div><h3>交给 Agent 的 {agent.length} 项</h3><p className="editorial-muted">已有明确要求可直接用于修正草稿；人的决定和正式权限仍需你确认。</p></div><div><ul>{agent.slice(0,3).map((item,index)=><li key={`${item.code}-${index}`}><strong>{item.message}</strong><p>{item.next_step}</p></li>)}</ul>{agent.length>3&&<details className="scope-records"><summary>另有 {agent.length-3} 项，同样会带入修正请求</summary><ul>{agent.slice(3).map((item,index)=><li key={index}><strong>{item.message}</strong><p>{item.next_step}</p></li>)}</ul></details>}</div></div>
    <div className="candidate-work-handoff"><p>{copied?'请求已复制，粘贴到原 Agent 对话中。它保存后，读取新修订继续。':'把修正请求发回原 Agent 对话；旧问题与已确认要求一起保留。'}</p><div>{copied?[copy,read]:[read,copy]}</div></div>
    <details className="candidate-work-later"><summary>后续与你有关的内容 · {human.length} 项待核对 · {capability.length} 项检查限制 · {confirmed} 项已确认</summary><p>这些内容仍保留。你可以先查看；处理顺序不会替你作决定。</p>{[...human,...capability].map((item,index)=><p key={index}><strong>{item.handler==='USER'?'需要你判断':'检查限制'}：</strong>{item.message}</p>)}<Button disabled={busy} onClick={onReview}>查看业务要求与原始记录</Button></details>
  </section>
}
