import {SearchField} from '../../shared/ui/SearchField'
import {useRef,useState} from 'react'
import {Inspector} from '../../shared/ui/Inspector'
import {CommandMenu} from '../../shared/ui/CommandMenu'
import DownOutlined from '@ant-design/icons/DownOutlined'
import {preparationApi} from '../../entities/preparation/api/preparation'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {routePage} from '../../shared/lib/routePage'
import {useRead} from '../../shared/lib/useRead'
import {go,scopedPath} from '../../shared/lib/navigation'
import type {PageProps} from '../../shared/model/page'
import {Heading} from '../../shared/ui/layout'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Badge,Empty,ErrorNote,PageError,Loading} from '../../shared/ui/feedback'
import './workspace.css'

const Editor=routePage(()=>import('./TestingEditor').then(module=>({default:module.TestingEditor})),'/testing')
const Scenarios=routePage(()=>import('./BusinessScenarios').then(module=>({default:module.BusinessScenarios})),'/testing')

export function Testing(props:PageProps) {
  if(props.route.query.has('scenario'))return <Scenarios {...props}/>
  const actionId=props.route.query.get('action_id')
  return actionId?<Editor key={props.projectId+props.route.query.toString()} {...props} actionId={actionId}/>:<TestingDirectory projectId={props.projectId}/>
}

function TestingDirectory({projectId}:{projectId:string}) {
  const state=useRead('testing-assets:'+projectId,signal=>operationFlowsApi.summary(projectId,signal))
  // 录制也能完成准备；流程数量不能代替服务给出的材料状态。
  const preparation=useRead('testing-preparation:'+projectId,signal=>preparationApi.get(projectId,signal))
  const collection=useRef<HTMLElement>(null),[detailOpen,setDetailOpen]=useState(true)
  const closeDetails=()=>{collection.current?.querySelector<HTMLButtonElement>('.jj-object-select[aria-pressed=true]')?.focus({preventScroll:true});setDetailOpen(false)}
  const [search,setSearch]=useState(''),[selectedId,setSelectedId]=useState<string|null>(null)
  if(state.loading&&!state.data)return <Loading page/>
  if(!state.data)return <PageError title="测试场景" error={state.error}/>
  const context=state.data
  const actions=context.actions.filter(item=>item.label.includes(search))
  const selected=actions.find(item=>item.action_id===selectedId)??actions[0]
  const materialFor=(id:string)=>preparation.data?.actions.find(item=>item.action_id===id)
  const savedFor=(id:string)=>context.flows.filter(item=>item.business_action_id===id)
  const statusFor=(id:string)=>{
    const ready=materialFor(id)
    return ready?.preparation_complete?{label:'可用于检查',tone:'positive' as const}:preparation.loading&&!preparation.data?{label:'读取准备状态',tone:'neutral' as const}:preparation.error?{label:'准备状态待核对',tone:'caution' as const}:!ready?{label:'尚未确认检查要求',tone:'neutral' as const}:{label:'仍有准备缺口',tone:'neutral' as const}
  }
  const selectedFlows=selected?savedFor(selected.action_id):[]
  const selectedMaterial=selected?materialFor(selected.action_id):undefined
  const adopted=selectedFlows.find(item=>item.in_use)
  return <><Heading title="测试场景" actions={<><Button onClick={()=>go('/testing?scenario=list')}>业务场景</Button><Button onClick={()=>go('/reports')}>运行记录</Button><Button kind="primary" onClick={()=>go('/reports?view=plan')}>预览并检查</Button></>}>以业务操作组织录制、接口流程和结果核对，沿用已准备的材料持续验证。</Heading>
    <div className="jj-workspace-toolbar"><SearchField label="查找场景" value={search} onValueChange={setSearch} placeholder="查找业务动作"/>
      <CommandMenu menu={{items:[...(context.actions.length?[{key:'requests',label:'从请求资料开始'}]:[]),{key:'identities',label:'身份与会话'},{key:'proof',label:'结果证明'},{key:'gaps',label:'准备缺口'}],onClick:({key})=>{go(({requests:'/application?view=sources',identities:'/preparation?identities=1',proof:'/preparation?proof_sources=1',gaps:'/preparation'} as Record<string,string>)[key])}}}><Button>准备与资料<DownOutlined aria-hidden="true"/></Button></CommandMenu>
    </div>
    {state.error&&<ErrorNote error={state.error}/>}
    {preparation.error&&<ErrorNote error={preparation.error}/>}
    <section ref={collection} data-detail-open={Boolean(selected)&&detailOpen} className="jj-collection jj-testing-directory" aria-label="可维护场景" data-page-pending={preparation.loading&&!preparation.data||undefined}><div className="jj-collection-layout"><div className="jj-collection-main">
      {actions.length?<div className="jj-scroll-table"><table className="jj-object-table"><thead><tr><th scope="col">业务操作与验证结果</th><th scope="col">执行方式</th><th scope="col" className="jj-table-state">当前准备</th></tr></thead><tbody>{actions.map(action=>{
        const flows=savedFor(action.action_id),active=flows.find(item=>item.in_use),material=materialFor(action.action_id),status=statusFor(action.action_id)
        return <tr key={action.action_id} data-selected={selected?.action_id===action.action_id}><th scope="row"><button className="jj-object-select" aria-pressed={selected?.action_id===action.action_id} onClick={()=>{setSelectedId(action.action_id);setDetailOpen(true)}}><strong>{action.label}</strong><small className="jj-object-summary">{action.effects.map(effect=>effect.label).join('、')||'按已确认要求核对业务结果'}</small></button></th><td className="jj-object-meta">{active?'接口流程':material?.execution.status==='SATISFIED'?'操作录制':flows.length?'接口草稿':'待准备'}<small>{action.state_changing?'包含恢复安排':'只读操作'}</small></td><td className="jj-table-state"><Badge tone={status.tone}>{status.label}</Badge></td></tr>
      })}</tbody></table></div>:<Empty title={search?'没有匹配的业务动作':'先关联要调查的业务动作'} action={<Button onClick={()=>search?setSearch(''):go('/application?view=sources')}>{search?'清除筛选':'打开接口来源'}</Button>}>已有权限要求和场景会持续保存在当前应用中。</Empty>}
      <p className="jj-testing-count">{context.actions.length} 项业务操作 · 接口流程与操作录制共用同一组准备要求</p>
    </div>{selected&&detailOpen&&<Inspector identity={selected.action_id} title={selected.label} caption="当前业务操作" status={<Badge tone={statusFor(selected.action_id).tone}>{statusFor(selected.action_id).label}</Badge>} onClose={closeDetails} actions={<><ActionLink href={'#'+scopedPath('/testing?action_id='+selected.action_id,projectId)}>{selectedFlows.length?'编辑接口流程':'设置接口流程'}</ActionLink><ActionLink kind="primary" href={'#'+scopedPath('/preparation?action_id='+selected.action_id,projectId)}>准备与核对材料</ActionLink></>}><h3>场景材料</h3><dl className="jj-facts"><div><dt>执行操作</dt><dd>{selectedMaterial?.execution.status==='SATISFIED'?'已准备':adopted?.configuration_current?'已有接口流程':'需要准备'}</dd></div><div><dt>接口流程</dt><dd>{new Set(selectedFlows.map(item=>item.id)).size} 份{adopted?' · 当前采用第 '+adopted.revision+' 修订':''}</dd></div><div><dt>结果核对</dt><dd>{selected.effects.map(effect=>effect.label).join('、')}</dd></div><div><dt>恢复安排</dt><dd>{selected.state_changing?selectedMaterial?.recovery.status==='SATISFIED'?'已准备恢复':'需确认恢复方式':'只读操作，无需恢复'}</dd></div></dl></Inspector>}</div></section>
  </>
}
