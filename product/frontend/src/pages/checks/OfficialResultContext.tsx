import type {ResultStory} from '../../entities/check/api/currentChecks'
import {actual,judgement,judgementLabels,requirement} from '../../entities/check/model/checks'
import {ActionLink} from '../../shared/ui/actions'
import {scopedPath} from '../../shared/lib/navigation'
import './official-result.css'

/** 后果只读报告事实；示例当前版本仅决定接续入口，停止或切换版本不能隐藏历史后果。 */
export function OfficialResultContext({story,implementation}:{story:ResultStory;implementation?:string}){
  const item=story.actions.find(action=>action.permission.expectation==='DENY'&&judgement(action)==='negative'&&action.fact_comparison.effects.some(effect=>effect.assessment_state==='CONFIRMED'))
  if(!item)return null
  const surface=item.fact_comparison.http_surface
  return <section className="jj-official-result" aria-label="这份修改的实际业务后果">
    <h2>本次发现的业务后果</h2><p className="jj-official-requirement">当时要求：{requirement(item)}</p>
    <div className="jj-official-result-columns"><section className="jj-official-business"><h3>实际发生了什么</h3>{item.fact_comparison.effects.filter(effect=>effect.assessment_state==='CONFIRMED').map((effect,index)=><p className="jj-official-effect" key={index}>{actual(effect)}</p>)}<p className="jj-official-judgement" data-tone={judgement(item)}>权限判断：<strong>{judgementLabels[judgement(item)]}</strong></p></section>
    <section className="jj-official-process"><h3>执行过程核对</h3><dl><div><dt>接口响应</dt><dd>{surface.http_status??'尚未取得'}</dd></div><div><dt>检查后的恢复</dt><dd>{surface.recovery_verified?'已核对':'尚未确认'}</dd></div></dl><p>响应拒绝或恢复完成，仍保留已经发生的业务后果。</p></section></div>
    {implementation==='VULNERABLE'&&story.verdict==='BLOCK'&&<div className="jj-official-result-next"><span>也可以进一步检查：响应拒绝，是否仍可能发生越权。</span><ActionLink navigationScope="page" href={'#'+scopedPath('/environment?view=change&experiment=expose',story.project_id)}>查看开放后撤回的修改</ActionLink></div>}
  </section>
}
