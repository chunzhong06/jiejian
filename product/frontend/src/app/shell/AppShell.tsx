import {useEffect,useState,type ReactNode} from 'react'
import MenuOutlined from '@ant-design/icons/MenuOutlined';
import MoonOutlined from '@ant-design/icons/MoonOutlined';
import SunOutlined from '@ant-design/icons/SunOutlined';
import ReloadOutlined from '@ant-design/icons/ReloadOutlined';
import {refreshCurrentPage} from '../../shared/lib/pageRefresh'
import type {ProjectDto} from '../../entities/application/api/projects'
import {scopedPath,type Route} from '../../shared/lib/navigation'
import {Button} from '../../shared/ui/actions'
import {Dialog} from '../../shared/ui/Dialog'
import {Breadcrumbs,NavigationLinks} from '../Navigation'
import {Shutdown} from '../Shutdown'
import {SettingsEntry} from './SettingsEntry'
import {Activity} from './Activity'
import {CollaborationEntry} from '../../entities/runtime/ui/CollaborationEntry'
import {ApplicationSwitcher} from './ApplicationSwitcher'

type Props={route:Route;current:string;project?:ProjectDto;projects?:ProjectDto[];choose:(id:string)=>void;appearance:'light'|'dark';toggleAppearance:()=>void;children:ReactNode}

export function AppShell({route,current,project,projects,choose,appearance,toggleAppearance,children}:Props){
  const [mobile,setMobile]=useState(false)
  const [refreshing,setRefreshing]=useState(false)
  const [collaborationHost,setCollaborationHost]=useState<HTMLElement|null>(null)
  const collaborationPage=current==='/workspace'&&route.query.get('view')==='collaboration'
  useEffect(()=>{setMobile(false)},[route.path,route.query.toString()])
  const close=()=>setMobile(false)
  const navigation=<>
    <a className="jj-brand" href={'#'+scopedPath('/workspace',project?.project_id)} onClick={close}><span className="jj-brand-symbol" aria-hidden="true"/><strong>界鉴</strong></a>
    <ApplicationSwitcher project={project} projects={projects} choose={choose}/>
    <NavigationLinks current={collaborationPage?'/collaboration':current} hasProject={Boolean(project)} projectId={project?.project_id} onNavigate={close}/>
    {project&&<nav className="jj-sidebar-collaboration" aria-label="Agent协作" ref={setCollaborationHost}/>}
    {project&&<Activity key={project.project_id} projectId={project.project_id}/>}
    <nav className="jj-sidebar-settings" aria-label="设置入口"><SettingsEntry current={current} projectId={project?.project_id} onNavigate={close}/></nav>
  </>
  return <div className="jj-app">
    <a className="jj-skip" href="#jj-content" onClick={event=>{event.preventDefault();document.getElementById('jj-content')?.focus()}}>跳到正文</a>
    <aside className="jj-sidebar">{!mobile&&navigation}</aside>
    {mobile&&<Dialog title="界鉴导航" onClose={close}><div className="jj-mobile-nav">{navigation}</div></Dialog>}
    {project&&<CollaborationEntry key={project.project_id} projectId={project.project_id} route={route.path+'?'+route.query.toString()} viewedTaskId={collaborationPage?route.query.get('task_id'):null} portalHost={collaborationHost} onNavigate={close}/>}
    <div className="jj-main">
      <header className="jj-topbar">
        <Button kind="quiet" className="jj-mobile-toggle" aria-label="打开导航" icon={<MenuOutlined aria-hidden="true"/>} onClick={()=>setMobile(true)}/>
        <Breadcrumbs route={route} projectName={project?.name} projectId={project?.project_id}/>
        <nav className="jj-toolbar" aria-label="全局工具">
          <Button kind="quiet" aria-label="刷新当前界面" tip="刷新当前界面" busy={refreshing} icon={<ReloadOutlined aria-hidden="true"/>} onClick={()=>{setRefreshing(true);void refreshCurrentPage().finally(()=>setRefreshing(false))}}/>
          <Button kind="quiet" aria-label={appearance==='light'?'切换雾蓝深色':'切换浅色'} title={appearance==='light'?'雾蓝深色':'浅色'} icon={appearance==='light'?<MoonOutlined aria-hidden="true"/>:<SunOutlined aria-hidden="true"/>} onClick={toggleAppearance}/>
          <Shutdown compact/>
        </nav>
      </header>
      <main id="jj-content" tabIndex={-1} className="jj-content">{children}</main>
    </div>
  </div>
}
