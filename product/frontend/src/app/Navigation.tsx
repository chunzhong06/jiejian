import {preloadRoute} from './Router'
import AppstoreOutlined from '@ant-design/icons/AppstoreOutlined';
import SafetyOutlined from '@ant-design/icons/SafetyOutlined';
import CarryOutOutlined from '@ant-design/icons/CarryOutOutlined';
import FileSearchOutlined from '@ant-design/icons/FileSearchOutlined';
import LinkOutlined from '@ant-design/icons/LinkOutlined';
import type {Route} from '../shared/lib/navigation'
import {settingsSection,settingsSections} from '../shared/lib/settings'
import {historyLocation,scopedPath} from '../shared/lib/navigation'

const primary=[
  {path:'/workspace',label:'工作台',icon:<AppstoreOutlined aria-hidden="true"/>},
  {path:'/permissions',label:'权限与覆盖',icon:<SafetyOutlined aria-hidden="true"/>},
  {path:'/testing',label:'测试',icon:<CarryOutOutlined aria-hidden="true"/>},
  {path:'/issues',label:'问题',icon:<FileSearchOutlined aria-hidden="true"/>},
  {path:'/application',label:'应用与来源',icon:<LinkOutlined aria-hidden="true"/>},
]
const connections=[
  {path:'/environment',label:'官方示例'},
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
  if(path==='/workspace'&&query.get('view')==='collaboration'){mode='collaboration';object=query.get('task_id')??''}
  if(path==='/permissions'){mode=query.has('proposal_id')?'review':query.has('candidate_id')?'candidate':query.has('rule_id')?'rule':'';object=query.get('proposal_id')??query.get('candidate_id')??query.get('rule_id')??''}
  if(path==='/preparation')mode=query.has('identities')?'accounts':query.has('proof_sources')||query.has('source_id')?'sources':query.get('material_kind')??''
  if(path==='/reports'||path==='/archive'){mode=query.has('run_id')?'result':query.get('view')??'';object=query.get('run_id')??query.get('change_id')??''}
  if(path==='/changes'){mode=query.get('view')??'';object=query.get('change_id')??''}
  if(path==='/application')mode=query.get('view')==='create'?'create':''
  if(path==='/testing'){mode=query.has('action_id')?'flow':'';object=[query.get('action_id'),query.get('source_id'),query.get('request_id')].join(':')}
  if(path==='/issues')object=query.get('case_id')??''
  return [path,path==='/archive'?query.get('project_id'):projectId,mode,object].join(':')
}
export function navigationDirection(from:Route,to:Route){
  if(normalizedPath(from)===normalizedPath(to))return from.query.size>to.query.size?'back':'forward'
  const order=[...primary,...connections,{path:'/tools'},{path:'/storage'},{path:'/system'}].map(item=>item.path)
  return order.indexOf(normalizedPath(to))<order.indexOf(normalizedPath(from))?'back':'forward'
}
export function NavigationLinks({current,hasProject,projectId,onNavigate}:{current:string;hasProject:boolean;projectId?:string;onNavigate:()=>void}){
  if(['/reports','/preparation'].includes(current))current='/testing'
  const items=(list:typeof primary)=>list.map(item=><a className="jj-nav-item" key={item.path} href={'#'+scopedPath(item.path,projectId)} onPointerEnter={()=>preloadRoute(item.path)} onFocus={()=>preloadRoute(item.path)} aria-current={current===item.path?'page':undefined} onClick={onNavigate}>{item.icon}<span className="jj-nav-label" data-short={/^[\u4e00-\u9fff]{2}$/.test(item.label)||undefined}>{item.label}</span></a>)
  return <div className="jj-nav-groups"><nav aria-label="应用工作区">{items(hasProject?primary.filter(item=>item.path!=='/application'):primary.filter(item=>item.path==='/application'))}</nav>{hasProject&&<nav className="jj-nav-context" aria-label="应用资料">{items(primary.filter(item=>item.path==='/application'))}</nav>}</div>
}
export function Breadcrumbs({route,projectName,projectId}:{route:Route;projectName?:string;projectId?:string}){
  const setting=settingsSection(route)
  const collaboration=route.path==='/workspace'&&route.query.get('view')==='collaboration'
  const current=normalizedPath(route),section=[...primary,...connections,{path:'/reports',label:'运行记录'},{path:'/preparation',label:'测试准备'},{path:'/tools',label:'开发工具'},{path:'/changes',label:'源码修改'},{path:'/storage',label:'本地存储'},{path:'/system',label:'运行与维护'},{path:'/archive',label:'归档记录'}].find(item=>item.path===current)
  const detail=current==='/reports'?route.query.has('run_id')?'报告详情':route.query.get('view')==='plan'?'检查范围':undefined
    :current==='/permissions'&&route.query.has('proposal_id')?'审阅权限变更'
    :current==='/permissions'&&route.query.has('rule_id')?'规则详情'
    :current==='/preparation'?route.query.has('identities')?'测试账号':route.query.has('proof_sources')||route.query.has('source_id')?'证明来源':undefined

    :current==='/changes'&&route.query.get('view')==='register'?'登记修改'
    :current==='/archive'&&route.query.has('run_id')?'报告详情':undefined
  const global=['/environment','/tools','/storage','/system','/archive'].includes(current)||!projectName
  const parent=current==='/reports'?historyLocation(projectId):current==='/archive'?'/archive?project_id='+encodeURIComponent(route.query.get('project_id')??''):section?.path
  const levels=setting?[{label:'界鉴',href:'#'+scopedPath('/workspace',projectId)},{label:'设置',href:'#'+scopedPath('/settings',projectId)},{label:settingsSections.find(item=>item.key===setting)!.label,href:undefined}]:[{label:global?'界鉴':projectName!,href:'#'+scopedPath('/workspace',projectId)},...(current==='/archive'?[{label:'官方示例',href:'#/environment'}]:[]),...(section?[{label:collaboration?'Agent 协作':section.label,href:detail&&parent?'#'+scopedPath(parent,projectId):undefined}]:[]),...(detail?[{label:detail,href:undefined}]:[])]
  return <nav className="jj-breadcrumb" aria-label="当前位置"><ol>{levels.map((item,index)=><li key={index}>{index>0&&<span className="jj-breadcrumb-separator" aria-hidden="true">/</span>}{item.href?<a href={item.href}>{item.label}</a>:<span aria-current="page">{item.label}</span>}</li>)}</ol></nav>
}
