import {routeDefinition,routeAliases,type RouteDefinition} from '../shared/lib/routes'
import {routePage} from '../shared/lib/routePage'
import {PageSkeleton} from '../shared/ui/PageSkeleton'
import type { ProjectDto } from '../entities/application/api/projects';
import type { OfficialExperienceDto } from '../entities/application/api/experience';
import type { WorkspaceViewDto } from '../entities/workspace/api/workspace';
import type { PageProps } from '../shared/model/page';
import type { Route } from '../shared/lib/navigation';
import {scopedPath} from '../shared/lib/navigation'
import {ActionLink} from '../shared/ui/actions'
import { Empty } from "../shared/ui/feedback";
import { Heading } from "../shared/ui/layout";
import {SettingsWorkspace} from './shell/SettingsWorkspace'
import {settingsSection} from '../shared/lib/settings'
const overview = () => import('../pages/overview/Home'), permissions = () => import('../pages/permissions/Permissions'), preparation = () => import('../pages/preparation/Preparation'), checks = () => import('../pages/checks/Reports'), connection = () => import('../pages/connections/Connect'), changes = () => import('../pages/changes/Changes'), tools = () => import('../pages/tools/Agent'), storage = () => import('../pages/storage/Storage'), archive = () => import('../pages/checks/ArchivedExample');
const Home = routePage(() => overview().then(module => ({ default: module.Home })),'/workspace'), Permissions = routePage(() => permissions().then(module => ({ default: module.Permissions })),'/permissions'), Preparation = routePage(() => preparation().then(module => ({ default: module.Preparation })),'/preparation'), Reports = routePage(() => checks().then(module => ({ default: module.Reports })),'/reports'), Connect = routePage(() => connection().then(module => ({ default: module.Connect })),'/application'), Changes = routePage(() => changes().then(module => ({ default: module.Changes })),'/changes'), Agent = routePage(() => tools().then(module => ({ default: module.Agent })),'/tools'), Storage = routePage(() => storage().then(module => ({ default: module.Storage })),'/storage'), ArchivedExample = routePage(() => archive().then(module => ({ default: module.ArchivedExample })),'/archive');
const System = routePage(() => import('../pages/system/System').then(module=>({default:module.System})),'/system');
const ApplicationWorkbench = routePage(() => import('../pages/connections/ApplicationWorkbench').then(module=>({default:module.ApplicationWorkbench})),'/application');
const Testing = routePage(() => import('../pages/testing/Testing').then(module=>({default:module.Testing})),'/testing');
const Issues = routePage(() => import('../pages/issues/Issues').then(module=>({default:module.Issues})),'/issues');
const Collaboration = routePage(() => import('../pages/tools/Collaboration').then(module=>({default:module.Collaboration})),'/workspace');
const CollaborationHub = routePage(() => import('../pages/tools/CollaborationHub').then(module=>({default:module.CollaborationHub})),'/workspace');
const CheckWorkspace=routePage(()=>import('./CheckWorkspace').then(module=>({default:module.CheckWorkspace})),'/reports');
const loaders: Record<RouteDefinition['preload'], () => Promise<unknown>> = {system:System.preload,home:Home.preload,permissions:Permissions.preload,preparation:Preparation.preload,reports:Reports.preload,application:ApplicationWorkbench.preload,testing:Testing.preload,issues:Issues.preload,environment:Connect.preload,changes:Changes.preload,tools:Agent.preload,storage:Storage.preload,archive:ArchivedExample.preload};
export function preloadRoute(path: string) {
    const [pathname,search]=path.split('?'),route={path:routeAliases[pathname]??pathname,query:new URLSearchParams(search)}
    if(route.path==='/reports'&&route.query.get('view')==='plan'){void CheckWorkspace.preload();return;}
    const key=settingsSection(route)??routeDefinition(route.path)?.preload
    if(key)void loaders[key]?.().catch(()=>{})
}
type Props = {
    current: string;
    route: Route;
    context: PageProps | null;
    project?: ProjectDto;
    loading: boolean;
    workspace: WorkspaceViewDto | null;
    environment?: OfficialExperienceDto;
    onConnected: (id: string) => void;
    onError: (error: unknown) => void;
};
export function RouteContent({ current, route, context, project, loading, workspace, environment, onConnected, onError }: Props) {
    if (current === '/workspace' && route.query.get('view') === 'collaboration' && context && route.query.get('task_id'))
        return <Collaboration key={route.query.get('task_id')} projectId={context.projectId} taskId={route.query.get('task_id')!}/>;
    if (current === '/workspace' && route.query.get('view') === 'collaboration' && context)
        return <CollaborationHub projectId={context.projectId}/>;
    const setting=settingsSection(route)
    if(setting)return <SettingsWorkspace onPreload={preloadRoute} route={route} projectId={project?.project_id}>{setting==='tools'?<Agent key={project?.project_id} projectId={project?.project_id} name={project?.name} onError={onError} embedded/>:setting==='storage'?<Storage embedded/>:<System route={route} projectId={project?.project_id} embedded/>}</SettingsWorkspace>;
    if (current === '/archive')
        return <ArchivedExample route={route} onError={onError}/>;
    if (current === '/application' && (project || route.query.get('view') !== 'source'))
        return <ApplicationWorkbench key={route.query.get('view')==='create'?'create':project?.project_id} selected={route.query.get('view')==='create'?undefined:project} existingProjectId={project?.project_id} onChanged={onConnected}/>;
    if (current === '/application' || current === '/environment')
        return <Connect key={project?.project_id} mode={current === '/environment' ? 'environment' : 'application'} selected={project} environment={environment} onChanged={onConnected} onError={onError}/>;
    if (loading && !project)
        return <PageSkeleton view={current}/>;
    if (!context)
        return <Welcome />;
    if (current === '/workspace')
        return <Home {...context} workspace={workspace} experience={environment ?? null}/>;
    if (current === '/permissions')
        return <Permissions key={context.projectId} {...context}/>;
    if (current === '/testing') return <Testing key={context.projectId} {...context}/>;
    if (current === '/issues') return <Issues key={context.projectId} {...context}/>;
    if (current === '/preparation')
        return <Preparation key={context.projectId} {...context}/>;
    if (current === '/reports' && route.query.get('view')==='plan' && project)
        return <CheckWorkspace {...context} project={project}/>;
    if (current === '/reports')
        return <Reports key={context.projectId} {...context}/>;
    if (current === '/changes')
        return <Changes key={context.projectId} {...context} workspace={workspace}/>;
    return <Empty title="从当前应用继续" action={<ActionLink navigationScope="page" href={'#'+scopedPath('/workspace')}  kind="default">打开应用概览</ActionLink>}/>;
}
function Welcome() { return <><Heading eyebrow="界鉴" title="检查应用的访问权限"/><div className="jj-welcome-grid"><section className="jj-welcome-main"><span className="jj-line-symbol" aria-hidden="true">[ ]</span><h2>从你的应用开始</h2><p>先明确谁可以操作哪些数据，再用测试账号验证实际行为。每次检查都会保留结果与判断依据。</p><footer className="jj-welcome-actions"><ActionLink navigationScope="page" href={'#'+scopedPath('/application')} kind="primary">连接应用</ActionLink></footer></section><section className="jj-welcome-example"><p className="jj-eyebrow">首次使用</p><h2>先试一次完整检查</h2><p>使用内置数字展馆走完一次权限检查，无需准备自己的应用。</p><footer className="jj-welcome-actions"><ActionLink navigationScope="page" href={'#'+scopedPath('/environment')}  kind="default">打开示例</ActionLink></footer></section></div></>; }
