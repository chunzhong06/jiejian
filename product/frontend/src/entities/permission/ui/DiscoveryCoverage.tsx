import {discoveryApi,type DiscoveryCoverage,type DiscoveryItem} from '../api/discovery'
import {useRead} from '../../../shared/lib/useRead'
import {scopedPath,withReturnDestination,readRoute} from '../../../shared/lib/navigation'
import {ActionLink} from '../../../shared/ui/actions'
import {ErrorNote} from '../../../shared/ui/feedback'
import {TaskActions} from '../../../shared/ui/layout'
import './discovery-coverage.css'

const states={PENDING:'待确认对应要求',RELATED:'已关联要求',EXCLUDED:'明确不纳入',RECHECK:'关联需要重核'}

/** 结论旁只标明外延，完整说明由报告后面的范围区域承载。 */
export function DiscoveryCoverageSummary({coverage}:{coverage?:DiscoveryCoverage|null}){
  const pending=(coverage?.pending_count??0)+(coverage?.recheck_count??0)
  const unexecuted=coverage?.unexecuted_request_count??0
  if(!pending&&!unexecuted)return null
  return <p className="jj-discovery-summary jj-small jj-muted" aria-label="本次结论之外的业务范围">
    {pending>0&&<span>{pending} 项业务线索未形成权限验证结论。</span>}
    {unexecuted>0&&<span>{unexecuted} 个已关联接口未在本次执行。</span>}
  </p>
}

/** 报告只传冻结快照；embedded 由父范围区命名，内容和处理入口仍完整呈现。 */
export function DiscoveryCoveragePanel({coverage,historical=false,readOnly=false,embedded=false}:{coverage?:DiscoveryCoverage|null;historical?:boolean;readOnly?:boolean;embedded?:boolean}){
  if(!coverage)return historical?<p className="jj-small jj-muted">这份历史检查未记录业务线索清单，权限结果按当时保存的规则与范围阅读。</p>:null
  const pending=coverage.pending_count+coverage.recheck_count
  const route=readRoute(),origin=route.path+'?'+route.query
  const destination=(item:DiscoveryItem)=>item.kind==='REQUEST'?'/application?'+new URLSearchParams({view:'sources',source_id:item.source_id!,request_id:item.request_id!}):'/application?view=business'
  const href=(path:string)=>'#'+scopedPath(withReturnDestination(path,origin))
  const Container=embedded?'div':'section'
  return <Container className="jj-discovery-coverage" aria-label={embedded?undefined:historical?'检查时的业务线索核对':'业务线索核对'}>
    <div className="jj-discovery-overview">{!embedded&&<h3>{historical?'检查时的业务线索核对':'业务线索核对'}</h3>}<span className="jj-small jj-muted">{coverage.related_count} 项已关联要求 · {coverage.excluded_count} 项明确不纳入</span></div>
    <div className="jj-discovery-context"><div className="jj-discovery-copy">
      {pending>0&&<p>{pending} 项线索{historical?'当时尚未完成核对，未据此形成权限验证结论。':'尚待核对对应的权限要求，可继续检查已有规则。'}</p>}
      {Boolean(coverage.unexecuted_request_count)&&<p className="jj-small">{coverage.unexecuted_request_count} 个已关联接口未作为本次受检步骤执行，关联要求不表示该入口已经检查。</p>}
    </div></div>
    <details><summary>{pending?'查看待核对线索与已确认范围':'查看线索与要求的关联'}</summary>
      <div className="jj-scroll-table"><table className="jj-content-table" data-density="compact"><thead><tr><th>业务线索</th><th>核对情况</th>{!readOnly&&<th>继续处理</th>}</tr></thead><tbody>{coverage.items.map(item=><tr key={item.key}><td>{item.label}</td><td>{states[item.status]}{item.in_execution===false&&item.status==='RELATED'&&<small>本次未执行此接口</small>}</td>{!readOnly&&<td><ActionLink kind="quiet" navigationScope="page" href={href(destination(item))}>{historical?'查看当前关联':'核对关联'}</ActionLink></td>}</tr>)}</tbody></table></div>
      {coverage.omitted_count>0&&<p className="jj-small">另有 {coverage.omitted_count} 项未在摘要展开，已计入上方总数；完整清单在应用与来源中核对。</p>}
      {historical&&<p className="jj-small jj-muted">以上保留检查时的核对状态，后来的处理不会改写这份报告。</p>}
    </details>
    {pending>0&&!readOnly&&!historical&&<TaskActions><ActionLink kind="quiet" navigationScope="page" href={href('/application?view=business')}>核对新增业务与权限要求</ActionLink></TaskActions>}
  </Container>
}

export function CurrentDiscoveryCoverage({projectId}:{projectId:string}){
  const state=useRead('discovery:'+projectId,signal=>discoveryApi.current(projectId,signal))
  return <>{state.error&&<ErrorNote error={state.error} onRetry={state.reload} retryLabel="重新读取业务范围"/>}<DiscoveryCoveragePanel coverage={state.data}/></>
}
