import {useEffect,useState} from 'react'
import {projectsApi} from '../../entities/application/api/projects'
import {experienceApi} from '../../entities/application/api/experience'
import {workspaceApi} from '../../entities/workspace/api/workspace'
import {assertProject} from '../../shared/model/page'
import {go} from '../../shared/lib/navigation'
import {useRead} from '../../shared/lib/useRead'

export function useApplication(current:string){
  const [selected,setSelected]=useState(()=>localStorage.getItem('jiejian.studio.project')??'')
  const projects=useRead('applications',projectsApi.projects)
  const environment=useRead('environment',signal=>experienceApi.status(undefined,true,signal),3000)
  const project=projects.data?.find(item=>item.project_id===selected)??projects.data?.[0]
  const needsWorkspace=['/workspace','/changes'].includes(current)
  const workspace=useRead(needsWorkspace&&project?'workspace:'+project.project_id:null,async signal=>{
    if(!project)return null
    const value=await workspaceApi.current(project.project_id,signal)
    assertProject(value.project.project_id,project.project_id)
    return value
  },value=>value?.active_check?2000:10000)
  useEffect(()=>{if(project)localStorage.setItem('jiejian.studio.project',project.project_id)},[project?.project_id])
  const choose=(id:string)=>{setSelected(id);go('/workspace')}
  const refresh=()=>{workspace.reload();projects.reload();environment.reload()}
  const connected=(id:string)=>{projects.reload();setSelected(id);environment.reload();go('/workspace')}
  return {project,projects,environment,workspace,choose,refresh,connected}
}
