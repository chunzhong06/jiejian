import './styles.css'
import { useRef, useState } from 'react';
import { ArrowRightOutlined, CodeOutlined, FolderOpenOutlined, AppstoreOutlined, DownOutlined, ReloadOutlined, PauseOutlined, PlusOutlined } from '@ant-design/icons';
import { Dropdown } from 'antd';
import { type OfficialExperienceDto } from '../../entities/application/api/experience';
import { projectsApi, type ProjectDto, type ConnectionPreview } from '../../entities/application/api/projects';
import { assertProject } from '../../shared/model/page';
import { date } from '../../shared/lib/format';
import { go } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
import { ActionLink, Button } from "../../shared/ui/actions";
import { Heading, Field } from "../../shared/ui/layout";
import { Badge, Loading, Notice, ErrorNote } from "../../shared/ui/feedback";
import { Dialog } from "../../shared/ui/Dialog";
import { ExampleLab } from './ExampleLab';
import { useExampleLifecycle } from './exampleLifecycle';
export function Connect({ selected, environment, mode = 'application', onChanged, onError }: {
    selected?: ProjectDto;
    environment?: OfficialExperienceDto;
    mode?: 'application' | 'environment';
    onChanged: (id: string) => void;
    onError: (error: unknown) => void;
}) {
    const [directory, setDirectory] = useState(''), [endpoint, setEndpoint] = useState<string>(), [preview, setPreview] = useState<ConnectionPreview>(), [busy, setBusy] = useState(false), [consent, setConsent] = useState(false), [startConfirm, setStartConfirm] = useState<'restart' | 'reset' | 'stop'>(), [connecting, setConnecting] = useState(!selected);
    const guard = useRef(false);
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
    return <>
    <Heading title={mode === 'environment' ? '官方示例' : '应用连接'} actions={mode === 'application' && selected && !connecting && <Button onClick={() => setConnecting(true)} icon={<FolderOpenOutlined aria-hidden="true"/>}>连接其他应用</Button>}/>
    {mode === 'application' ? <>
      {current.loading && selected ? <Loading page>正在读取应用连接</Loading> : value && !connecting && <section className="jj-connection-workbench">
        <header className="jj-workspace-header"><span className="jj-workspace-symbol"><CodeOutlined aria-hidden="true"/></span><div><p className="jj-eyebrow">当前应用</p><h2>{selected?.name ?? '待检查的应用'}</h2></div><Badge tone={value.confirmed_endpoint ? 'positive' : 'neutral'}>{value.confirmed_endpoint ? '地址已确认' : '待确认地址'}</Badge></header>
        <div className="jj-connection-body">
          <section className="jj-source-connection"><h3>源码与业务</h3><p className="jj-path">{value.source_root}</p>
            <div className="jj-connection-facts"><div><span>源码读取</span><strong>{value.source_analysis_authorized ? '已授权' : '尚未授权'}</strong></div><div><span>业务线索</span><strong>{value.analysis_completed_at_us ? value.role_candidates.length + ' 个角色，' + value.action_candidates.length + ' 项操作' : '尚未读取'}</strong></div></div>
            {!value.source_analysis_authorized && <label className="jj-checkbox"><input type="checkbox" checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)}/><span>允许界鉴读取此目录的源码，用于识别业务角色与操作。</span></label>}
            <div className="jj-inline-actions jj-form-actions">
              <Button busy={busy} disabled={!consent && !value.source_analysis_authorized} onClick={() => void act(async () => { let next = await projectsApi.understanding(selected!.project_id); assertProject(next.project_id, selected!.project_id); if (!next.source_analysis_authorized)
                next = await projectsApi.authorizeSourceAnalysis(selected!.project_id, next.revision); await projectsApi.analyzeSource(selected!.project_id, next.revision); current.reload(); go('/application?view=business'); })}>{value.analysis_completed_at_us ? '重新读取业务结构' : '读取业务结构'}</Button>
              {value.analysis_completed_at_us && <Button kind="quiet" onClick={() => go('/application?view=business')}>核对业务名称<ArrowRightOutlined aria-hidden="true"/></Button>}
            </div>
          </section>
          <section className="jj-endpoint-connection"><h3>运行地址</h3><p className="jj-small jj-muted">用于登录、录制和实际检查。</p><div className="jj-endpoint-form"><Field label="应用访问地址"><input type="url" disabled={busy} value={endpoint ?? value.confirmed_endpoint ?? ''} placeholder="http://127.0.0.1:端口" onChange={event => setEndpoint(event.target.value)}/></Field><Button busy={busy} disabled={!(endpoint ?? value.confirmed_endpoint ?? '').trim()} onClick={() => void act(async () => { await projectsApi.confirmEndpoint(selected!.project_id, endpoint ?? value.confirmed_endpoint ?? '', value.revision); setEndpoint(undefined); current.reload(); })}>确认地址</Button></div></section>
        </div>
      </section>}
      {(connecting || !selected) && <section className="jj-connect-new">
        <header><span className="jj-workspace-symbol"><FolderOpenOutlined aria-hidden="true"/></span><div><h2>连接本地应用</h2><p>选择源码目录，先核对是否已有项目。</p></div></header>
        <div className="jj-connect-new-body"><div className="jj-directory-form"><Field label="项目目录"><input value={directory} disabled={busy} onChange={event => { setDirectory(event.target.value); setPreview(undefined); }} placeholder="源码所在的完整目录"/></Field><Button kind="primary" busy={busy} disabled={!directory.trim()} onClick={() => void act(async () => setPreview(await projectsApi.connectionPreview(directory.trim())))}>检查连接</Button></div>
        {preview && <div className="jj-connection-preview"><p className="jj-path">{preview.source_root}</p>{preview.projects.length > 0 && <section><h3>此目录已有项目</h3>{preview.projects.map(item => <div className="jj-existing-project" key={item.project_id}><strong>{item.name}</strong><Button busy={busy} onClick={() => void act(async () => { const result = await projectsApi.connectApplication(preview.source_root, undefined, { mode: 'RESUME', existing_project_id: item.project_id, expected_snapshot: preview.snapshot, operation_id: crypto.randomUUID() }); onChanged(result.project.project_id); })}>继续使用</Button></div>)}</section>}<div className="jj-connect-new-choice"><span>{preview.projects.length ? '另建项目将使用独立的权限和材料。' : '将为此目录建立独立项目。'}</span><Button kind="primary" busy={busy} onClick={() => void act(async () => { const result = await projectsApi.connectApplication(preview.source_root, undefined, { mode: 'NEW', expected_snapshot: preview.snapshot, operation_id: crypto.randomUUID() }); onChanged(result.project.project_id); })}>建立新项目</Button></div></div>}
        </div>{selected && <footer><Button kind="quiet" disabled={busy} onClick={() => setConnecting(false)}>返回当前应用</Button></footer>}
      </section>}
      {current.error && <ErrorNote error={current.error} onRetry={current.reload}/>}
    </> : <div className="jj-environment-workspace">
      <section className="jj-example-overview"><header><span className="jj-workspace-symbol"><AppstoreOutlined aria-hidden="true"/></span><div><p className="jj-eyebrow">独立体验环境</p><h2>数字展馆</h2></div><Badge tone={official?.active ? 'positive' : 'neutral'}>{official?.active ? '正在运行' : official?.lifecycle === 'STARTING' ? '正在启动' : '尚未运行'}</Badge></header><p className="jj-example-description">负责人管理展馆资料，评审访问公开内容。通过这组业务核对访问限制、实际结果与修复。</p>
      <footer>{lifecycle.pending ? <><div className="jj-environment-progress" role="status"><span className="jj-working-dot"/><div><strong>{lifecycle.phase}</strong><p>{lifecycle.pending.kind === 'reset' ? '正在建立全新示例，旧项目与报告保留在归档中。' : '保留当前项目、源码、权限和报告。'}</p></div></div><Button onClick={lifecycle.reload}>查询这次操作</Button></> : official?.active && official.project_id ? <><span className="jj-small jj-muted">源码、权限和报告保存在独立项目中。</span><div className="jj-example-actions"><ExampleManagement active disabled={lifecycle.busy} onChoose={setStartConfirm}/><Button kind="primary" onClick={() => onChanged(official.project_id!)}>进入示例<ArrowRightOutlined aria-hidden="true"/></Button></div></> : <><span className="jj-small jj-muted">{resumable ? '继续使用已保存的源码、权限和报告。' : '将建立本地示例和独立测试数据。'}</span><div className="jj-inline-actions">{resumable && <ExampleManagement disabled={lifecycle.busy || official?.available === false} onChoose={setStartConfirm}/>}<Button kind="primary" disabled={lifecycle.busy || official?.available === false} onClick={() => lifecycle.begin(resumable ? 'resume' : 'start')}>{resumable ? '继续上次示例' : '启动官方示例'}</Button></div></>}</footer>{official?.available === false && <Notice>{official.unavailable_reason ?? '当前示例运行条件尚未就绪。'}</Notice>}{lifecycle.unknown && <Notice>操作已提交，结果尚未确认。请查询这次操作，不要重复启动。</Notice>}{lifecycle.failure && <Notice>{lifecycle.failure}<Button onClick={lifecycle.reload}>读取运行状态</Button></Notice>}{lifecycle.error && <ErrorNote error={lifecycle.error} onRetry={lifecycle.reload}/>}</section>
      {(archives.data?.length || archives.error) ? <section className="jj-example-archives"><header><h2>已归档示例</h2><span className="jj-small jj-muted">查看先前的检查与证据</span></header>{archives.error ? <ErrorNote error={archives.error} onRetry={archives.reload}/> : archives.data?.map(item => <article key={item.project_id}><div><h3>{item.name ?? '数字展馆'}</h3>{item.created_at_us && <time className="jj-small jj-muted">{date(item.created_at_us)}</time>}</div><ActionLink href={'#/archive?project_id=' + encodeURIComponent(item.project_id)}>查看检查记录<ArrowRightOutlined aria-hidden="true"/></ActionLink></article>)}</section> : null}
      {official?.active && official.project_id === selected?.project_id && <ExampleLab projectId={official.project_id!} onError={onError} onChanged={() => onChanged(official.project_id!)}/>}
    </div>}
    {startConfirm && <Dialog title={startConfirm === 'reset' ? '重新开始示例' : startConfirm === 'stop' ? '停止数字展馆' : '重启运行环境'} onClose={() => setStartConfirm(undefined)} actions={dismiss => <><Button onClick={dismiss}>取消</Button><Button kind={startConfirm === 'stop' ? 'danger' : 'primary'} onClick={() => { const kind = startConfirm; setStartConfirm(undefined); lifecycle.begin(kind); }}>{startConfirm === 'reset' ? '重新开始' : startConfirm === 'stop' ? '停止示例' : '重启运行环境'}</Button></>}><p>{startConfirm === 'reset' ? '创建全新的源码、项目与测试数据。当前示例及其活动检查将停止；旧项目、权限与报告保留在“已归档示例”中。' : startConfirm === 'stop' ? '停止当前运行环境和本示例的活动检查。项目、源码、权限和历史报告保留。' : '停止当前示例及其活动检查，再运行同一份源码。项目、权限和报告保留，登录与证明来源需要重新核对。'}</p></Dialog>}
  </>;
}
function ExampleManagement({ active = false, disabled, onChoose }: {
    active?: boolean;
    disabled?: boolean;
    onChoose: (value: 'restart' | 'stop' | 'reset') => void;
}) {
    const [open, setOpen] = useState(false), trigger = useRef<HTMLButtonElement>(null);
    const close = () => { setOpen(false); trigger.current?.focus({ preventScroll: true }); };
    return <Dropdown open={open} onOpenChange={setOpen} trigger={['click']} placement="bottomRight" autoFocus overlayClassName="jj-example-menu" menu={{
            selectable: false,
            items: [...(active ? [{ key: 'restart', label: '重启运行环境', icon: <ReloadOutlined aria-hidden="true"/> }, { key: 'stop', label: '停止示例', icon: <PauseOutlined aria-hidden="true"/> }, { type: 'divider' as const }] : []), { key: 'reset', label: '重新开始示例', icon: <PlusOutlined aria-hidden="true"/> }],
            onClick: ({ key }) => { close(); onChoose(key as 'restart' | 'stop' | 'reset'); },
            onKeyDown: event => { if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                close();
            } },
        }}><Button className="jj-menu-trigger" ref={trigger} disabled={disabled} aria-haspopup="menu" aria-expanded={open} onKeyDown={event => { if (event.key === 'ArrowDown') {
        event.preventDefault();
        setOpen(true);
    } }}>管理示例<DownOutlined className="jj-menu-chevron" aria-hidden="true"/></Button></Dropdown>;
}
