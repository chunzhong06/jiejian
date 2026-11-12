import {LinkTabs} from './Tabs'
import {scopedPath,returnDestination,withReturnDestination,type Route} from '../lib/navigation'
import {routeAliases} from '../lib/routes'

export const applicationSections=[{value:'environment',label:'应用连接'},{value:'sources',label:'接口来源'},{value:'business',label:'业务角色与操作'}]

/** 分类属于长期目的地，在模块或业务读取失败时仍应可达。 */
export function TestingSections({value,projectId}:{value:'materials'|'plans'|'scenarios'|'history';projectId?:string}){
  return <LinkTabs label="测试工作" value={value} items={[
    {value:'plans',label:'检查方案',href:'#'+scopedPath('/testing?view=plans',projectId)},
    {value:'materials',label:'操作与材料',href:'#'+scopedPath('/testing',projectId)},
    {value:'scenarios',label:'业务场景',href:'#'+scopedPath('/testing?scenario=list',projectId)},
    {value:'history',label:'检查记录',href:'#'+scopedPath('/reports',projectId)},
  ]}/>
}

/** 只为目录提供分类；准确编辑、执行与报告任务继续由其原回程负责。 */
export function directoryNavigation(view:string,route:Route,projectId?:string){
  const path=routeAliases[route.path]??route.path,query=route.query
  const project=projectId??query.get('project_id')??undefined
  if(!project||path!==view)return
  if(path==='/testing'){
    if(query.has('action_id')||query.has('routine_id')||query.has('scenario')&&query.get('scenario')!=='list')return
    const value=query.get('view')==='plans'?'plans':query.get('scenario')==='list'?'scenarios':'materials'
    return {title:value==='plans'?'检查方案':value==='scenarios'?'业务场景':'操作与材料',navigation:<TestingSections value={value} projectId={project}/>}
  }
  if(path==='/reports'&&!['run_id','resume_run','intent_id','rule_id'].some(key=>query.has(key))&&!['plan','compare'].includes(query.get('view')??''))
    return {title:'检查记录',navigation:<TestingSections value="history" projectId={project}/>}
  if(path==='/application'&&query.get('view')!=='create'){
    const selected=query.get('view')??'environment',value=selected==='source'?'environment':selected
    return {title:'应用与来源',navigation:<LinkTabs label="应用资料" value={value} items={applicationSections.map(item=>{
      const params=new URLSearchParams({view:item.value})
      if(query.has('runtime_method'))params.set('runtime_method',query.get('runtime_method')!)
      const path='/application?'+params,origin=returnDestination(query.get('return_to'))
      return {...item,href:'#'+scopedPath(origin?withReturnDestination(path,origin):path,project)}
    })}/>}
  }
}
