import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { ArrowLeftOutlined } from '@ant-design/icons';
import { projectsApi } from '../../entities/application/api/projects';
import { assertProject } from '../../shared/model/page';
import { useRead } from '../../shared/lib/useRead';
import { type Route } from '../../shared/lib/navigation';
import { ActionLink } from "../../shared/ui/actions";
import { ErrorNote, Notice } from "../../shared/ui/feedback";
import { Reports } from './Reports';
export function ArchivedExample({ route, onError }: {
    route: Route;
    onError: (error: unknown) => void;
}) {
    const id = route.query.get('project_id') ?? '';
    const state = useRead('archived-example:' + id, async (signal) => { if (!id)
        throw new Error('未指定归档项目。'); const value = (await projectsApi.archivedProjects(signal)).find(item => item.project_id === id); if (!value || value.status !== 'ARCHIVED')
        throw new Error('指定项目不属于已归档项目。'); assertProject(value.project_id, id); return value; });
    if (state.loading)
        return <PageSkeleton view="/archive"/>;
    if (!state.data || state.error)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    return <><Notice tone="neutral"><span>已归档：{state.data.name ?? '数字展馆'}</span><ActionLink href="#/environment"><ArrowLeftOutlined aria-hidden="true"/>返回官方示例</ActionLink></Notice><Reports key={id} archive projectId={id} name={state.data.name ?? '数字展馆'} official route={route} refresh={() => { }} onError={onError}/></>;
}
