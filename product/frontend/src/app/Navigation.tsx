import {preloadRoute} from './Router'
import { AppstoreOutlined, SafetyOutlined, CarryOutOutlined, FileSearchOutlined, LinkOutlined, ApiOutlined, ExperimentOutlined } from '@ant-design/icons'
import type {Route} from '../shared/lib/navigation'
import {historyLocation} from '../shared/lib/navigation'

const primary=[
  {path:'/workspace',label:'应用概览',icon:<AppstoreOutlined aria-hidden="true"/>},
  {path:'/permissions',label:'权限规则',icon:<SafetyOutlined aria-hidden="true"/>},
  {path:'/preparation',label:'检查准备',icon:<CarryOutOutlined aria-hidden="true"/>},
  {path:'/reports',label:'检查记录',icon:<FileSearchOutlined aria-hidden="true"/>},
]
const connections=[
  {path:'/application',label:'应用连接',icon:<LinkOutlined aria-hidden="true"/>},
  {path:'/tools',label:'开发工具',icon:<ApiOutlined aria-hidden="true"/>},
  {path:'/environment',label:'官方示例',icon:<ExperimentOutlined aria-hidden="true"/>},
]
export function normalizedPath(route:Route){
  if(route.path==='/tests')return route.query.has('run_id')?'/reports':route.query.get('materials')==='1'||['task_id','proof_sources','source_id','material_kind','identities'].some(key=>route.query.has(key))?'/preparation':'/reports'
  if(['/results','/history'].includes(route.path))return '/reports'
  if(['/identities','/flows'].includes(route.path))return '/preparation'
  return route.path==='/settings/models'?'/tools':route.path
}
export function pageTransitionKey(route:Route,projectId?:string){
  const path=normalizedPath(route),query=route.query
  let mode='',object=''
  if(path==='/permissions'){mode=query.has('proposal_id')?'review':query.has('candidate_id')?'candidate':query.has('rule_id')?'rule':'';object=query.get('proposal_id')??query.get('candidate_id')??query.get('rule_id')??''}
  if(path==='/preparation')mode=query.has('identities')?'accounts':query.has('proof_sources')||query.has('source_id')?'sources':query.get('material_kind')??''
  if(path==='/reports'||path==='/archive'){mode=query.has('run_id')?'result':query.get('view')??'';object=query.get('run_id')??query.get('change_id')??''}
  if(path==='/changes'){mode=query.get('view')??'';object=query.get('change_id')??''}
  if(path==='/application')mode=query.get('view')??''
  return [path,path==='/archive'?query.get('project_id'):projectId,mode,object].join(':')
}
export function navigationDirection(from:Route,to:Route){
  if(normalizedPath(from)===normalizedPath(to))return from.query.size>to.query.size?'back':'forward'
  const order=[...primary,...connections].map(item=>item.path)
  return order.indexOf(normalizedPath(to))<order.indexOf(normalizedPath(from))?'back':'forward'
}
export function NavigationLinks({current,hasProject,onNavigate}:{current:string;hasProject:boolean;onNavigate:()=>void}){
  const items=(list:typeof primary)=>list.map(item=><a className="jj-nav-item" key={item.path} href={'#'+item.path} onPointerEnter={()=>preloadRoute(item.path)} onFocus={()=>preloadRoute(item.path)} aria-current={current===item.path?'page':undefined} onClick={onNavigate}>{item.icon}<span>{item.label}</span></a>)
  return <div className={'jj-nav-groups'+(hasProject?' has-project':'')}>{hasProject&&<nav aria-label="应用工作区">{items(primary)}</nav>}<section className="jj-nav-section"><h2>连接与环境</h2><nav aria-label="连接与环境">{items(connections)}</nav></section></div>
}
export function Breadcrumbs({route,projectName,projectId}:{route:Route;projectName?:string;projectId?:string}){
  const current=normalizedPath(route),section=[...primary,...connections,{path:'/changes',label:'源码修改'},{path:'/storage',label:'本地存储'},{path:'/archive',label:'归档记录'}].find(item=>item.path===current)
  const detail=current==='/reports'?route.query.has('run_id')?'报告详情':route.query.get('view')==='plan'?'检查范围':undefined
    :current==='/permissions'&&route.query.has('proposal_id')?'审阅权限变更'
    :current==='/permissions'&&route.query.has('rule_id')?'规则详情'
    :current==='/preparation'?route.query.has('identities')?'测试账号':route.query.has('proof_sources')||route.query.has('source_id')?'证明来源':undefined
    :current==='/application'&&route.query.get('view')==='business'?'业务名称'
    :current==='/changes'&&route.query.get('view')==='register'?'登记修改'
    :current==='/archive'&&route.query.has('run_id')?'报告详情':undefined
  const global=['/environment','/tools','/storage','/archive'].includes(current)||!projectName
  const parent=current==='/reports'?historyLocation(projectId):current==='/archive'?'/archive?project_id='+encodeURIComponent(route.query.get('project_id')??''):section?.path
  const levels=[{label:global?'界鉴':projectName!,href:'#/workspace'},...(current==='/archive'?[{label:'官方示例',href:'#/environment'}]:[]),...(section?[{label:section.label,href:detail?'#'+parent:undefined}]:[]),...(detail?[{label:detail,href:undefined}]:[])]
  return <nav className="jj-breadcrumb" aria-label="当前位置"><ol>{levels.map((item,index)=><li key={index}>{index>0&&<span className="jj-breadcrumb-separator" aria-hidden="true">/</span>}{item.href?<a href={item.href}>{item.label}</a>:<span aria-current="page">{item.label}</span>}</li>)}</ol></nav>
}
