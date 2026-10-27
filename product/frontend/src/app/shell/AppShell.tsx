import {useEffect,useState,type ReactNode} from 'react'
import {DatabaseOutlined,MenuOutlined,MoonOutlined,SunOutlined} from '@ant-design/icons'
import type {ProjectDto} from '../../entities/application/api/projects'
import type {Route} from '../../shared/lib/navigation'
import {Button} from '../../shared/ui/actions'
import {Choice} from '../../shared/ui/Choice'
import {Dialog} from '../../shared/ui/Dialog'
import {Breadcrumbs,NavigationLinks} from '../Navigation'
import {preloadRoute} from '../Router'
import {Shutdown} from '../Shutdown'
import {RuntimeStatus} from './RuntimeStatus'

type Props={route:Route;current:string;project?:ProjectDto;projects?:ProjectDto[];choose:(id:string)=>void;appearance:'light'|'dark';toggleAppearance:()=>void;children:ReactNode}

export function AppShell({route,current,project,projects,choose,appearance,toggleAppearance,children}:Props){
  const [mobile,setMobile]=useState(false)
  useEffect(()=>setMobile(false),[route.path,route.query.toString()])
  const close=()=>setMobile(false)
  const navigation=<>
    <a className="jj-brand" href="#/workspace" onClick={close}><span className="jj-brand-symbol" aria-hidden="true"/><strong>界鉴</strong></a>
    <div className="jj-project-select"><label htmlFor="jj-project">当前应用</label><Choice id="jj-project" value={project?.project_id??''} onValueChange={choose}>
      {!project&&<option value="">尚未连接应用</option>}
      {projects?.map(item=><option value={item.project_id} key={item.project_id}>{item.name??'未命名应用'}</option>)}
    </Choice></div>
    <NavigationLinks current={current} hasProject={Boolean(project)} onNavigate={close}/>
    <nav className="jj-sidebar-bottom" aria-label="本地维护">
      <a className="jj-nav-item" href="#/storage" onPointerEnter={()=>preloadRoute('/storage')} onFocus={()=>preloadRoute('/storage')} aria-current={current==='/storage'?'page':undefined} onClick={close}><DatabaseOutlined aria-hidden="true"/><span>本地存储</span></a>
      <Shutdown/>
    </nav>
  </>
  return <div className="jj-app">
    <a className="jj-skip" href="#jj-content" onClick={event=>{event.preventDefault();document.getElementById('jj-content')?.focus()}}>跳到正文</a>
    <aside className="jj-sidebar">{!mobile&&navigation}</aside>
    {mobile&&<Dialog title="界鉴导航" onClose={close}><div className="jj-mobile-nav">{navigation}</div></Dialog>}
    <div className="jj-main">
      <header className="jj-topbar">
        <Button kind="quiet" className="jj-mobile-toggle" aria-label="打开导航" icon={<MenuOutlined aria-hidden="true"/>} onClick={()=>setMobile(true)}/>
        <Breadcrumbs route={route} projectName={project?.name} projectId={project?.project_id}/>
        <div className="jj-toolbar"><Button kind="quiet" aria-label={appearance==='light'?'切换雾蓝深色':'切换浅色'} title={appearance==='light'?'雾蓝深色':'浅色'} icon={appearance==='light'?<MoonOutlined aria-hidden="true"/>:<SunOutlined aria-hidden="true"/>} onClick={toggleAppearance}/><span className="jj-toolbar-divider" aria-hidden="true"/><RuntimeStatus/></div>
      </header>
      <main id="jj-content" tabIndex={-1} className="jj-content">{children}</main>
    </div>
  </div>
}
