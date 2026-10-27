import {routePage} from './routePage'
import {PageSkeleton} from '../shared/ui/PageSkeleton'
import type { ProjectDto } from '../entities/application/api/projects';
import type { OfficialExperienceDto } from '../entities/application/api/experience';
import type { WorkspaceViewDto } from '../entities/workspace/api/workspace';
import type { PageProps } from '../shared/model/page';
import type { Route } from '../shared/lib/navigation';
import { go } from '../shared/lib/navigation';
import { Button } from "../shared/ui/actions";
import { Empty } from "../shared/ui/feedback";
import { Heading } from "../shared/ui/layout";
const overview = () => import('../pages/overview/Home'), permissions = () => import('../pages/permissions/Permissions'), preparation = () => import('../pages/preparation/Preparation'), checks = () => import('../pages/checks/Reports'), connection = () => import('../pages/connections/Connect'), changes = () => import('../pages/changes/Changes'), tools = () => import('../pages/tools/Agent'), storage = () => import('../pages/storage/Storage'), archive = () => import('../pages/checks/ArchivedExample'), business = () => import('../pages/connections/Understanding');
const Home = routePage(() => overview().then(module => ({ default: module.Home })),'/workspace'), Permissions = routePage(() => permissions().then(module => ({ default: module.Permissions })),'/permissions'), Preparation = routePage(() => preparation().then(module => ({ default: module.Preparation })),'/preparation'), Reports = routePage(() => checks().then(module => ({ default: module.Reports })),'/reports'), Connect = routePage(() => connection().then(module => ({ default: module.Connect })),'/application'), Changes = routePage(() => changes().then(module => ({ default: module.Changes })),'/changes'), Agent = routePage(() => tools().then(module => ({ default: module.Agent })),'/tools'), Storage = routePage(() => storage().then(module => ({ default: module.Storage })),'/storage'), ArchivedExample = routePage(() => archive().then(module => ({ default: module.ArchivedExample })),'/archive'), Understanding = routePage(() => business().then(module => ({ default: module.Understanding })),'/application');
const loaders: Record<string, () => Promise<unknown>> = { '/workspace': Home.preload, '/permissions': Permissions.preload, '/preparation': Preparation.preload, '/reports': Reports.preload, '/application': Connect.preload, '/environment': Connect.preload, '/changes': Changes.preload, '/tools': Agent.preload, '/storage': Storage.preload, '/archive': ArchivedExample.preload };
export function preloadRoute(path: string) { void loaders[path]?.().catch(() => { }); }
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
    if (current === '/tools')
        return <Agent key={project?.project_id} projectId={project?.project_id} name={project?.name} onError={onError}/>;
    if (current === '/storage')
        return <Storage />;
    if (current === '/archive')
        return <ArchivedExample route={route} onError={onError}/>;
    if (current === '/application' && route.query.get('view') === 'business' && context)
        return <Understanding projectId={context.projectId} onError={onError}/>;
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
    if (current === '/preparation')
        return <Preparation key={context.projectId} {...context}/>;
    if (current === '/reports')
        return <Reports key={context.projectId} {...context}/>;
    if (current === '/changes')
        return <Changes key={context.projectId} {...context} workspace={workspace}/>;
    return <Empty title="从当前应用继续" action={<Button onClick={() => go('/workspace')}>打开应用概览</Button>}/>;
}
function Welcome() { return <><Heading eyebrow="界鉴" title="检查应用的访问权限"/><div className="jj-welcome-grid"><section className="jj-welcome-main"><span className="jj-line-symbol" aria-hidden="true">[ ]</span><h2>从你的应用开始</h2><p>连接应用，约定访问规则，再用真实操作验证业务结果。</p><Button kind="primary" onClick={() => go('/application')}>连接应用</Button></section><section className="jj-welcome-example"><p className="jj-eyebrow">首次使用</p><h2>先试一次完整检查</h2><p>用独立数字展馆体验权限审阅、材料准备和结果核对。</p><Button onClick={() => go('/environment')}>打开示例</Button></section></div></>; }
