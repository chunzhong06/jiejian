import {collaborationOperationLabel,type CollaborationOperation} from '../../entities/runtime/api/collaboration'

/** 摘要来自已保存回执；展开历史只阅读，不恢复或重新执行原操作。 */
export function OperationHistory({operations}:{operations:CollaborationOperation[]}){
  const newest=[...operations].reverse(),recent=newest.slice(0,4),earlier=newest.slice(4)
  const list=(items:CollaborationOperation[])=><ul className="jj-collaboration-receipts">{items.map(item=><li key={item.operation_id}>
    <div className="jj-operation-result"><strong>{item.title}</strong><span className="jj-small jj-muted">{collaborationOperationLabel(item)}</span></div>
    {Boolean(item.summary?.length)&&<details className="jj-operation-scope"><summary>查看操作内容</summary><dl className="jj-facts is-stacked" data-layout="columns">{item.summary!.map((fact,index)=><div key={index}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl></details>}
    {item.error_code&&<details className="jj-operation-diagnostic"><summary>执行诊断</summary><p>诊断编号：<code>{item.error_code}</code></p></details>}
  </li>)}</ul>
  return <section className="jj-operation-history" aria-label="已记录的操作结果"><header><h3>操作结果</h3><p className="jj-small jj-muted">共 {operations.length} 项，最近操作在前。已保存的内容可在“产物与相关资料”中查看。</p></header>{list(recent)}
    {earlier.length>0&&<details className="jj-operation-earlier"><summary>更早的操作 · {earlier.length} 项</summary>{list(earlier)}</details>}
  </section>
}
