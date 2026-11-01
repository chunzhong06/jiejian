import { useEffect, useRef, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import UserOutlined from '@ant-design/icons/UserOutlined';
import GlobalOutlined from '@ant-design/icons/GlobalOutlined';
import CheckOutlined from '@ant-design/icons/CheckOutlined';
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined';
import { testIdentitiesApi as api, type IdentityPreparationDto, type TestIdentityDto } from '../../../entities/preparation/api/testIdentities';
import { preparationApi, type ActionPreparation } from '../../../entities/preparation/api/preparation';
import { ApiError } from '../../../shared/api/http';
import { assertProject } from '../../../shared/model/page';
import { text } from '../../../shared/lib/format';
import { useRead } from '../../../shared/lib/useRead';
import { operationId, readPending, savePending } from '../../../shared/lib/operations';
import { go } from '../../../shared/lib/navigation';
import { Badge, Empty, ErrorNote, Loading, Notice } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import { Heading } from "../../../shared/ui/layout";
import { Dialog } from "../../../shared/ui/Dialog";
import {AccountAuthentication} from './AccountAuthentication';
export function Accounts({ projectId, actions, requestedPreparation, onBack, onError }: {
    projectId: string;
    actions: ActionPreparation[];
    requestedPreparation?: string | null;
    onBack: () => void;
    onError: (error: unknown) => void;
}) {
    const state = useRead('accounts:' + projectId, async (signal) => {
        const [identities, preparation, preparations] = await Promise.all([api.list(projectId, signal), preparationApi.get(projectId, signal), api.preparations(projectId, signal)]);
        assertProject(preparation.project_id, projectId);
        identities.forEach(value => assertProject(value.project_id, projectId));
        if (preparation.actions.some(action => action.identity_requirements.slots.some(slot => slot.test_identity_id && !identities.some(item => item.identity_id === slot.test_identity_id))))
            throw new Error('账号清单已变化，请重新读取。');
        return { identities, actions: preparation.actions, preparations };
    });
    const pendingKey = 'jiejian.studio.login:' + projectId;
    type Pending = { kind: 'create'; operation: string; actor: string; revision: number; label: string } | { kind: 'login'; operation: string; identity: string; verifyOnly?: boolean };
    const [reset, setReset] = useState<string>(), [busy, setBusy] = useState(false), [login, setLogin] = useState<IdentityPreparationDto>(), [pending, setPending] = useState(() => readPending<Pending>(pendingKey));
    const [authentication,setAuthentication]=useState<TestIdentityDto>();
    const [selectedAccount, setSelectedAccount] = useState<string>();
    const remember = (value?: Pending) => { savePending(pendingKey, value); setPending(value); };
    // React busy 尚未提交时也要挡住第二次点击；真正的跨刷新去重仍依赖持久操作标识。
    const lock = useRef(false);
    const located = useRef<string | undefined>(undefined);
    const requested = useRead(requestedPreparation ? 'requested-login:' + requestedPreparation : null, async () => {
        if (!requestedPreparation) return null;
        const value = await api.preparation(requestedPreparation);
        assertProject(value.project_id ?? '', projectId);
        return value;
    });
    const active = useRead(login ? 'login:' + login.preparation_id : null, async () => login ? api.preparation(login.preparation_id) : null, value => value && !['PREPARED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(value.status) ? 1000 : 0);
    const current = active.data ?? login;
    useEffect(() => {
        if (requested.data && located.current !== requested.data.preparation_id) {
            located.current = requested.data.preparation_id;
            setLogin(requested.data);
        }
    }, [requested.data]);
    useEffect(() => {
        if (requestedPreparation) return;
        const running = state.data?.preparations.find(value => value.cleanup_required || !['PREPARED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(value.status));
        if (running && (!login || ['PREPARED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(login.status))) setLogin(running);
    }, [state.data?.preparations, requestedPreparation, login?.preparation_id, login?.status]);
    useEffect(() => { if (current && ['PREPARED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(current.status)) {
        remember();
        state.reload();
    } }, [current?.preparation_id, current?.status]);
    const act = async (callback: () => Promise<unknown>) => { if (lock.current)
        return; lock.current = true; setBusy(true); try {
        await callback();
    }
    catch (error) {
        onError(error);
    }
    finally {
        lock.current = false;
        setBusy(false);
    } };
    const recover = async (retry = false) => {
        // 自动恢复只查原回执；明确点击重试后仍复用原标识，避免网络断开时重复建账号或开窗口。
        const saved = readPending<Pending>(pendingKey);
        if (saved?.kind === 'create') {
            const item = await api.created(projectId, saved.operation) ?? (retry ? await api.create(projectId, saved.actor, saved.revision, saved.label, saved.operation) : null);
            if (item) remember();
        } else if (saved?.kind === 'login') {
            const items = await api.list(projectId), identity = items.find(item => item.identity_id === saved.identity);
            const latest = await api.requestedPreparation(saved.identity, saved.operation);
            if (latest) { setLogin(latest); remember(); }
            else if (identity?.status === 'PREPARED') remember();
            else if (retry) { setLogin(await api.startPreparation(saved.identity, saved.operation, saved.verifyOnly)); remember(); }
        }
        state.reload();
    };
    useEffect(() => { if (readPending<Pending>(pendingKey)) void act(() => recover()); }, [projectId]);
    const prepare = (identity: TestIdentityDto | undefined, slot: ActionPreparation['identity_requirements']['slots'][number]) => {
        if (!state.data || state.error)
            return;
        if (identity && identity.status !== 'NOT_PREPARED') {
            setReset(identity.identity_id);
            return;
        }
        void act(async () => {
            let item = identity;
            if (!item) {
                // 初次展示后可能已有另一入口建好账号；创建前重读槽位，复用后端当前绑定。
                const latest = await preparationApi.get(projectId);
                assertProject(latest.project_id, projectId);
                const currentSlot = latest.actions.flatMap(action => action.identity_requirements.slots).find(value => value.requirement.slot_id === slot.requirement.slot_id);
                if (!currentSlot)
                    throw new Error('账号要求已变化，请重新读取。');
                if (currentSlot.test_identity_id) {
                    const values = await api.list(projectId);
                    values.forEach(value => assertProject(value.project_id, projectId));
                    item = values.find(value => value.identity_id === currentSlot.test_identity_id);
                    if (!item)
                        throw new Error('账号清单已变化，请重新读取。');
                    if (item.status === 'PREPARED') {
                        state.reload();
                        return;
                    }
                    if (item.status === 'NEEDS_REVIEW') {
                        setReset(item.identity_id);
                        return;
                    }
                }
            }
            if (!item) {
                const request = { kind: 'create' as const, operation: operationId(), actor: slot.requirement.actor_id, revision: slot.requirement.actor_revision, label: slot.actor_display_name + '检查账号 ' + slot.requirement.ordinal };
                try {
                    remember(request);
                    item = await api.create(projectId, request.actor, request.revision, request.label, request.operation);
                    remember();
                    state.reload();
                }
                catch (error) {
                    if (error instanceof ApiError) remember();
                    throw error;
                }
            }
            try {
                const request = { kind: 'login' as const, operation: operationId(), identity: item.identity_id };
                remember(request);
                const next = await api.startPreparation(item.identity_id, request.operation);
                setLogin(next);
                if (requestedPreparation) go('/preparation?identities=1&preparation_id=' + next.preparation_id, projectId);
                remember();
            }
            catch (error) {
                if (error instanceof ApiError) remember();
                throw error;
            }
        });
    };
    const accounts = new Map<string, {
        slot: ActionPreparation['identity_requirements']['slots'][number];
        identity?: TestIdentityDto;
        actions: string[];
    }>();
    for (const action of state.data?.actions ?? actions)
        for (const slot of action.identity_requirements.slots) {
            const matches = state.data?.identities.filter(item => item.actor_id === slot.requirement.actor_id && item.actor_revision === slot.requirement.actor_revision) ?? [];
            const identity = state.data?.identities.find(item => item.identity_id === slot.test_identity_id) ?? (matches.length === 1 && matches[0].status === 'NEEDS_REVIEW' && slot.requirement.ordinal === 1 ? matches[0] : undefined);
            // 动作内的 slot_id 不代表独立账户；同角色同序号跨动作复用，已绑定的真实账户按身份保留。
            const id = identity ? 'identity:' + identity.identity_id : 'required:' + slot.requirement.actor_id + ':' + slot.requirement.actor_revision + ':' + slot.requirement.ordinal;
            const entry = accounts.get(id) ?? { slot, identity, actions: [] };
            if (!entry.actions.includes(action.display_name))
                entry.actions.push(action.display_name);
            accounts.set(id, entry);
        }
    const loginAccount = [...accounts.values()].find(item => item.identity?.identity_id === current?.identity_id);
    const accountEntries = [...accounts];
    const selectedId = accountEntries.find(([id]) => id === selectedAccount)?.[0]
        ?? accountEntries.find(([, item]) => item.identity?.identity_id === current?.identity_id)?.[0]
        ?? accountEntries.find(([, item]) => item.identity?.status !== 'PREPARED')?.[0] ?? accountEntries[0]?.[0];
    const readyCount = accountEntries.filter(([, item]) => item.identity?.status === 'PREPARED').length;
    const loginTitle = loginAccount ? text(loginAccount.slot.actor_display_name) + '账号登录' : '测试账号登录';
    const loginStep = current ? ({ STARTING: 0, WAITING_FOR_LOGIN: 1, SAVING: 2, PREPARED: 3, CANCELLING: -1, FAILED: -1, CANCELLED: -1, UNSUPPORTED: -1 })[current.status] : -1;
    const loginProgress = <>{current?.purpose==='VERIFY'&&<section className="jj-login-progress" aria-live="polite"><header><div><h2>核验已保存会话</h2><p>{text(current.message)}</p></div><Badge tone="neutral">{current.status==='PREPARED'?'已完成':'核验中'}</Badge></header>{active.error&&<ErrorNote error={active.error}/>}</section>}
    {current && current.purpose!=='VERIFY'&& <section className="jj-login-progress" data-status={current.status} data-terminal={['FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(current.status)} aria-label={loginTitle}>
      <header><span className="jj-login-symbol">{current.status === 'PREPARED' ? <CheckCircleOutlined aria-hidden="true"/> : <GlobalOutlined aria-hidden="true"/>}</span><div><div className="jj-login-heading"><h2>{loginTitle}</h2><span role="status"><Badge tone={current.status === 'PREPARED' ? 'positive' : current.status === 'FAILED' ? 'negative' : current.status === 'WAITING_FOR_LOGIN' ? 'accent' : 'neutral'}>{({ STARTING: '正在打开', WAITING_FOR_LOGIN: '等待登录', SAVING: '正在保存', CANCELLING: '正在取消', PREPARED: '已保存', FAILED: '未完成', CANCELLED: '已取消', UNSUPPORTED: '当前方式不支持' })[current.status]}</Badge></span></div>{!['FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(current.status) && <p>{current.status === 'WAITING_FOR_LOGIN' ? '请在已打开的独立浏览器中完成登录，再返回这里保存。' : text(current.message)}</p>}</div></header>
      {loginStep >= 0 && <ol className="jj-login-stages" aria-label="登录准备步骤">{['打开登录窗口', '在应用中登录', '保存登录状态'].map((label, index) => <li key={label} data-state={index < loginStep ? 'complete' : index === loginStep ? 'current' : 'pending'} aria-current={index === loginStep ? 'step' : undefined}><span aria-hidden="true">{index < loginStep ? <CheckOutlined/> : index + 1}</span><span>{label}</span></li>)}</ol>}
      {!['PREPARED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(current.status) && <footer className="jj-login-actions"><Button busy={busy} disabled={current.status === 'CANCELLING'} onClick={() => void act(async () => setLogin(await api.cancelPreparation(current.preparation_id)))}>取消本次登录</Button>{current.status === 'WAITING_FOR_LOGIN' && <Button kind="primary" busy={busy} onClick={() => void act(async () => setLogin(await api.confirmPreparation(current.preparation_id)))}>我已完成登录</Button>}</footer>}
      {current.status === 'PREPARED' && <footer className="jj-login-actions"><Button kind="primary" onClick={()=>{const next=accountEntries.find(([,item])=>item.identity?.status!=='PREPARED');if(next)setSelectedAccount(next[0]);else onBack()}}>{readyCount<accounts.size?'准备下一个账号':'继续准备其他材料'}</Button></footer>}{current.cleanup_required && <Notice>登录操作已结束，临时资源尚未完成清理，请保留当前账号。<Button busy={busy} onClick={() => void act(async () => setLogin(await api.cleanupPreparation(current.preparation_id)))}>重试清理临时资源</Button></Notice>}{active.error && <ErrorNote error={active.error} onRetry={active.reload}/>}
      {['FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(current.status) && <div className="jj-login-resolution"><p>{text(current.message)}</p>{current.status === 'FAILED' && !current.cleanup_required && loginAccount && <Button kind="primary" busy={busy} disabled={Boolean(pending) || Boolean(state.error)} onClick={() => prepare(loginAccount.identity, loginAccount.slot)}>重新打开登录窗口</Button>}</div>}
    </section>}</>;
    return <>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>检查准备</Button></div>
    <Heading title="准备测试账号" actions={<Button kind="quiet" busy={busy} onClick={() => void act(() => recover())}>刷新状态</Button>}/>
    {state.error && <ErrorNote error={state.error}/>}
    {requested.error && <ErrorNote error={requested.error} onRetry={requested.reload}/>}
    {pending && !current && <Notice>上次账号操作仍待确认。<Button busy={busy} onClick={() => void act(() => recover(true))}>查询并恢复本次操作</Button></Notice>}
    {state.loading ? <Loading page/> : <section className="jj-accounts-workspace">
      <header><div><h2>登录检查所需的账号</h2><p className="jj-small jj-muted">每个账号只需准备一次，可用于多项操作。</p></div><Badge tone={readyCount === accounts.size ? 'positive' : 'neutral'}>{readyCount} / {accounts.size} 已准备</Badge></header>
      <div className="jj-accounts-console"><nav className="jj-account-index" aria-label="待准备的账号">{accountEntries.map(([id,{slot,identity}])=><Button key={id} kind="quiet" aria-current={selectedId===id?'page':undefined} onClick={()=>setSelectedAccount(id)}><UserOutlined aria-hidden="true"/><span>{text(slot.actor_display_name)}账号{slot.requirement.ordinal>1?' '+slot.requirement.ordinal:''}<small>{identity?.status==='PREPARED'?'已准备':identity?.status==='NEEDS_REVIEW'?'需要重新登录':'待登录'}</small></span>{identity?.status==='PREPARED'&&<CheckOutlined aria-hidden="true"/>}</Button>)}</nav>
      <div className="jj-account-detail">{accountEntries.filter(([id])=>id===selectedId).map(([id, { slot, identity, actions: usedBy }]) => <article className="jj-account-row" data-current={current?.identity_id === identity?.identity_id && Boolean(identity)} key={id}>
        <header>
        <span className="jj-account-symbol"><UserOutlined aria-hidden="true"/></span>
        <div className="jj-account-body"><div className="jj-item-heading"><h3>{text(slot.actor_display_name)}账号{slot.requirement.ordinal > 1 ? ' ' + slot.requirement.ordinal : ''}</h3><Badge tone={identity?.status === 'PREPARED' ? 'positive' : identity?.status === 'NEEDS_REVIEW' ? 'caution' : 'neutral'}>{identity?.status === 'PREPARED' ? '已登录' : identity?.status === 'NEEDS_REVIEW' ? '需要核对' : '待登录'}</Badge></div>{identity && <p className="jj-small jj-muted">{text(identity.label)}</p>}</div>
        </header>
        <footer>
        <div className="jj-account-purpose"><span className="jj-eyebrow">这个账号用于</span><p>{usedBy.map(text).join('、')}</p></div>
        {current&&current.identity_id===identity?.identity_id&&!['CANCELLED','UNSUPPORTED'].includes(current.status)?loginProgress:<div className="jj-account-instruction"><h3>{identity?.status==='PREPARED'?'登录状态已保存':'使用应用自己的账号登录'}</h3><p>{identity?.status==='PREPARED'?'可以继续准备操作和结果证明。': '点击下方按钮，在单独打开的窗口中完成登录，再返回界鉴保存。'}</p>{identity?.verification&&<Badge tone={identity.verification.status==='VERIFIED'?'positive':'caution'}>{({VERIFIED:'登录身份匹配',AUTH_EXPIRED:'登录已失效',SUBJECT_MISMATCH:'登录的不是指定账号',ROLE_MISMATCH:'登录角色不符',FIELD_MISSING:'无法读取账号信息',UNAVAILABLE:'暂时无法核对账号'})[identity.verification.status]}</Badge>}</div>}
        {identity?.status!=='PREPARED'&&!(current&&current.identity_id===identity?.identity_id&&!['CANCELLED','UNSUPPORTED'].includes(current.status))&&<div className="jj-account-primary"><Button kind="primary" busy={busy} disabled={Boolean(pending) || Boolean(state.error) || !state.data || Boolean(current && !['PREPARED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(current.status))} onClick={() => prepare(identity, slot)}>{identity?.status === 'NEEDS_REVIEW' ? '重新登录此账号' : '开始登录'}</Button></div>}
        {identity&&<details className="jj-account-management"><summary>登录设置与管理</summary><div><span className="jj-small jj-muted">登录方式：{({BROWSER_SESSION:'在浏览器中登录',API_LOGIN:'使用账号和密码',BEARER:'使用访问令牌'})[identity.authentication?.method??'BROWSER_SESSION']}</span><div className="jj-inline-actions"><Button disabled={busy} onClick={()=>setAuthentication(identity)}>修改登录设置</Button>{identity.auth_method&&identity.authentication&&<Button disabled={busy} onClick={()=>void act(async()=>{const next={kind:'login' as const,identity:identity.identity_id,operation:operationId(),verifyOnly:true};remember(next);setLogin(await api.startPreparation(identity.identity_id,next.operation,true));remember()})}>检查登录是否有效</Button>}{identity.status==='PREPARED'&&<Button disabled={busy} onClick={()=>prepare(identity,slot)}>重新登录</Button>}</div></div></details>}
        </footer>
      </article>)}</div></div>
      {!accounts.size && <Empty title="当前权限没有账号要求"/>}{current&&!accountEntries.some(([,item])=>item.identity?.identity_id===current.identity_id)&&loginProgress}
      <footer className="jj-account-note"><span>登录信息仅用于当前应用的检查，保存在本机。</span><Button kind={readyCount===accounts.size?'primary':'quiet'} onClick={onBack}>{readyCount===accounts.size?'继续准备检查材料':'返回材料清单'}</Button></footer>
    </section>}
    {reset && <Dialog title="重新准备这个账号" onClose={() => setReset(undefined)} actions={dismiss => <><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} onClick={() => void act(async () => { await api.reset(reset); setReset(undefined); setLogin(undefined); state.reload(); })}>清除登录并重新准备</Button></>}><p>清除已保存的登录状态，账号身份和历史记录保留。重新登录后，界鉴会核验已有材料是否仍适用。</p></Dialog>}
    {authentication&&<AccountAuthentication identity={authentication} onClose={()=>setAuthentication(undefined)} onSaved={()=>state.reload()}/>}
  </>;
}
