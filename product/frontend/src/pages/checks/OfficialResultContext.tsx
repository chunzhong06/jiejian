import type {ResultStory} from '../../entities/check/api/currentChecks'
import {judgement} from '../../entities/check/model/checks'
import {ActionLink} from '../../shared/ui/actions'
import {scopedPath} from '../../shared/lib/navigation'
import {BusinessOutcome} from '../../entities/check/ui/BusinessOutcome'
import './official-result.css'

/** 后果只读报告事实；示例当前版本仅决定接续入口，停止或切换版本不能隐藏历史后果。 */
export function OfficialResultContext({story,implementation}:{story:ResultStory;implementation?:string}){
  const item=story.actions.find(action=>action.permission.expectation==='DENY'&&judgement(action)==='negative')??story.actions.find(action=>action.permission.expectation==='DENY')
  if(!item)return null
  const surface=item.fact_comparison.http_surface
  return <section className="jj-official-result" aria-label="这份修改的实际业务后果">
    <h2>内部包访问的业务核对</h2>
    <BusinessOutcome action={item}/>
    <section className="jj-official-process" aria-label="执行过程核对"><dl className="jj-facts" data-layout="columns"><div><dt>接口响应</dt><dd>{surface.http_status??'尚未取得'}</dd></div><div><dt>检查后的恢复</dt><dd>{surface.recovery_verified?'已核对':'尚未确认'}</dd></div></dl><p>接口响应和恢复状态分别记录；已经确认发生的业务后果继续保留。</p></section>
    {implementation==='VULNERABLE'&&story.verdict==='BLOCK'&&<div className="jj-official-result-next"><span>也可以进一步检查：响应拒绝，是否仍可能发生越权。</span><ActionLink navigationScope="page" href={'#'+scopedPath('/environment?view=change&experiment=expose',story.project_id)}>查看开放后撤回的修改</ActionLink></div>}
  </section>
}
