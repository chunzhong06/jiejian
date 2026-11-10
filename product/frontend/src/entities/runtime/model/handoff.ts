import {useEffect,useSyncExternalStore} from 'react'
import type {CollaborationEditor,CollaborationPurpose} from '../api/collaboration'

export type HandoffContext={projectId:string;label:string;references:Record<string,string>;editor?:CollaborationEditor}
const contexts=new Map<symbol,HandoffContext>(),listeners=new Set<()=>void>()
const notify=()=>listeners.forEach(listener=>listener())
const subscribe=(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener)}}
export function useHandoffContext(value:HandoffContext|undefined){
  const identity=JSON.stringify(value)
  useEffect(()=>{
    if(!value)return
    const token=Symbol();contexts.set(token,value);notify()
    return()=>{contexts.delete(token);notify()}
  },[identity])
}
export function useCurrentHandoff(projectId:string){
  return useSyncExternalStore(subscribe,()=>{const active=[...contexts.values()].reverse().filter(item=>item.projectId===projectId);return active.find(item=>item.editor)??active[0]})
}
export function requestCollaboration(projectId:string,purpose:CollaborationPurpose,goal:string,newTask=false){
  window.dispatchEvent(new CustomEvent('jiejian:collaboration-compose',{detail:{projectId,purpose,goal,newTask}}))
}
export function routeReferences(route:string){
  const [path,search]=route.split('?'),query=new URLSearchParams(search),references:Record<string,string>={}
  // 只交接已知对象与回程，URL 中的任意查询字段不进入协作历史。
  for(const key of ['action_id','rule_id','candidate_id','run_id','case_id','change_id','source_id','recording_id','flow_id','revision','material_kind','request_id','scope_id','scenario_id','scenario_revision','routine_id','routine_revision','binding_id','repair_reference','issue','section','effect_id']){
    const value=query.get(key);if(value)references[key]=value
  }
  if(['plan','compare','plans','repair','collaboration','environment','source','sources','business','register'].includes(query.get('view')??''))references.view=query.get('view')!
  for(const key of ['identities','proof_sources','resume_draft'])if(query.get(key)==='1')references[key]='1'
  if(['new','edit'].includes(query.get('configure')??''))references.configure=query.get('configure')!
  const safe=new URLSearchParams(references)
  references.return_to=path+(safe.size?'?'+safe:'')
  return references
}

// 原始表单只保留于本次文档内存；导航接续不会将参数值写入数据库或浏览器存储。
const drafts=new Map<string,{project:string;value:unknown;generation:number}>()
let generation=0
export function editorDraft<T>(key:string,project:string){const entry=drafts.get(key);return entry?.project===project?entry.value as T:undefined}
export function rememberEditorDraft<T>(key:string,value:T,project?:string){
  if(value===undefined){drafts.delete(key);return}
  if(!project)throw new Error('编辑草稿必须声明所属应用')
  if(drafts.get(key)?.value!==value)drafts.set(key,{project,value,generation:++generation})
}
export function discardProjectEditorDrafts(project:string){
  for(const [key,entry] of drafts)if(entry.project===project)drafts.delete(key)
}

/** 迟到保存只清提交时的草稿；同一对象之后的编辑仍保留。 */
export function editorDraftGeneration(key:string,project:string){const value=drafts.get(key);return value?.project===project?value.generation:undefined}
export function clearSubmittedDraft(key:string,project:string,submitted:number|undefined){const entry=drafts.get(key);if(entry?.project===project&&entry.generation===submitted)drafts.delete(key)}
export function useDraftProtection(dirty:boolean){
  useEffect(()=>{if(!dirty)return;const protect=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=''};window.addEventListener('beforeunload',protect);return()=>window.removeEventListener('beforeunload',protect)},[dirty])
}
