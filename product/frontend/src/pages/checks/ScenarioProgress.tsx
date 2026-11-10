import type {CheckStatus} from '../../entities/check/api/currentChecks'

export function ScenarioProgress({nodes}:{nodes:NonNullable<CheckStatus['scenario_execution']>}){
  if(!nodes.length)return null
  const requestLabel={NOT_STARTED:'尚无请求记录',INTENT_SAVED:'请求意图已保存，结果待核对',RECEIVED:'已收到请求回执',UNCONFIRMED:'请求结果未确认'}
  return <section className="jj-scenario-progress" aria-label="业务场景执行进展">
    <h2>实验与恢复进展</h2>
    <p className="jj-small jj-muted">结果未确认的请求会保留原记录，不自动重发。权限结论见检查报告。</p>
    <div className="jj-scroll-table"><table className="jj-content-table jj-plan-case-table">
      <thead><tr><th scope="col">实验与动作</th><th scope="col">请求</th><th scope="col">恢复核对</th></tr></thead>
      <tbody>{nodes.map(node=><tr key={node.experiment_id+':'+node.invocation_id}>
        <td>{node.invocation_label}<small>{node.experiment_label} · {node.case_ids.length} 项资源</small></td>
        <td>{requestLabel[node.request]}</td>
        <td>{node.recovery_intents.length?node.recovered_cases.length===node.recovery_intents.length?'已尝试的恢复均已核对':`${node.recovered_cases.length} / ${node.recovery_intents.length} 项已核对`:'没有恢复请求记录'}</td>
      </tr>)}</tbody>
    </table></div>
  </section>
}
