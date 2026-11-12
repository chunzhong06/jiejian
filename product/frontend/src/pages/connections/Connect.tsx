import {useWorkflow} from '../../shared/lib/workflow'
import './styles.css'
import { useEffect, useRef, useState } from 'react';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import CodeOutlined from '@ant-design/icons/CodeOutlined';
import FolderOpenOutlined from '@ant-design/icons/FolderOpenOutlined';
import AppstoreOutlined from '@ant-design/icons/AppstoreOutlined';
import DownOutlined from '@ant-design/icons/DownOutlined';
import ReloadOutlined from '@ant-design/icons/ReloadOutlined';
import PauseOutlined from '@ant-design/icons/PauseOutlined';
import PlusOutlined from '@ant-design/icons/PlusOutlined';
import { CommandMenu } from '../../shared/ui/CommandMenu';
import { type OfficialExperienceDto } from '../../entities/application/api/experience';
import { projectsApi, type ProjectDto, type ConnectionPreview, type ConnectionChoice } from '../../entities/application/api/projects';
import {selectFolderPath} from '../../entities/application/api/onboarding';
import {DirectoryField} from '../../shared/ui/DirectoryField';
import { ApiError } from '../../shared/api/http';
import { operationId, readPending, savePending } from '../../shared/lib/operations';
import { assertProject } from '../../shared/model/page';
import { date } from '../../shared/lib/format';
import {go,readRoute,returnDestination,scopedPath} from '../../shared/lib/navigation'
import { useRead } from '../../shared/lib/useRead';
import {ActionLink,Button} from '../../shared/ui/actions'
import { Heading } from "../../shared/ui/layout";
import { Badge, Loading, Notice, ErrorNote } from "../../shared/ui/feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { ExampleLab } from './ExampleLab';
import {TaskSurface} from '../../shared/ui/TaskSurface'
import { RuntimeConnection } from './RuntimeConnection';
import { Capabilities } from './Capabilities';
import { useExampleLifecycle } from './exampleLifecycle';
export function Connect({ selected, environment, mode = 'application', embedded = false, onSourceBack, onRuntimeFocus, onChanged, onError }: {
    selected?: ProjectDto;
    environment?: OfficialExperienceDto;
    mode?: 'application' | 'environment';
    embedded?: boolean;
    onSourceBack?: () => void;
    onRuntimeFocus?: (active:boolean) => void;
    onChanged: (id: string) => void;
    onError: (error: unknown) => void;
}) {
    const workflow=useWorkflow(),route=workflow?.route??readRoute();
    const [directory, setDirectory] = useState(''), [preview, setPreview] = useState<ConnectionPreview>(), [busy, setBusy] = useState(false), [consent, setConsent] = useState(false), [startConfirm, setStartConfirm] = useState<'restart' | 'reset' | 'stop'>(), [connecting, setConnecting] = useState(!selected);
    const guard = useRef(false);
    const pendingKey = 'jiejian.studio.connection';
    type PendingConnection = { source: string; choice: ConnectionChoice };
    const [pending, setPending] = useState(() => readPending<PendingConnection>(pendingKey));
    const connect = async (source: string, choice: ConnectionChoice) => {
        const saved = { source, choice };
        savePending(pendingKey, saved); setPending(saved);
        try {
            const result = await projectsApi.connectApplication(source, undefined, choice);
            savePending(pendingKey, undefined); setPending(undefined);
            onChanged(result.project.project_id);
        } catch (error) {
            if (error instanceof ApiError) { savePending(pendingKey, undefined); setPending(undefined); }
            throw error;
        }
    };
    const recoverConnection = async () => {
        if (!pending) return;
        const id = pending.choice.mode === 'NEW' ? 'app_' + pending.choice.operation_id : pending.choice.existing_project_id;
        try {
            const project = id ? await projectsApi.project(id) : null;
            if (project && project.status !== 'ARCHIVED') { savePending(pendingKey, undefined); setPending(undefined); onChanged(project.project_id); return; }
            if (project?.status === 'ARCHIVED' && pending.choice.mode === 'NEW') { savePending(pendingKey, undefined); setPending(undefined); throw new Error('原连接建立的项目已归档，请重新选择连接方式。'); }
        } catch (error) { if (!(error instanceof ApiError && error.code === 'PROJECT_NOT_FOUND')) throw error; }
        await connect(pending.source, pending.choice);
    };
    const current = useRead('connect:' + selected?.project_id, async () => { if (!selected)
        return null; const value = await projectsApi.understanding(selected.project_id); assertProject(value.project_id, selected.project_id); return value; });
    const lifecycle = useExampleLifecycle(environment, onChanged, onError), official = lifecycle.official;
    const archives = useRead(mode === 'environment' ? 'example-archives' : null, async () => { const values = await projectsApi.archivedProjects(); return values.filter(item => item.official_sample && item.status === 'ARCHIVED'); });
    const act = async (callback: () => Promise<unknown>) => { if (guard.current)
        return; guard.current = true; setBusy(true); try {
        await callback();
    }
    catch (error) {
        onError(error);
    }
    finally {
        guard.current = false;
        setBusy(false);
    } };
    const resumable = Boolean(official?.workspace_retained && official.history_project_id);
    const value = current.data;
    const exampleProject = official?.project_id ?? (official?.workspace_retained ? official.history_project_id : undefined);
    const returnTo = returnDestination(route.query.get('return_to'));
    const [runtimeOpen,setRuntimeOpen]=useState(route.query.get('runtime_method')==='managed');
    const [runtimeError,setRuntimeError]=useState<unknown>()
    const runtimeActive=runtimeOpen&&Boolean(selected&&value)
    // 运行任务接管标题与返回；父级保留应用分类入口和草稿所有者。
    useEffect(()=>{onRuntimeFocus?.(runtimeActive)},[onRuntimeFocus,runtimeActive])
    useEffect(()=>()=>onRuntimeFocus?.(false),[onRuntimeFocus])
    useEffect(()=>{if(!runtimeOpen)setRuntimeError(undefined)},[runtimeOpen])
    return <><div hidden={runtimeActive}>
    {onSourceBack && <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onSourceBack}>返回应用连接</Button></div>}
    {!embedded && mode === 'application' && returnTo?.startsWith('/preparation') && <div className="jj-back-link"><ActionLink href={'#'+scopedPath(returnTo,selected?.project_id)}><ArrowLeftOutlined aria-hidden="true"/>返回结果证明</ActionLink></div>}
    {!embedded && <Heading title={mode === 'environment' ? '官方示例' : '应用连接'} actions={mode === 'application' && selected && !connecting && <Button onClick={() => setConnecting(true)} icon={<FolderOpenOutlined aria-hidden="true"/>}>连接其他应用</Button>}/>}
    {mode === 'application' ? <>
      {current.loading && selected ? <Loading page>正在读取应用连接</Loading> : value && !connecting && <section className="jj-application-workspace" aria-label="应用连接设置">
        <header className="jj-workspace-header" hidden={embedded}><span className="jj-workspace-symbol"><CodeOutlined aria-hidden="true"/></span><div><p className="jj-eyebrow">当前应用</p><div className="jj-object-line"><h2>{selected?.name ?? '待检查的应用'}</h2><Badge tone={value.confirmed_endpoint ? 'positive' : 'neutral'}>{value.confirmed_endpoint ? '检查地址已设置' : '待设置检查地址'}</Badge></div></div></header>
        <div className="jj-connection-layout"><section className="jj-connection-workbench">
          <section className="jj-source-connection"><h3>识别业务角色与操作</h3><p className="jj-path">{value.source_root}</p>
            <div className="jj-connection-facts"><div><span>源码读取</span><strong>{value.source_analysis_authorized ? '已授权' : '尚未授权'}</strong></div><div><span>识别到的业务</span><strong>{value.analysis_completed_at_us ? value.role_candidates.length + ' 个角色，' + value.action_candidates.length + ' 项操作' : '尚未读取'}</strong></div></div>
            {!value.source_analysis_authorized && <label className="jj-checkbox"><input type="checkbox" checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)}/><span>允许界鉴读取此目录的源码，用于识别业务角色与操作。</span></label>}
            <div className="jj-inline-actions jj-form-actions">
              <Button busy={busy} disabled={!consent && !value.source_analysis_authorized} onClick={() => void act(async () => { let next = await projectsApi.understanding(selected!.project_id); assertProject(next.project_id, selected!.project_id); if (!next.source_analysis_authorized)
                next = await projectsApi.authorizeSourceAnalysis(selected!.project_id, next.revision); await projectsApi.analyzeSource(selected!.project_id, next.revision); current.reload(); go('/application?view=business'); })}>{value.analysis_completed_at_us ? '重新识别业务' : '识别业务角色与操作'}</Button>
              {!embedded && value.analysis_completed_at_us && <ActionLink navigationScope="page" href={'#'+scopedPath('/application?view=business')} kind="quiet">核对业务名称<ArrowRightOutlined aria-hidden="true"/></ActionLink>}
            </div>
          </section>
        {selected&&!selected.official_sample&&<div className="jj-task-actions"><Button disabled={!value.source_analysis_authorized} onClick={()=>setRuntimeOpen(true)}>准备或管理本地运行实例</Button></div>}
      </section>
        {selected && <Capabilities projectId={selected.project_id} revision={value.revision}/>}
      </div>
      </section>}
      {pending && <Notice tone="caution">上次连接尚未确认。继续后会先核对已有记录，必要时沿用原请求完成连接。<Button busy={busy} onClick={() => void act(recoverConnection)}>继续上次连接</Button></Notice>}
      {(connecting || !selected) && <section className="jj-connect-new">
        <header><span className="jj-workspace-symbol"><FolderOpenOutlined aria-hidden="true"/></span><div><h2>连接本地应用</h2><p>选择源码目录，先查看这个目录是否已经关联应用，再决定继续使用或新建。</p></div></header>
        <div className="jj-connect-new-body"><DirectoryField label="项目目录" value={directory} busy={busy} onValueChange={value=>{setDirectory(value);setPreview(undefined)}} onBrowse={()=>void act(async()=>{const path=await selectFolderPath();if(path){setDirectory(path);setPreview(undefined)}})} hint="选择只填入目录。核对连接后，再决定继续已有工作区或建立新工作区。"/><div className="jj-connection-inspection-actions"><Button kind="primary" busy={busy} disabled={!directory.trim()} onClick={() => void act(async () => setPreview(await projectsApi.connectionPreview(directory.trim())))}>查看已有应用</Button></div>
        {preview && <div className="jj-connection-preview"><p className="jj-path">{preview.source_root}</p>{preview.projects.length > 0 && <section><h3>此目录已关联的应用</h3>{preview.projects.map(item => <div className="jj-existing-project" key={item.project_id}><strong>{item.name}</strong><Button busy={busy} disabled={Boolean(pending)} onClick={() => void act(async () => { await connect(preview.source_root, { mode: 'RESUME', existing_project_id: item.project_id, expected_snapshot: preview.snapshot, operation_id: operationId() }); })}>继续使用</Button></div>)}</section>}<div className="jj-connect-new-choice"><span>{preview.projects.length ? '另建项目将使用独立的权限和材料。' : '将为此目录建立独立项目。'}</span><Button kind="primary" busy={busy} disabled={Boolean(pending)} onClick={() => void act(async () => { await connect(preview.source_root, { mode: 'NEW', expected_snapshot: preview.snapshot, operation_id: operationId() }); })}>建立新项目</Button></div></div>}
        </div>{selected && <footer><Button kind="quiet" disabled={busy} onClick={() => setConnecting(false)}>返回当前应用</Button></footer>}
      </section>}
      {current.error && <ErrorNote error={current.error}/>}
    </> : <div className="jj-environment-workspace">
      <section className="jj-example-overview"><header><span className="jj-workspace-symbol"><AppstoreOutlined aria-hidden="true"/></span><div><div className="jj-object-line"><h2>数字展馆</h2><Badge tone={official?.active ? 'positive' : 'neutral'}>{official?.active ? '正在运行' : official?.lifecycle === 'STARTING' ? '正在启动' : '尚未运行'}</Badge></div></div></header><p className="jj-example-description">负责人管理展馆资料，评审访问公开内容。</p>
      <footer>{lifecycle.pending ? <><div className="jj-environment-progress" role="status"><span className="jj-working-dot"/><div><strong>{lifecycle.phase}</strong><p>{lifecycle.pending.kind === 'reset' ? '正在建立全新示例，旧项目与报告保留在归档中。' : '保留当前项目、源码、权限和报告。'}</p></div></div><Button onClick={lifecycle.reload}>查询这次操作</Button></> : official?.active && official.project_id ? <><span className="jj-small jj-muted">源码、权限和报告保存在独立项目中。</span><div className="jj-example-actions"><ExampleManagement active disabled={lifecycle.busy} onChoose={setStartConfirm}/><Button kind="primary" onClick={() => onChanged(official.project_id!)}>进入示例<ArrowRightOutlined aria-hidden="true"/></Button></div></> : <><span className="jj-small jj-muted">{resumable ? '继续使用已保存的源码、权限和报告。' : '将建立本地示例和独立测试数据。'}</span><div className="jj-inline-actions">{resumable && <ExampleManagement disabled={lifecycle.busy || official?.available === false} onChoose={setStartConfirm}/>}<Button kind="primary" disabled={lifecycle.busy || official?.available === false} onClick={() => lifecycle.begin(resumable ? 'resume' : 'start')}>{resumable ? '继续上次示例' : '启动官方示例'}</Button></div></>}</footer>{exampleProject && <nav className="jj-example-workflow" aria-label="示例工作区"><ActionLink presentation="row" href={'#/permissions?project_id=' + encodeURIComponent(exampleProject)}>权限规则<ArrowRightOutlined aria-hidden="true"/></ActionLink><ActionLink presentation="row" href={'#/preparation?project_id=' + encodeURIComponent(exampleProject)}>检查准备<ArrowRightOutlined aria-hidden="true"/></ActionLink><ActionLink presentation="row" href={'#/reports?project_id=' + encodeURIComponent(exampleProject)}>检查记录<ArrowRightOutlined aria-hidden="true"/></ActionLink></nav>}{official?.available === false && <Notice tone="caution"><p>当前无法启动示例。已有项目、权限和报告仍可查看。</p>{official.unavailable_reason&&<p className="jj-small">{official.unavailable_reason}</p>}</Notice>}{lifecycle.unknown && <Notice tone="caution">操作已提交，结果尚未确认。请查询这次操作，不要重复启动。</Notice>}{lifecycle.failure && <Notice tone="caution">{lifecycle.failure}<Button onClick={lifecycle.reload}>读取运行状态</Button></Notice>}{lifecycle.error && <ErrorNote error={lifecycle.error}/>}</section>
      {(archives.data?.length || archives.error) ? <details className="jj-example-archives"><summary>已归档示例 · {archives.data?.length??0} 个</summary>{archives.error ? <ErrorNote error={archives.error}/> : archives.data?.map(item => <article key={item.project_id}><div><h3>{item.name ?? '数字展馆'}</h3>{item.created_at_us && <time className="jj-small jj-muted">{date(item.created_at_us)}</time>}</div><ActionLink href={'#/archive?project_id=' + encodeURIComponent(item.project_id)}>查看检查记录<ArrowRightOutlined aria-hidden="true"/></ActionLink></article>)}</details> : null}
      {official?.active && official.project_id === selected?.project_id && <ExampleLab projectId={official.project_id!} onError={onError} onChanged={() => onChanged(official.project_id!)}/>}
    </div>}
    {startConfirm && <Dialog title={startConfirm === 'reset' ? '重新开始示例' : startConfirm === 'stop' ? '停止数字展馆' : '重启运行环境'} onClose={() => setStartConfirm(undefined)} actions={dismiss => <><Button onClick={dismiss}>取消</Button><Button kind={startConfirm === 'stop' ? 'danger' : 'primary'} onClick={() => { const kind = startConfirm; setStartConfirm(undefined); lifecycle.begin(kind); }}>{startConfirm === 'reset' ? '重新开始' : startConfirm === 'stop' ? '停止示例' : '重启运行环境'}</Button></>}><p>{startConfirm === 'reset' ? '创建全新的源码、项目与测试数据。当前示例及其活动检查将停止；旧项目、权限与报告保留在“已归档示例”中。' : startConfirm === 'stop' ? '停止当前运行环境和本示例的活动检查。项目、源码、权限和历史报告保留。' : '停止当前示例及其活动检查，再运行同一份源码。项目、权限和报告保留，登录与证明来源需要重新核对。'}</p></Dialog>}
  </div>{selected&&value&&<TaskSurface active={runtimeOpen} title="准备应用的本地运行" context={selected.name} onBack={()=>setRuntimeOpen(false)} backLabel={embedded?'返回源码设置':'返回应用连接'}>{Boolean(runtimeError)&&<ErrorNote error={runtimeError}/>}{selected && <RuntimeConnection key={selected.project_id} projectId={selected.project_id} revision={value.revision} confirmedEndpoint={value.confirmed_endpoint} canStart={!selected.official_sample && value.source_analysis_authorized} initialMethod={!selected.official_sample&&value.source_analysis_authorized&&route.query.get('runtime_method')==='managed'?'managed':undefined} onChanged={()=>{setRuntimeError(undefined);current.reload()}} onError={setRuntimeError}/>}</TaskSurface>}</>;
}
function ExampleManagement({ active = false, disabled, onChoose }: {
    active?: boolean;
    disabled?: boolean;
    onChoose: (value: 'restart' | 'stop' | 'reset') => void;
}) {
    return <CommandMenu className="jj-example-menu" menu={{
            selectable: false,
            items: [...(active ? [{ key: 'restart', label: '重启运行环境', icon: <ReloadOutlined aria-hidden="true"/> }, { key: 'stop', label: '停止示例', icon: <PauseOutlined aria-hidden="true"/> }, { type: 'divider' as const }] : []), { key: 'reset', label: '重新开始示例', icon: <PlusOutlined aria-hidden="true"/> }],
            onClick: ({ key }) => onChoose(key as 'restart' | 'stop' | 'reset'),
        }}><Button className="jj-menu-trigger" disabled={disabled}>管理示例<DownOutlined className="jj-menu-chevron" aria-hidden="true"/></Button></CommandMenu>;
}
