import type {ActionResultStory} from '../api/currentChecks'
import {actual,judgement,judgementLabels,owner,requirement} from '../model/checks'
import {Badge} from '../../../shared/ui/feedback'
import './business-outcome.css'

/** 只解释同一发布事项的要求、事实与判断；响应状态及恢复由外层提供辅助阅读。 */
export function BusinessOutcome({action}:{action:ActionResultStory}){
  const tone=judgement(action)
  return <div className="jj-business-outcome"><dl>
    <div><dt>当时要求</dt><dd><strong>{requirement(action)}</strong><p className="jj-business-object">{owner(action)}的资源{action.fact_comparison.resource_id&&<> · {action.fact_comparison.resource_id}</>}</p></dd></div>
    <div><dt>实际发生</dt><dd>{action.fact_comparison.effects.length?action.fact_comparison.effects.map(effect=><p key={effect.effect_id}>{actual(effect)}</p>):<p>尚无可读取的业务观察</p>}</dd></div>
    <div><dt>本次判断</dt><dd><Badge tone={tone}>{judgementLabels[tone]}</Badge></dd></div>
  </dl></div>
}
