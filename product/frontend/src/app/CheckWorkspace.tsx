import {useMemo} from 'react'
import type {PageProps} from '../shared/model/page'
import type {ProjectDto} from '../entities/application/api/projects'
import {WorkflowContext} from '../shared/lib/workflow'
import {useHandoffContext,routeReferences} from '../entities/runtime/model/handoff'
import {go,returnDestination,type Route} from '../shared/lib/navigation'
import {Button} from '../shared/ui/actions'
import {PageError} from '../shared/ui/feedback'
import './check-workspace.css'

import {routePage} from '../shared/lib/routePage'
const Reports=routePage(()=>import('../pages/checks/Reports').then(module=>({default:module.Reports})),'/reports')
const Preparation=routePage(()=>import('../pages/preparation/Preparation').then(module=>({default:module.Preparation})),'/preparation')
const TestingEditor=routePage(()=>import('../pages/testing/TestingEditor').then(module=>({default:module.TestingEditor})),'/testing')
const ApplicationWorkbench=routePage(()=>import('../pages/connections/ApplicationWorkbench').then(module=>({default:module.ApplicationWorkbench})),'/application')
const Permissions=routePage(()=>import('../pages/permissions/Permissions').then(module=>({default:module.Permissions})),'/permissions')

const scopeKeys=['scope_id','rule_id','change_id','scenario_id','scenario_revision','routine_id','routine_revision','binding_id','repair_reference']
const sameCheck=(a:URLSearchParams,b:URLSearchParams)=>scopeKeys.every(key=>a.get(key)===b.get(key))
function supported(route:Route){return ['/preparation','/application','/permissions'].includes(route.path)||route.path==='/testing'&&route.query.has('action_id')&&!route.query.has('scenario')}
function parse(value:string){const [path,search]=value.split('?');return {path,query:new URLSearchParams(search)}}

/** 组合原工作面；URL 保留准确检查范围与当前子事项，刷新不另建任务或重放操作。 */
export function CheckWorkspace(props:PageProps&{project:ProjectDto}){
 const {route,projectId}=props
 const rootQuery=new URLSearchParams(route.query);rootQuery.delete('work_item');rootQuery.delete('work_reviewed')
 const root='/reports?'+rootQuery
 const value=route.query.get('work_item'),destination=returnDestination(value)
 const child=parse(destination??'')
 const valid=!value||Boolean(destination&&supported(child)&&(!child.query.has('project_id')||child.query.get('project_id')===projectId))
 const finishRoot=()=>{const parent=new URLSearchParams(rootQuery);parent.set('work_reviewed','1');go('/reports?'+parent,projectId);props.refresh()}
 const finish=()=>{
  const back=returnDestination(child.query.get('return_to'))
  if(back){const target=parse(back);if(target.path==='/reports'&&target.query.get('view')==='plan'&&sameCheck(target.query,rootQuery)&&target.query.has('work_item')&&(!target.query.has('project_id')||target.query.get('project_id')===projectId)){go(back,projectId);props.refresh();return}}
  finishRoot()
 }
 const open=(target:string)=>{
  const allowed=returnDestination(target)
  if(!allowed)return
  const next=parse(allowed)
  if(next.query.has('project_id')&&next.query.get('project_id')!==projectId){go(allowed);return}
  if(next.path==='/reports'&&next.query.get('view')==='plan'){
   if(!sameCheck(next.query,rootQuery)){go(allowed,projectId);return}
   const parent=new URLSearchParams(rootQuery)
   for(const key of ['plan_tab','plan_item','binding_slot'])if(next.query.has(key))parent.set(key,next.query.get(key)!)
   parent.set('work_reviewed','1');go('/reports?'+parent,projectId);return
  }
  if(!supported(next)){go(allowed,projectId);return}
  const parent=new URLSearchParams(rootQuery),back=returnDestination(next.query.get('return_to'))
  let checkpoint='/reports?'+parent
  if(back){
   const previous=parse(back)
   if(previous.path==='/reports'&&sameCheck(previous.query,rootQuery)){
    for(const key of ['plan_tab','plan_item','binding_slot'])if(previous.query.has(key))parent.set(key,previous.query.get(key)!)
    checkpoint='/reports?'+parent
   }else if(supported(previous)&&(!previous.query.has('project_id')||previous.query.get('project_id')===projectId)){
    // 登录等短准备返回原编辑器；草稿继续由原编辑器保管。
    previous.query.set('return_to',checkpoint)
    const resume=new URLSearchParams(parent);resume.set('work_item',previous.path+'?'+previous.query)
    checkpoint='/reports?'+resume
   }
  }
  next.query.set('return_to',checkpoint)
  parent.set('work_item',next.path+'?'+next.query);go('/reports?'+parent,projectId)
 }
 const back=returnDestination(child.query.get('return_to')),previous=back?parse(back).query.get('work_item'):null
 const finishLabel=previous?.startsWith('/testing?')?'返回接口流程':previous?.includes('configure=')?'返回证明配置':'返回本次检查'
 const references=routeReferences(root)
 // 交接只携带白名单对象与位置，不保存原始 work_item 中可能存在的表单值。
 const handoffRoot=new URLSearchParams(references.return_to.split('?')[1])
 const original=returnDestination(rootQuery.get('return_to'))
 if(original)handoffRoot.set('return_to',routeReferences(original).return_to)
 const resume=(target:string)=>{
  const allowed=returnDestination(target)
  if(!allowed||!supported(parse(allowed))||parse(allowed).query.has('project_id')&&parse(allowed).query.get('project_id')!==projectId)return '/reports?'+handoffRoot
  const safe=parse(routeReferences(allowed).return_to),outer=new URLSearchParams(handoffRoot)
  safe.query.set('resume_draft','1');outer.set('work_item',safe.path+'?'+safe.query)
  return '/reports?'+outer
 }
 const origin=valid&&value?resume(destination!):'/reports?'+handoffRoot
 useHandoffContext({projectId,label:props.name+' · 本次检查',references:{...references,return_to:origin}})
 const navigation=useMemo(()=>({open,finish,label:'本次检查',origin,resume,references,finishLabel,route:value?child:undefined,reviewed:route.query.get('work_reviewed')==='1'}),[root,projectId,value,route.query.get('work_reviewed')])
 if(!valid)return <PageError title="继续本次检查" error={new Error('这项准备位置无效，请返回原检查范围。')}/>
 const content=!value?<Reports {...props}/>:child.path==='/preparation'?<Preparation {...props} route={child}/>:child.path==='/testing'?<TestingEditor {...props} route={child} actionId={child.query.get('action_id')!}/>:child.path==='/permissions'?<Permissions {...props} route={child}/>:<ApplicationWorkbench selected={props.project} onChanged={id=>{if(id===projectId)props.refresh()}}/>
 return <WorkflowContext.Provider value={navigation}>{value&&<section className="jj-work-context" aria-label="当前检查上下文"><div><strong>{props.name} · {route.query.has('routine_id')?'沿用已保存的检查方案':route.query.has('change_id')?'验证这次修改':route.query.has('rule_id')?'核对所选权限要求':'继续本次检查'}</strong><p>完成这里的准备后，继续核对本次检查。已有材料和本地草稿会保留。</p></div><Button kind="quiet" onClick={finishRoot}>返回本次检查</Button></section>}{content}</WorkflowContext.Provider>
}
