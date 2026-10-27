import { useRef, useState } from 'react';
import { experienceApi, type OfficialScenarioVersion } from '../../entities/application/api/experience';
import { repairsApi, repairReference } from '../../entities/check/api/repairs';
import { ApiError } from '../../shared/api/http';
import { Choice } from "../../shared/ui/Choice";
import { Badge, ErrorNote, Loading, Notice } from "../../shared/ui/feedback";
import { Button } from "../../shared/ui/actions";
import { Dialog } from "../../shared/ui/Dialog";
import { Field } from "../../shared/ui/layout";
import { assertProject } from '../../shared/model/page';
import { go } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
const versions: Array<{
    id: OfficialScenarioVersion;
    label: string;
    meaning: string;
}> = [{ id: 'BASELINE', label: '正常访问限制', meaning: '负责人可取自己的资料，评审只能访问已公开的内容。' }, { id: 'VULNERABLE', label: '内部包下载限制被移除', meaning: '预置修改取消了内部包下载入口的访问限制，用实际检查核对后果。' }, { id: 'EXPOSE_REVOKE', label: '处理中开放后再撤回', meaning: '预置修改会在处理过程中开放内部资料访问权，然后撤回。' }, { id: 'FIXED', label: '恢复访问限制', meaning: '预置修复恢复内部包访问限制，并使用原问题的要求复验。' }, { id: 'PREVIEW_CHANGED', label: '调整公开预览内容', meaning: '只改变公开预览的展示内容，检查既有权限要求是否继续成立。' }];
export function ExampleLab({ projectId, onError, onChanged }: {
    projectId: string;
    onError: (error: unknown) => void;
    onChanged: () => void;
}) {
    const state = useRead('example-lab:' + projectId, signal => experienceApi.status(undefined, true, signal)), repair = useRead('example-repair:' + projectId, () => repairsApi.project(projectId));
    const [selected, setSelected] = useState<OfficialScenarioVersion>('VULNERABLE'), [confirm, setConfirm] = useState(false), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false), lock = useRef(false);
    const value = versions.find(item => item.id === selected)!, contract = repair.data?.tasks.find(item => ['REPAIR_REQUIRED', 'CHANGE_SUBMITTED', 'READY_TO_VERIFY'].includes(item.status))?.contract;
    const switchVersion = async () => { if (lock.current)
        return; lock.current = true; setBusy(true); try {
        const result = await experienceApi.switchVersion(selected, selected === 'FIXED' && contract ? repairReference(contract) : undefined);
        assertProject(result.project_id ?? '', projectId);
        setConfirm(false);
        state.reload();
        onChanged();
        go('/preparation' + (result.current_change_id ? '?change_id=' + encodeURIComponent(result.current_change_id) : ''));
    }
    catch (error) {
        setUncertain(!(error instanceof ApiError));
        onError(error);
    }
    finally {
        lock.current = false;
        setBusy(false);
    } };
    return <details className="jj-example-lab"><summary>切换示例实现</summary>{state.loading ? <Loading>正在读取当前实现</Loading> : state.error ? <ErrorNote error={state.error} onRetry={state.reload}/> : <><div className="jj-example-current"><span>当前运行</span><strong>{versions.find(item => item.id === state.data?.scenario_version)?.label ?? '本地修改的实现'}</strong><Badge tone={state.data?.active ? 'positive' : 'neutral'}>{state.data?.active ? '运行中' : '已停止'}</Badge></div><div className="jj-example-lab-content">
    <Field label="选择要加载的实现"><Choice value={selected} onValueChange={value => setSelected(value as OfficialScenarioVersion)} disabled={busy || uncertain}>{versions.filter(item => state.data?.runtime_kind !== 'NODE_ESM' || item.id !== 'BASELINE').map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Choice></Field>
    <div><h3>{value.label}</h3><p className="jj-example-meaning">{value.meaning}</p><div className="jj-confirmation-actions">{state.data?.runtime_kind !== 'NODE_ESM' && <Button disabled={!state.data?.active || busy || uncertain} onClick={() => void (async () => { lock.current = true; setBusy(true); try {
            await experienceApi.observation(state.data?.evidence_limited === true);
            state.reload();
            onChanged();
            go('/preparation');
        }
        catch (error) {
            setUncertain(true);
            onError(error);
        }
        finally {
            lock.current = false;
            setBusy(false);
        } })()}>{state.data?.evidence_limited ? '恢复业务记录采集' : '暂停业务记录采集'}</Button>}<Button disabled={busy || uncertain || !state.data?.active || selected === 'FIXED' && !contract} onClick={() => setConfirm(true)}>加载这份示例源码</Button></div></div>
    {uncertain && <Notice>修改结果尚未确认，先读取当前实现状态。<Button onClick={() => { state.reload(); onChanged(); }}>读取当前状态</Button></Notice>}
    {selected === 'FIXED' && !contract && <p className="jj-small jj-muted">从问题报告发起原题修复后，可加载修复实现。</p>}
  </div></>}{confirm && <Dialog title="加载示例源码" onClose={() => setConfirm(false)} actions={dismiss => <><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} onClick={() => void switchVersion()}>确认加载</Button></>}><p>{value.meaning}</p><p>这会替换独立示例的运行实现。已有权限和报告保留，受影响的登录与材料需要重新核对。</p></Dialog>}</details>;
}
