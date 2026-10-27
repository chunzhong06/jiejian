import { useEffect, useRef, useState } from 'react';
import { ArrowLeftOutlined, UserOutlined } from '@ant-design/icons';
import { testIdentitiesApi as api, type IdentityPreparationDto, type TestIdentityDto } from '../../../entities/preparation/api/testIdentities';
import { preparationApi, type ActionPreparation } from '../../../entities/preparation/api/preparation';
import { ApiError } from '../../../shared/api/http';
import { assertProject } from '../../../shared/model/page';
import { text } from '../../../shared/lib/format';
import { useRead } from '../../../shared/lib/useRead';
import { Badge, Empty, ErrorNote, Loading, Notice } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import { Heading } from "../../../shared/ui/layout";
import { Dialog } from "../../../shared/ui/Dialog";
export function Accounts({ projectId, actions, onBack, onError }: {
    projectId: string;
    actions: ActionPreparation[];
    onBack: () => void;
    onError: (error: unknown) => void;
}) {
    const state = useRead('accounts:' + projectId, async (signal) => {
        const [identities, preparation] = await Promise.all([api.list(projectId, signal), preparationApi.get(projectId, signal)]);
        assertProject(preparation.project_id, projectId);
        identities.forEach(value => assertProject(value.project_id, projectId));
        if (preparation.actions.some(action => action.identity_requirements.slots.some(slot => slot.test_identity_id && !identities.some(item => item.identity_id === slot.test_identity_id))))
            throw new Error('账号清单已变化，请重新读取。');
        return { identities, actions: preparation.actions };
    });
    const pendingKey = 'jiejian.studio.login:' + projectId;
    const [reset, setReset] = useState<string>(), [busy, setBusy] = useState(false), [login, setLogin] = useState<IdentityPreparationDto>(), [unknown, setUnknown] = useState(Boolean(sessionStorage.getItem(pendingKey)));
    const lock = useRef(false);
    const active = useRead(login ? 'login:' + login.preparation_id : null, async () => login ? api.preparation(login.preparation_id) : null, value => value && !['PREPARED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(value.status) ? 1000 : 0);
    const current = active.data ?? login;
    useEffect(() => { if (current?.status === 'PREPARED')
        state.reload(); }, [current?.preparation_id, current?.status]);
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
                try {
                    sessionStorage.setItem(pendingKey, 'create');
                    item = await api.create(projectId, slot.requirement.actor_id, slot.requirement.actor_revision, slot.actor_display_name + '检查账号 ' + slot.requirement.ordinal);
                    sessionStorage.removeItem(pendingKey);
                    state.reload();
                }
                catch (error) {
                    if (!(error instanceof ApiError))
                        setUnknown(true);
                    else
                        sessionStorage.removeItem(pendingKey);
                    throw error;
                }
            }
            try {
                sessionStorage.setItem(pendingKey, 'login');
                setLogin(await api.startPreparation(item.identity_id));
                sessionStorage.removeItem(pendingKey);
            }
            catch (error) {
                if (!(error instanceof ApiError))
                    setUnknown(true);
                else
                    sessionStorage.removeItem(pendingKey);
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
    return <>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>检查准备</Button></div>
    <Heading title="测试账号" actions={<Button disabled={busy} onClick={state.reload}>读取账号状态</Button>}/>
    {state.error && <ErrorNote error={state.error}/>}
    {unknown && <Notice>账号操作结果尚未确认。请读取账号状态，避免重复建立账号或打开登录浏览器。</Notice>}
    {state.loading ? <Loading page/> : <section className="jj-accounts-workspace">
      <header><h2>本次需要的账号</h2><span>{accounts.size} 个账号</span></header>
      <div className="jj-account-list">{[...accounts].map(([id, { slot, identity, actions: usedBy }]) => <article className="jj-account-row" key={id}>
        <span className="jj-account-symbol"><UserOutlined aria-hidden="true"/></span>
        <div className="jj-account-body"><div className="jj-item-heading"><h3>{text(slot.actor_display_name)}账号{slot.requirement.ordinal > 1 ? ' ' + slot.requirement.ordinal : ''}</h3><Badge tone={identity?.status === 'PREPARED' ? 'positive' : identity?.status === 'NEEDS_REVIEW' ? 'caution' : 'neutral'}>{identity?.status === 'PREPARED' ? '已登录' : identity?.status === 'NEEDS_REVIEW' ? '需重新登录' : '待登录'}</Badge></div><p className="jj-small jj-muted">{identity ? text(identity.label) : '尚未建立测试账号'}</p></div>
        <p className="jj-account-uses">用于{usedBy.map(text).join('、')}</p>
        <Button busy={busy} disabled={unknown || Boolean(state.error) || !state.data || Boolean(current && !['PREPARED', 'FAILED', 'CANCELLED', 'UNSUPPORTED'].includes(current.status))} onClick={() => prepare(identity, slot)}>{identity?.status === 'PREPARED' ? '重新登录' : identity?.status === 'NEEDS_REVIEW' ? '核对并重新登录' : identity ? '打开登录浏览器' : '建立账号并登录'}</Button>
      </article>)}</div>
      {!accounts.size && <Empty title="当前权限没有账号要求"/>}
      <footer className="jj-account-note">登录信息保存在本地受控存储中，界面只显示准备状态。</footer>
    </section>}
    {current && <section className="jj-login-progress"><header><h2>{current.status === 'PREPARED' ? '登录已保存' : current.status === 'WAITING_FOR_LOGIN' ? '请在独立浏览器中登录' : '登录准备'}</h2><Badge>{({ STARTING: '正在打开', WAITING_FOR_LOGIN: '等待登录', SAVING: '正在保存', CANCELLING: '正在取消', PREPARED: '已完成', FAILED: '未完成', CANCELLED: '已取消', UNSUPPORTED: '当前方式不支持' })[current.status]}</Badge></header>
      {current.status === 'WAITING_FOR_LOGIN' && <div className="jj-inline-actions"><Button kind="primary" busy={busy} onClick={() => void act(async () => setLogin(await api.confirmPreparation(current.preparation_id)))}>我已完成登录</Button><Button busy={busy} onClick={() => void act(async () => setLogin(await api.cancelPreparation(current.preparation_id)))}>取消本次登录</Button></div>}
      {current.status === 'PREPARED' && <Button kind="primary" onClick={onBack}>返回材料清单</Button>}{current.error_code && <Notice>这次登录未完成，请核对登录浏览器与应用状态。</Notice>}
    </section>}
    {reset && <Dialog title="重新准备这个账号" onClose={() => setReset(undefined)} actions={dismiss => <><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} onClick={() => void act(async () => { await api.reset(reset); setReset(undefined); setLogin(undefined); state.reload(); })}>清除登录并重新准备</Button></>}><p>这会清除该测试账号已保存的登录信息，相关材料需要重新核对。清除后可打开独立浏览器重新登录。</p></Dialog>}
  </>;
}
