import './workspace.css'
import { useRef, useState } from 'react';
import { ArrowRightOutlined, CheckOutlined, LinkOutlined, SafetyOutlined } from '@ant-design/icons';
import { agentClients, agentConnectionsApi, mcpAccessApi, type AgentClient, type MCPAccessLevel, type AgentConnection } from '../../entities/runtime/api/mcp';
import { Choice } from "../../shared/ui/Choice";
import { Badge, ErrorNote, Loading, Notice } from "../../shared/ui/feedback";
import { Button } from "../../shared/ui/actions";
import { Dialog } from "../../shared/ui/Dialog";
import { Field, Heading } from "../../shared/ui/layout";
import { useRead } from '../../shared/lib/useRead';
const levels: Record<MCPAccessLevel, string> = { READ: '只读资料与报告', PREPARE: '整理规则候选与检查材料', EXECUTE: '准备材料并提交检查' };
const levelDetails: Record<MCPAccessLevel, string> = { READ: '读取业务要求、材料和已发布报告。', PREPARE: '可保存规则候选与材料建议，权限生效仍由你批准。', EXECUTE: '可准备材料并提交检查，执行仍受账号、资源与权限门禁约束。' };
const connectionLabels: Record<AgentConnection['state'], string> = { NOT_CONFIGURED: '尚未配置', AWAITING_CLIENT: '等待工具确认', STARTED: '连接器已启动', CONNECTED: '连接已建立', TOOLS_READ: '已读取工具', REQUEST_ACCEPTED: '已接收请求', DISCONNECTED: '连接已断开', FAILED: '连接未完成' };
export function Agent({ projectId, name, onError }: {
    projectId?: string;
    name?: string;
    onError: (error: unknown) => void;
}) {
    const state = useRead('agent-access', mcpAccessApi.status, 4000);
    const [client, setClient] = useState<AgentClient>('codex'), [profile, setProfile] = useState(''), [busy, setBusy] = useState(false), [confirm, setConfirm] = useState<'connect' | 'access' | 'restore' | 'forget'>(), [level, setLevel] = useState<MCPAccessLevel>(), [message, setMessage] = useState(''), lock = useRef(false);
    const connection = useRead('agent-client:' + client, () => agentConnectionsApi.status(client), 5000);
    const grant = state.data?.project_grants.find(item => item.project_id === projectId);
    const chosenLevel = level ?? grant?.level ?? 'READ';
    const selectedClient = agentClients.find(item => item.key === client)!;
    const connected = connection.data && ['CONNECTED', 'TOOLS_READ', 'REQUEST_ACCEPTED'].includes(connection.data.state);
    const act = async (callback: () => Promise<unknown>) => { if (lock.current)
        return; lock.current = true; setBusy(true); try {
        await callback();
        state.reload();
        connection.reload();
        setConfirm(undefined);
    }
    catch (error) {
        onError(error);
    }
    finally {
        lock.current = false;
        setBusy(false);
    } };
    return <>
    <Heading title="开发工具" actions={<Button disabled={busy} onClick={() => { state.reload(); connection.reload(); }}>读取连接状态</Button>}/>
    {message && <Notice tone="accent">{message}</Notice>}
    <div className="jj-tools-layout">
      <section className="jj-tools-connection">
        <header className="jj-workspace-header"><span className="jj-workspace-symbol"><LinkOutlined aria-hidden="true"/></span><div><h2>连接开发工具</h2><p className="jj-small jj-muted">将业务要求、材料和检查报告带回开发过程。</p></div></header>
        <div className="jj-tools-body">
          <div className="jj-tool-picker" aria-label="选择开发工具">{agentClients.map(item => <button key={item.key} aria-pressed={client === item.key} disabled={busy} onClick={() => { setClient(item.key); setProfile(''); }}><span>{item.name}</span>{client === item.key && <CheckOutlined aria-hidden="true"/>}</button>)}</div>
          <section className="jj-tool-detail" key={client}>
            <header><h3>{selectedClient.name}</h3>{connection.data && <Badge tone={connected ? 'positive' : connection.data.state === 'FAILED' ? 'caution' : 'neutral'}>{connectionLabels[connection.data.state]}</Badge>}</header>
            {connection.loading ? <Loading>正在读取工具连接</Loading> : connection.error ? <ErrorNote error={connection.error} onRetry={connection.reload}/> : <>
            <div className="jj-tool-configure"><div className="jj-tool-configure-content">{connection.data?.message && <p className="jj-tool-message">{connection.data.message}</p>}{(connection.data?.tool_count ?? 0) > 0 && <p className="jj-small jj-muted">最近一次读取到 {connection.data?.tool_count} 项工具。</p>}{connection.data?.profiles.length ? <Field label="配置位置"><Choice value={profile} disabled={busy} onValueChange={value => setProfile(value)}><option value="">选择配置</option>{connection.data.profiles.map(item => <option key={item} value={item}>{item}</option>)}</Choice></Field> : <p className="jj-small jj-muted">配置后，按客户端提示确认或重新加载连接。</p>}</div><Button kind="primary" disabled={busy || Boolean(connection.data?.profiles.length && !profile)} onClick={() => setConfirm('connect')}>配置连接<ArrowRightOutlined aria-hidden="true"/></Button></div><details className="jj-tool-maintenance"><summary>连接维护</summary><div className="jj-inline-actions"><Button disabled={busy} onClick={() => setConfirm('restore')}>恢复原有工具配置</Button>{state.data?.paired && <Button kind="danger" disabled={busy} onClick={() => setConfirm('forget')}>解除所有工具配对</Button>}</div></details></>}
          </section>
        </div>
        {state.data && <footer className="jj-tools-service"><div><span className="jj-status-dot" data-ready={state.data.paired && state.data.accepting_connections}/><strong>{state.data.paired ? state.data.accepting_connections ? '正在接受工具连接' : '工具连接已暂停' : '尚未建立工具配对'}</strong></div>{state.data.paired && <Button kind="quiet" busy={busy} onClick={() => void act(async () => { await (state.data!.accepting_connections ? mcpAccessApi.pause() : mcpAccessApi.resume()); setMessage(state.data!.accepting_connections ? '工具连接已暂停。' : '工具连接已恢复。'); })}>{state.data.accepting_connections ? '暂停工具连接' : '恢复工具连接'}</Button>}<details><summary>本地连接地址</summary><p className="jj-path">{state.data.endpoint}</p></details></footer>}
      </section>
      <section className="jj-tools-access">
        <header><SafetyOutlined aria-hidden="true"/><h2>应用授权</h2></header>
        {state.loading ? <Loading page/> : state.error ? <ErrorNote error={state.error} onRetry={state.reload}/> : <>
          <div className="jj-current-grant"><p className="jj-eyebrow">当前应用</p><h3>{name ?? (projectId ? '已选应用' : '尚未选择应用')}</h3><p>{grant ? levels[grant.level] : '尚未授予此应用权限'}</p></div>
          <Field label="允许范围"><Choice value={chosenLevel} disabled={!projectId || busy} onValueChange={value => setLevel(value as MCPAccessLevel)}>{Object.entries(levels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</Choice></Field><p className="jj-access-explanation">{levelDetails[chosenLevel]}</p>
          {!state.data?.paired && <p className="jj-small jj-muted">先配置工具连接，再授予当前应用的访问范围。</p>}
          <Button disabled={!projectId || busy || !state.data?.paired} onClick={() => setConfirm('access')}>确认应用权限</Button>{projectId && grant && grant.level !== 'READ' && <Button kind="quiet" disabled={busy} onClick={() => void act(async () => { await mcpAccessApi.setProjectAccess(projectId, 'READ'); setLevel(undefined); setMessage('当前应用已改为只读。'); })}>将当前应用改为只读</Button>}
        </>}
      </section>
    </div>
    {confirm && <Dialog title={confirm === 'connect' ? '配置开发工具连接' : confirm === 'restore' ? '恢复工具配置' : confirm === 'forget' ? '解除工具配对' : '更新工具权限'} onClose={() => setConfirm(undefined)} actions={dismiss => <><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} onClick={() => void act(async () => { if (confirm === 'connect') {
        const value = await agentConnectionsApi.connect(client, profile || undefined);
        setMessage(value.message);
    }
    else if (confirm === 'restore') { const value = await agentConnectionsApi.restore(client); setMessage(value.message); } else if (confirm === 'forget') { await mcpAccessApi.forget(); setMessage('工具配对已解除。需要重新配置连接才能继续访问。'); } else if (projectId) {
        await mcpAccessApi.setProjectAccess(projectId, chosenLevel);
        setLevel(undefined);
    } })}>确认</Button></>}><p>{confirm === 'restore' ? '恢复界鉴配置连接前保存的工具设置。当前客户端可能需要重新加载。' : confirm === 'forget' ? '解除所有开发工具的本地配对和应用授权。现有规则、材料与报告保留。' : confirm === 'connect' ? '界鉴会更新 ' + selectedClient.name + ' 的本地连接配置，并保存恢复所需的信息。连接后的默认权限为只读。' : '允许开发工具在“' + (name ?? '当前应用') + '”内' + levels[chosenLevel] + '。权限规则的生效仍需由你审阅批准。'}</p></Dialog>}
  </>;
}
