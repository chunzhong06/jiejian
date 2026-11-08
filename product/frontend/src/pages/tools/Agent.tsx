import './workspace.css'
import { useRef, useState } from 'react';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import { agentClients, agentConnectionsApi, mcpAccessApi, type AgentClient, type MCPAccessLevel, type AgentConnection } from '../../entities/runtime/api/mcp';
import { Choice } from "../../shared/ui/Choice";
import { Badge, ErrorNote, Loading, Notice } from "../../shared/ui/feedback";
import { Button } from "../../shared/ui/actions";
import {Switch} from '../../shared/ui/Switch';
import { Dialog } from "../../shared/ui/Dialog";
import {Field, Heading,ObjectIdentity} from "../../shared/ui/layout"
import { useRead } from '../../shared/lib/useRead';
const levels: Record<MCPAccessLevel, string> = { READ: '只读资料与报告', PREPARE: '整理规则候选与检查材料', EXECUTE: '准备材料并提交检查' };
const levelDetails: Record<MCPAccessLevel, string> = { READ: '', PREPARE: '权限规则仍需你确认后生效。', EXECUTE: '执行受账号、资源与权限门禁约束，权限规则仍需你确认后生效。' };
const connectionLabels: Record<AgentConnection['state'], string> = { NOT_CONFIGURED: '尚未配置', AWAITING_CLIENT: '等待工具确认', STARTED: '连接器已启动', CONNECTED: '连接已建立', TOOLS_READ: '已读取工具', REQUEST_ACCEPTED: '已接收请求', DISCONNECTED: '连接已断开', FAILED: '连接未完成' };
export function Agent({ projectId, name, onError,embedded=false }: {
    projectId?: string;
    name?: string;
    onError: (error: unknown) => void;
    embedded?:boolean;
}) {
    const state = useRead('agent-access', mcpAccessApi.status, 4000);
    const [client, setClient] = useState<AgentClient>('codex'), [profile, setProfile] = useState(''), [busy, setBusy] = useState(false), [confirm, setConfirm] = useState<'connect' | 'access' | 'restore' | 'forget'>(), [level, setLevel] = useState<MCPAccessLevel>(), [message, setMessage] = useState(''), lock = useRef(false);
    const connection = useRead('agent-client:' + client, () => agentConnectionsApi.status(client), 5000);
    const grant = state.data?.project_grants.find(item => item.project_id === projectId);
    const chosenLevel = level ?? grant?.level ?? 'READ';
    const selectedClient = agentClients.find(item => item.key === client)!;
    const connected = connection.data && ['CONNECTED', 'TOOLS_READ', 'REQUEST_ACCEPTED'].includes(connection.data.state);
    // 未配置状态由标签说明；已连接的完整协议说明归入管理区，异常与待确认指引保留在当前工作面。
    const connectionHint = connection.data && !connected && connection.data.state !== 'NOT_CONFIGURED' ? connection.data.message : '';
    const accessChanged = Boolean(grant && chosenLevel !== grant.level);
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
    {!embedded&&<Heading title="开发工具"/>}
    {message&&message!==connection.data?.message&&<Notice tone="accent">{message}</Notice>}
    <div className="jj-tools-layout">
      <section className="jj-tools-connection">
        <header className="jj-tools-heading"><h2>工具连接</h2></header>
        <div className="jj-tools-body">
          <div className="jj-tool-selector"><div className="jj-tool-object"><Field label="开发工具"><Choice value={client} disabled={busy} onValueChange={value=>{setClient(value as AgentClient);setProfile('');setMessage('');}}>{agentClients.map(item=><option key={item.key} value={item.key}>{item.name}</option>)}</Choice></Field><div className="jj-tool-state">{connection.loading?<Badge>读取中</Badge>:!connection.error&&connection.data&&<><Badge tone={connected?'positive':connection.data.state==='FAILED'?'negative':'neutral'}>{connectionLabels[connection.data.state]}</Badge>{connection.data.tool_count>0&&<span className="jj-small jj-muted">{connection.data.tool_count} 项工具</span>}</>}</div></div></div>
          {(connection.error||connectionHint||connected||Boolean(connection.data?.profiles.length))&&<section className="jj-tool-detail" key={client}>
            {connection.error?<ErrorNote error={connection.error}/>:<>
              {connectionHint&&<p className="jj-tool-message">{connectionHint}</p>}
              {connected&&<p className="jj-small jj-muted">显示最近活动，不代表客户端持续在线。</p>}
              {Boolean(connection.data?.profiles.length)&&<Field label="配置位置"><Choice value={profile} disabled={busy} onValueChange={setProfile}><option value="">选择配置</option>{connection.data!.profiles.map(item=><option key={item} value={item}>{item}</option>)}</Choice></Field>}
            </>}
          </section>}
        </div>
        {state.data&&<section className="jj-tools-service"><div className="jj-tools-service-row"><div className="jj-tools-service-state"><ObjectIdentity name={<strong>本地接入服务</strong>} status={<Badge tone={state.data.paired&&state.data.accepting_connections?'positive':'neutral'}>{state.data.paired?state.data.accepting_connections?'接受连接':'已暂停':'未配对'}</Badge>}/></div>{state.data.paired&&<Switch label="允许开发工具接入" checked={state.data.accepting_connections} busy={busy} onCheckedChange={accepting=>void act(async()=>{await(accepting?mcpAccessApi.resume():mcpAccessApi.pause());})}/>}</div>
          <details className="jj-tool-management"><summary>连接管理</summary><div className="jj-tool-management-content"><dl className="jj-facts"><dt>本地接入地址</dt><dd className="jj-path">{state.data.endpoint}</dd></dl>{connected&&connection.data?.message&&<p className="jj-small jj-muted">{connection.data.message}</p>}<div className="jj-inline-actions">{connection.data&&connection.data.state!=='NOT_CONFIGURED'&&<Button disabled={busy} onClick={()=>setConfirm('restore')}>恢复此工具原配置</Button>}{state.data.paired&&<Button kind="danger" disabled={busy} onClick={()=>setConfirm('forget')}>解除全部工具配对</Button>}</div></div></details>
        </section>}
        <footer className="jj-tools-actions"><Button kind={connected?'quiet':'primary'} disabled={busy||connection.loading||Boolean(connection.error)||Boolean(connection.data?.profiles.length&&!profile)} onClick={()=>setConfirm('connect')}>{connection.data?.state==='NOT_CONFIGURED'?'配置连接':'更新连接'}<ArrowRightOutlined aria-hidden="true"/></Button></footer>
      </section>
      <section className="jj-tools-access">
        <header><h2>应用授权</h2></header>
        <p className="jj-access-explanation">选择这个开发工具可以在当前应用中做什么。连接工具与授予访问权限分别确认。</p>
        {state.loading ? <Loading page/> : state.error ? <ErrorNote error={state.error}/> : <>
          <div className="jj-current-grant"><h3>{name??(projectId?'已选应用':'尚未选择应用')}</h3>{projectId&&<Badge tone={grant?'positive':'neutral'}>{grant?'已授权':'未授权'}</Badge>}</div>
          <Field label="访问范围" hint={levelDetails[chosenLevel]||"读取业务要求、检查材料和已发布报告。"}><Choice value={chosenLevel} disabled={!projectId||busy} onValueChange={value=>setLevel(value as MCPAccessLevel)}>{Object.entries(levels).map(([id,label])=><option key={id} value={id}>{label}</option>)}</Choice></Field>
          {accessChanged&&<p className="jj-access-current">当前权限：{levels[grant!.level]}，新范围尚未保存。</p>}
          {!state.data?.paired&&<p className="jj-access-explanation">先配置工具连接，再选择它可以访问的应用和操作范围。</p>}
          <Button disabled={!projectId||busy||!state.data?.paired||Boolean(grant&&!accessChanged)} onClick={()=>setConfirm('access')}>{grant?'保存权限':'授予访问权限'}</Button>
        </>}
      </section>
    </div>
    {confirm && <Dialog title={confirm === 'connect' ? '配置开发工具连接' : confirm === 'restore' ? '恢复工具配置' : confirm === 'forget' ? '解除工具配对' : '更新工具权限'} onClose={() => setConfirm(undefined)} actions={dismiss => <><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind={confirm === 'forget' ? 'danger' : 'primary'} busy={busy} onClick={() => void act(async () => { if (confirm === 'connect') {
        const value = await agentConnectionsApi.connect(client, profile || undefined);
        setMessage(value.message);
    }
    else if (confirm === 'restore') { const value = await agentConnectionsApi.restore(client); setMessage(value.message); } else if (confirm === 'forget') { await mcpAccessApi.forget(); setMessage('工具配对已解除。需要重新配置连接才能继续访问。'); } else if (projectId) {
        await mcpAccessApi.setProjectAccess(projectId, chosenLevel);
        setLevel(undefined);
    } })}>{confirm === 'forget' ? '解除配对' : confirm === 'restore' ? '恢复配置' : confirm === 'connect' ? '配置连接' : '更新权限'}</Button></>}><p>{confirm === 'restore' ? '恢复界鉴配置连接前保存的工具设置。当前客户端可能需要重新加载。' : confirm === 'forget' ? '解除所有开发工具的本地配对和应用授权。现有规则、材料与报告保留。' : confirm === 'connect' ? '界鉴会更新 ' + selectedClient.name + ' 的本地连接配置，并保存恢复所需的信息。连接后的默认权限为只读。' : '允许开发工具在“' + (name ?? '当前应用') + '”内' + levels[chosenLevel] + '。权限规则的生效仍需由你审阅批准。'}</p></Dialog>}
  </>;
}
