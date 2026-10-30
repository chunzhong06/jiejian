import {useEffect,useState} from 'react'
import {projectsApi} from '../../entities/application/api/projects'
import {experienceApi} from '../../entities/application/api/experience'
import {workspaceApi} from '../../entities/workspace/api/workspace'
import {currentChecksApi} from '../../entities/check/api/currentChecks'
import {assertProject} from '../../shared/model/page'
import {go,type Route} from '../../shared/lib/navigation'
import {useRead} from '../../shared/lib/useRead'

export function useApplication(current:string,route:Route){
  const [selected,setSelected]=useState(()=>localStorage.getItem('jiejian.studio.project')??'')
  const projects=useRead('applications',projectsApi.projects)
  const environment=useRead('environment',signal=>experienceApi.status(undefined,true,signal),3000)
  const runId=current==='/reports'?route.query.get('run_id'):null
  const legacy=useRead(runId&&!route.query.has('project_id')?'report-owner:'+runId:null,async()=>runId?currentChecksApi.status(runId):null)
  const requested=current==='/archive'?undefined:route.query.get('project_id')??legacy.data?.run.project_id
  // 显式链接中的项目优先于上次选择；历史报告先解析所属项目，不能套用当前应用的工作区。
  const scope=requested??selected
  const known=projects.data?.find(item=>item.project_id===scope)
  const resolved=useRead(requested&&!known?'application-owner:'+requested:null,()=>projectsApi.project(requested!))
  const project=known??(requested?resolved.data:projects.data?.[0])
  useEffect(()=>{
    if(project?.status==='ARCHIVED'&&current!=='/archive'&&runId){const query=new URLSearchParams(route.query);query.set('project_id',project.project_id);go('/archive?'+query)}
    else if(legacy.data&&!route.query.has('project_id')){const query=new URLSearchParams(route.query);query.set('project_id',legacy.data.run.project_id);go(route.path+'?'+query)}
  },[project?.project_id,project?.status,legacy.data,runId,current])
  // 仅需要完整投影的页面读取工作区，准备和账号页面各自加载轻量事实，避免被无关历史阻塞。
  const needsWorkspace=['/workspace','/changes'].includes(current)
  const workspace=useRead(needsWorkspace&&project?'workspace:'+project.project_id:null,async signal=>{
    if(!project)return null
    const value=await workspaceApi.current(project.project_id,signal)
    assertProject(value.project.project_id,project.project_id)
    return value
  },value=>value?.active_check?2000:10000)
  useEffect(()=>{if(project)localStorage.setItem('jiejian.studio.project',project.project_id)},[project?.project_id])
  const choose=(id:string)=>{setSelected(id);go('/workspace',id)}
  const refresh=()=>{workspace.reload();projects.reload();environment.reload()}
  const connected=(id:string)=>{projects.reload();setSelected(id);environment.reload();go('/workspace',id)}
  return {project,projects,environment,workspace,choose,refresh,connected,resolutionError:legacy.error??resolved.error,resolving:legacy.loading||resolved.loading}
}
