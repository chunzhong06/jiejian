import {routeDefinition} from './routes'
export type Route={path:string;query:URLSearchParams}
export function readRoute():Route{const [path,query]=(location.hash.slice(1)||'/workspace').split('?');return {path,query:new URLSearchParams(query)}}
export function scopedPath(path:string,projectId?:string){
  // 路径明确指定的项目不被当前选择覆盖；补默认范围服务应用内页面与保留应用上下文的工具入口，不替代服务端归属校验。
  const [pathname,search]=path.split('?'),query=new URLSearchParams(search)
  const scope=projectId??readRoute().query.get('project_id')??localStorage.getItem('jiejian.studio.project')
  if(scope&&routeDefinition(pathname)?.scoped&&!query.has('project_id'))query.set('project_id',scope)
  return pathname+(query.size?'?'+query:'')
}
export function go(path:string,projectId?:string){location.hash=scopedPath(path,projectId)}
/** 范围恢复只是入口解析，替换中转地址，避免后退时再次跳回同一预览。 */
export function replaceDestination(path:string,projectId?:string){location.replace('#'+scopedPath(path,projectId))}
export function returnDestination(value:string|null){
  // 协作须有准确任务；工作台只接受项目范围，不因此放行其他工作台视图或外部地址。
  if(!value||/[#\\\u0000-\u0020]/.test(value))return null
  const [path,search]=value.split('?'),query=new URLSearchParams(search)
  if(path==='/workspace')return query.get('view')==='collaboration'&&Boolean(query.get('task_id')?.trim())||[...query.keys()].every(key=>key==='project_id')?value:null
  if(!/^\/(reports|permissions|changes|preparation|testing|issues|application)$/.test(path))return null
  return value
}
export function withReturnDestination(path:string,origin:string){
  const [pathname,search]=path.split('?'),query=new URLSearchParams(search)
  const destination=returnDestination(origin)
  if(destination)query.set('return_to',destination)
  return pathname+(query.size?'?'+query:'')
}
export function returnDestinationLabel(destination:string){
  const [path,search]=destination.split('?'),query=new URLSearchParams(search)
  if(path==='/reports')return query.get('view')==='compare'?'返回本轮变化':query.get('view')==='plan'?'返回检查范围':query.has('run_id')?'返回检查报告':'返回检查记录'
  if(path==='/permissions')return '返回权限规则'
  if(path==='/testing')return query.get('view')==='plans'?'返回检查方案':query.has('action_id')?'返回接口流程':query.has('scenario')?'返回业务场景':'返回操作与材料'
  if(path==='/preparation')return '返回检查准备'
  if(path==='/issues')return '返回修复任务'
  if(path==='/changes')return '返回源码修改'
  if(path==='/application')return '返回应用与来源'
  if(path==='/workspace')return query.get('view')==='collaboration'?'返回协作任务':'返回工作台'
  return '返回发起位置'
}
/** 再次核对沿用已选择的规则、实验和原发起位置，不把失败运行改成全量检查。 */
export function checkPlanDestination(query:URLSearchParams){
  const target=new URLSearchParams({view:'plan'})
  for(const key of ['rule_id','scope_id','change_id','scenario_id','scenario_revision','routine_id','routine_revision','binding_id','repair_reference','return_to']){
    const value=query.get(key)
    if(value)target.set(key,value)
  }
  return '/reports?'+target
}
export function historyLocation(projectId?:string){
  if(!projectId)return '/reports'
  try{const saved=sessionStorage.getItem('jiejian.studio.history-location:'+projectId);if(saved?.startsWith('/reports')&&!new URLSearchParams(saved.split('?')[1]).has('run_id'))return saved}catch{}
  return '/reports'
}
