// 路由元信息只有这一份；业务查询参数仍由各工作面解释，加载函数留在应用层。
export type RouteDefinition={path:string;label:string;scoped:boolean;primary?:boolean;global?:boolean;settings?:'tools'|'storage'|'system';preload:'home'|'permissions'|'testing'|'issues'|'application'|'environment'|'reports'|'preparation'|'tools'|'changes'|'storage'|'system'|'archive'}
export const routes:readonly RouteDefinition[]=[
  {path:'/workspace',label:'工作台',scoped:true,primary:true,preload:'home'},
  {path:'/permissions',label:'权限与覆盖',scoped:true,primary:true,preload:'permissions'},
  {path:'/testing',label:'测试',scoped:true,primary:true,preload:'testing'},
  {path:'/issues',label:'问题',scoped:true,primary:true,preload:'issues'},
  {path:'/application',label:'应用与来源',scoped:true,primary:true,preload:'application'},
  {path:'/environment',label:'官方示例',scoped:false,global:true,preload:'environment'},
  {path:'/reports',label:'运行记录',scoped:true,preload:'reports'},
  {path:'/preparation',label:'测试准备',scoped:true,preload:'preparation'},
  {path:'/tools',label:'开发工具',scoped:true,global:true,settings:'tools',preload:'tools'},
  {path:'/changes',label:'源码修改',scoped:true,preload:'changes'},
  {path:'/storage',label:'本地存储',scoped:true,global:true,settings:'storage',preload:'storage'},
  {path:'/system',label:'运行与维护',scoped:true,global:true,settings:'system',preload:'system'},
  {path:'/archive',label:'归档记录',scoped:false,global:true,preload:'archive'},
  {path:'/settings',label:'设置',scoped:true,global:true,preload:'tools'},
]
export function routeDefinition(path:string){return routes.find(item=>item.path===path)}
export const routeAliases:Readonly<Record<string,string>>={'/results':'/reports','/history':'/reports','/identities':'/preparation','/flows':'/preparation','/settings/models':'/tools'}
