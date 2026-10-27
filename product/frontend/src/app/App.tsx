import {useEffect,useRef,useState} from 'react'
import {CloseOutlined} from '@ant-design/icons'
import {Button} from '../shared/ui/actions'
import {ErrorNote} from '../shared/ui/feedback'
import {commitPageTransition} from '../shared/lib/pageTransition'
import {PageSurface} from '../shared/ui/PageSurface'
import {readRoute} from '../shared/lib/navigation'
import {trackInputMode} from '../shared/lib/inputMode'
import {normalizedPath,pageTransitionKey,navigationDirection} from './Navigation'
import {RouteContent} from './Router'
import {RouteBoundary} from './RouteBoundary'
import {UIProvider} from './providers/UIProvider'
import {useAppearance} from './model/useAppearance'
import {useApplication} from './model/useApplication'
import {AppShell} from './shell/AppShell'
import './styles.css'

export default function App(){
  useEffect(trackInputMode,[])
  const [route,setRoute]=useState(readRoute),[error,setError]=useState<unknown>()
  const previousRoute=useRef(route)
  const current=normalizedPath(route)
  const application=useApplication(current)
  const {appearance,toggle}=useAppearance()
  const {project,projects,environment,workspace}=application
  useEffect(()=>{
    const update=()=>{
      const next=readRoute(),previous=previousRoute.current
      previousRoute.current=next
      const updateRoute=()=>{
        setRoute(next);setError(undefined)
        if(next.path!==previous.path||['run_id','rule_id','view','identities','proof_sources','material_kind'].some(key=>next.query.get(key)!==previous.query.get(key)))window.scrollTo({top:0,behavior:'instant'})
      }
      if(pageTransitionKey(next)!==pageTransitionKey(previous))commitPageTransition(updateRoute,navigationDirection(previous,next))
      else updateRoute()
    }
    window.addEventListener('hashchange',update)
    return()=>window.removeEventListener('hashchange',update)
  },[])
  const context=project?{projectId:project.project_id,name:project.name??'未命名应用',official:Boolean(project.official_sample),refresh:application.refresh,onError:setError,route}:null
  const key=pageTransitionKey(route,project?.project_id)
  return <UIProvider appearance={appearance}>
    <AppShell route={route} current={current} project={project} projects={projects.data} choose={application.choose} appearance={appearance} toggleAppearance={toggle}>
      {Boolean(error)&&<div className="jj-global-error"><ErrorNote error={error}/><Button kind="quiet" aria-label="关闭错误提示" icon={<CloseOutlined aria-hidden="true"/>} onClick={()=>setError(undefined)}/></div>}
      {projects.error&&<ErrorNote error={projects.error} onRetry={projects.reload}/>}
      <PageSurface transitionKey={key} view={current+(route.query.has('proposal_id')?'/review':route.query.get('view')==='plan'?'/plan':route.query.has('run_id')?'/result':'')}>
        <RouteBoundary key={key}>
          <RouteContent current={current} route={route} context={context} project={project} loading={projects.loading} workspace={workspace.data??null} environment={environment.data} onConnected={application.connected} onError={setError}/>
        </RouteBoundary>
      </PageSurface>
    </AppShell>
  </UIProvider>
}
