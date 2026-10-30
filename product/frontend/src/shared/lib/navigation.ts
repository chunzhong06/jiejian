export type Route={path:string;query:URLSearchParams}
export function readRoute():Route{const [path,query]=(location.hash.slice(1)||'/workspace').split('?');return {path,query:new URLSearchParams(query)}}
export function scopedPath(path:string,projectId?:string){
  // 路径明确指定的项目不被当前选择覆盖；补默认范围服务应用内页面与保留应用上下文的工具入口，不替代服务端归属校验。
  const [pathname,search]=path.split('?'),query=new URLSearchParams(search)
  const scope=projectId??readRoute().query.get('project_id')??localStorage.getItem('jiejian.studio.project')
  if(scope&&['/workspace','/permissions','/preparation','/reports','/changes','/application','/tools','/storage'].includes(pathname)&&!query.has('project_id'))query.set('project_id',scope)
  return pathname+(query.size?'?'+query:'')
}
export function go(path:string,projectId?:string){location.hash=scopedPath(path,projectId)}
export function returnDestination(value:string|null){
  // 返回位置只允许产品内的已知任务页面，不把任意传入值当作可跳转目的地。
  if(!value||!/^\/(reports|permissions|changes)(\?|$)/.test(value))return null
  return value
}
export function historyLocation(projectId?:string){
  if(!projectId)return '/reports'
  try{const saved=sessionStorage.getItem('jiejian.studio.history-location:'+projectId);if(saved?.startsWith('/reports')&&!new URLSearchParams(saved.split('?')[1]).has('run_id'))return saved}catch{}
  return '/reports'
}
