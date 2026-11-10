import type {PreparationBatch} from '../../entities/preparation/api/batches'
import {text} from '../../shared/lib/format'
import {Button} from '../../shared/ui/actions'
import {Badge,Status} from '../../shared/ui/feedback'
import {FormColumns,ObjectIdentity} from '../../shared/ui/layout'
import {Progress} from '../../shared/ui/Progress'

export function BatchProgress({batch,onCancel}:{batch:PreparationBatch;onCancel:()=>void}){
  // 账号与操作先于证明来源准备；来源计数不能充当整个批次的百分比。
  const recipe=batch.phase==='RECIPE'||batch.phase==='RECIPE_RUNNING'
  const measurable=!recipe&&batch.total>0
  const stopping=batch.cancel_requested||batch.state==='CANCELLING'
  const title=stopping?'正在停止准备':recipe?'正在准备示例账号和操作':measurable?'正在核对业务结果证明':'正在核对准备范围'
  return <section className="jj-panel jj-preparation-batch">
    <FormColumns>
      <div className="jj-batch-summary">
        <div className="jj-section-header"><h2 className="jj-title-group">{title}</h2><Badge tone="accent">{measurable?`${batch.completed} / ${batch.total}`:'进行中'}</Badge></div>
        <Progress value={measurable?batch.completed:undefined} max={batch.total} active label={measurable?`业务结果证明已完成 ${batch.completed} / ${batch.total} 项`:title}/>
        {batch.message&&text(batch.message)!==title&&<p className="jj-small jj-muted">{text(batch.message)}</p>}
      </div>
      <div className="jj-batch-items">
        {batch.identities?.map(item=><div key={item.account}><ObjectIdentity name={item.account==='curator'?'负责人账号':item.account==='judge'?'评审账号':item.account} status={<Status tone={item.state==='PREPARED'?'positive':item.state==='FAILED'?'caution':'accent'}>{item.state==='PREPARED'?'已登录':item.state==='FAILED'?'准备中断':'处理中'}</Status>}/></div>)}
        {batch.items?.map(item=><div key={item.label}><ObjectIdentity name={text(item.label)} status={<Status tone={item.state==='READY'?'positive':item.state==='BLOCKED'?'caution':item.state==='CHECKING'?'accent':'neutral'}>{({READY:'已就绪',CHECKING:'正在核对',BLOCKED:'需要处理',WAITING:'等待处理'} as Record<string,string>)[item.state]??text(item.state)}</Status>}/></div>)}
      </div>
    </FormColumns>
    <footer><Button kind="quiet" disabled={stopping} onClick={onCancel}>{stopping?'正在停止':'停止准备'}</Button></footer>
  </section>
}
