import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import {ObjectTable} from '../../shared/ui/ObjectTable'
import {SearchField} from '../../shared/ui/SearchField'
import {useRef} from 'react'
import {Inspector,InspectorSection} from '../../shared/ui/Inspector'
import {CommandMenu} from '../../shared/ui/CommandMenu'
import DownOutlined from '@ant-design/icons/DownOutlined'
import {preparationApi} from '../../entities/preparation/api/preparation'
import {operationFlowsApi} from '../../entities/preparation/api/operationFlows'
import {routePage} from '../../shared/lib/routePage'
import {useRead} from '../../shared/lib/useRead'
import {useDirectoryState} from '../../shared/lib/directoryState'
import {go,scopedPath,withReturnDestination} from '../../shared/lib/navigation'
import type {PageProps} from '../../shared/model/page'
import {Heading} from '../../shared/ui/layout'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Badge,Empty,ErrorNote,PageError} from '../../shared/ui/feedback'
import './workspace.css'
import {TestingSections} from '../../shared/ui/SectionNavigation'

const Editor=routePage(()=>import('./TestingEditor').then(module=>({default:module.TestingEditor})),'/testing')
const Scenarios=routePage(()=>import('./BusinessScenarios').then(module=>({default:module.BusinessScenarios})),'/testing')
const Routines=routePage(()=>import('./CheckRoutines').then(module=>({default:module.CheckRoutines})),'/testing')

export function Testing(props:PageProps) {
  if(props.route.query.get('view')==='plans')return <Routines {...props}/>
  if(props.route.query.has('scenario'))return <Scenarios {...props}/>
  const actionId=props.route.query.get('action_id')
  return actionId?<Editor key={props.projectId+props.route.query.toString()} {...props} actionId={actionId}/>:<TestingDirectory projectId={props.projectId}/>
}

function TestingDirectory({projectId}:{projectId:string}) {
  const state=useRead('testing-assets:'+projectId,signal=>operationFlowsApi.summary(projectId,signal))
  // 录制也能完成准备；流程数量不能代替服务给出的材料状态。
  const preparation=useRead('testing-preparation:'+projectId,signal=>preparationApi.get(projectId,signal))
  const collection=useRef<HTMLElement>(null)
  const directory=useDirectoryState('jiejian.directory:'+projectId+':testing',{search:'',selectedId:'',detailOpen:true as boolean},Boolean(state.data),collection)
  const {search,selectedId,detailOpen}=directory.value
  const setSearch=(search:string)=>directory.update({search})
  const setDetailOpen=(detailOpen:boolean)=>directory.update({detailOpen})
  const closeDetails=()=>{collection.current?.querySelector<HTMLButtonElement>('.jj-object-select[aria-pressed=true]')?.focus({preventScroll:true});setDetailOpen(false)}
  const destination=(path:string)=>withReturnDestination(path,'/testing')
  const navigation=<TestingSections value="materials" projectId={projectId}/>
  if(state.loading&&!state.data)return <PageSkeleton view="/testing" title="操作与材料" navigation={navigation}/>
  if(!state.data)return <PageError title="操作与材料" navigation={navigation} error={state.error}/>
  const context=state.data
  const actions=context.actions.filter(item=>item.label.includes(search))
  const selected=actions.find(item=>item.action_id===selectedId)??actions[0]
  const materialFor=(id:string)=>preparation.data?.actions.find(item=>item.action_id===id)
  const savedFor=(id:string)=>context.flows.filter(item=>item.business_action_id===id)
  const statusFor=(id:string)=>{
    const ready=materialFor(id)
    return ready?.preparation_complete?{label:'可用于检查',tone:'positive' as const}:preparation.loading&&!preparation.data?{label:'读取准备状态',tone:'neutral' as const}:preparation.error?{label:'准备状态待核对',tone:'caution' as const}:!ready?{label:'尚未确认检查要求',tone:'neutral' as const}:{label:'仍有待准备事项',tone:'neutral' as const}
  }
  const selectedFlows=selected?savedFor(selected.action_id):[]
  const selectedMaterial=selected?materialFor(selected.action_id):undefined
  const adopted=selectedFlows.find(item=>item.in_use)
  return <><Heading title="操作与材料"/>
    <TestingSections value="materials" projectId={projectId}/>
    {Boolean(context.actions.length||search)&&<div className="jj-workspace-toolbar"><SearchField label="查找业务操作" value={search} onValueChange={setSearch} placeholder="查找业务操作"/>
      <CommandMenu menu={{items:[...(context.actions.length?[{key:'requests',label:'从请求资料开始'}]:[]),{key:'identities',label:'测试账号与登录'},{key:'proof',label:'结果证明'},{key:'gaps',label:'待准备事项'}],onClick:({key})=>{directory.remember(selected?.action_id);go(destination(({requests:'/application?view=sources',identities:'/preparation?identities=1',proof:'/preparation?proof_sources=1',gaps:'/preparation'} as Record<string,string>)[key]))}}}><Button>准备与资料<DownOutlined aria-hidden="true"/></Button></CommandMenu>
    </div>}
    {state.error&&<ErrorNote error={state.error}/>}
    {preparation.error&&<ErrorNote error={preparation.error}/>}
    <section ref={collection} data-detail-open={Boolean(selected)&&detailOpen} className="jj-collection jj-testing-directory" aria-label="可维护场景" data-page-pending={preparation.loading&&!preparation.data||undefined}><div className="jj-collection-layout"><div className="jj-collection-main">
      {actions.length?<ObjectTable selection={detailOpen?selected?.action_id??"":""}><thead><tr><th scope="col">业务操作与验证结果</th><th scope="col">执行方式</th><th scope="col" className="jj-table-state">当前准备</th></tr></thead><tbody>{actions.map(action=>{
        const flows=savedFor(action.action_id),active=flows.find(item=>item.in_use),material=materialFor(action.action_id),status=statusFor(action.action_id)
        return <tr key={action.action_id} data-selected={selected?.action_id===action.action_id}><th scope="row"><button className="jj-object-select" data-directory-id={action.action_id} aria-pressed={selected?.action_id===action.action_id} onClick={()=>{directory.update({selectedId:action.action_id,detailOpen:true as boolean})}}><strong>{action.label}</strong><small className="jj-object-summary">{action.effects.map(effect=>effect.label).join('、')||'按已确认要求核对业务结果'}</small></button></th><td className="jj-object-meta">{active?'接口流程':material?.execution.status==='SATISFIED'?'操作录制':flows.length?'接口草稿':'待准备'}<small>{action.state_changing?'包含恢复安排':'只读操作'}</small></td><td className="jj-table-state"><Badge tone={status.tone}>{status.label}</Badge></td></tr>
      })}</tbody></ObjectTable>:<Empty title={search?'没有匹配的业务操作':'先确认要检查的业务操作'} action={<Button onClick={()=>search?setSearch(''):go('/permissions')}>{search?'清除筛选':'设置权限要求'}</Button>}>{search?'可以调整搜索词，或清除筛选查看已有业务操作。':'先在“权限与覆盖”中添加访问要求，再为对应操作准备账号、执行步骤和结果证明。'}</Empty>}
      <p className="jj-testing-count">{context.actions.length} 项业务操作</p>
    </div>{selected&&detailOpen&&<Inspector identity={selected.action_id} title={selected.label} caption="当前业务操作" status={<Badge tone={statusFor(selected.action_id).tone}>{statusFor(selected.action_id).label}</Badge>} onClose={closeDetails} actions={<><ActionLink onClick={()=>directory.remember(selected.action_id)} href={'#'+scopedPath(destination('/testing?action_id='+selected.action_id),projectId)}>{selectedFlows.length?'编辑接口流程':'设置接口流程'}</ActionLink><ActionLink kind="primary" onClick={()=>directory.remember(selected.action_id)} href={'#'+scopedPath(destination('/preparation?action_id='+selected.action_id),projectId)}>准备与核对材料</ActionLink></>}><InspectorSection title="要验证的结果"><p>{selected.effects.map(effect=>effect.label).join('、')||'按权限要求核对实际业务结果。'}</p></InspectorSection><InspectorSection title="执行准备"><dl className="jj-facts" data-layout="columns"><div><dt>执行方式</dt><dd>{adopted?.configuration_current?'接口流程，第 '+adopted.revision+' 修订':selectedMaterial?.execution.status==='SATISFIED'?'已有操作录制':'尚未准备'}</dd></div><div><dt>恢复安排</dt><dd>{selected.state_changing?selectedMaterial?.recovery.status==='SATISFIED'?'已准备恢复':'需确认恢复方式':'只读操作，无需恢复'}</dd></div></dl></InspectorSection></Inspector>}</div></section>
  </>
}
