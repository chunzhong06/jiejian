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
  for(const key of ['action_id','rule_id','candidate_id','run_id','case_id','change_id','source_id','recording_id','flow_id','revision','material_kind','request_id']){
    const value=query.get(key);if(value)references[key]=value
  }
  const safe=new URLSearchParams(references)
  references.return_to=path+(safe.size?'?'+safe:'')
  return references
}

// 原始表单只保留于本次文档内存；导航接续不会将参数值写入数据库或浏览器存储。
const drafts=new Map<string,unknown>()
export function editorDraft<T>(key:string){return drafts.get(key) as T|undefined}
export function rememberEditorDraft<T>(key:string,value:T){drafts.set(key,value)}
