import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import './workspace.css'
import { useEffect, useRef, useState } from 'react';
import { ArrowRightOutlined, DownOutlined, CodeOutlined } from '@ant-design/icons';
import { sourceChangesApi, type SourceChangeViewDto } from '../../entities/source-change/api/sourceChanges';
import { developmentApi } from '../../entities/source-change/api/development';
import { repairsApi, repairReference } from '../../entities/check/api/repairs';
import type { WorkspaceViewDto } from '../../entities/workspace/api/workspace';
import { Button } from "../../shared/ui/actions";
import { Badge, Empty, ErrorNote, Loading, Notice } from "../../shared/ui/feedback";
import { Field, Heading } from "../../shared/ui/layout";
import { assertProject, type PageProps } from '../../shared/model/page';
import { date, text } from '../../shared/lib/format';
import { go } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
const readiness: Record<SourceChangeViewDto['revalidation']['status'], string> = { READY: '可预览检查', NO_BASELINE: '缺少对照起点', SOURCE_STALE: '源码已更新', POLICY_STALE: '规则已更新', MAPPING_REVIEW_REQUIRED: '需核对业务实现' };
export function Changes({ projectId, official, onError, refresh, route, workspace }: PageProps & {
    workspace?: WorkspaceViewDto | null;
}) {
    const [reason, setReason] = useState(''), [busy, setBusy] = useState(false), [register, setRegister] = useState(route.query.get('view') === 'register'), [pending, setPending] = useState<string | null>(() => sessionStorage.getItem('jiejian.studio.change:' + projectId)), [focused, setFocused] = useState<string>(), lock = useRef(false);
    useEffect(() => { if (route.query.get('view') === 'register')
        setRegister(true); }, [route.query.get('view')]);
    const state = useRead('changes:' + projectId, async () => { const [changes, repair] = await Promise.all([sourceChangesApi.list(projectId), repairsApi.project(projectId)]); assertProject(repair.project_id, projectId); changes.forEach(item => assertProject(item.manifest.project_id, projectId)); return { changes, repair }; });
    const reference = route.query.get('repair_reference'), selected = route.query.get('change_id'), expanded = selected ?? focused;
    const detail = useRead('change-detail:' + projectId + ':' + expanded, async () => { if (!expanded)
        return null; const value = await developmentApi.details(projectId, expanded); if (value) {
        assertProject(value.project_id, projectId);
        if (value.delivery.change_id !== expanded)
            throw new Error('修改记录与检查关联不一致。');
    } return value; });
    const contract = state.data?.repair.tasks.find(item => item.contract.repair_fingerprint === reference)?.contract;
    const changes = selected ? state.data?.changes.filter(item => item.manifest.change_id === selected) : state.data?.changes;
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
    const accept = () => { setPending(null); sessionStorage.removeItem('jiejian.studio.change:' + projectId); setRegister(false); state.reload(); refresh(); };
    if (state.loading)
        return <PageSkeleton view="/changes"/>;
    if (state.error)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    return <>
    <Heading title="源码修改" actions={!register && <Button kind="primary" onClick={() => setRegister(true)}>{pending ? '查询登记回执' : '登记本地修改'}</Button>}/>
    {selected && <div className="jj-back-link"><Button kind="quiet" onClick={() => { setFocused(undefined); go('/changes'); }}>全部修改记录</Button></div>}
    {contract && <section className="jj-repair-scope"><header><Badge tone="accent">原题修复</Badge><h2>本次修复范围</h2><Button kind="quiet" onClick={() => go('/reports?run_id=' + encodeURIComponent(contract.source_run_id) + '&case_id=' + encodeURIComponent(contract.source_case_id))}>阅读原问题依据<ArrowRightOutlined aria-hidden="true"/></Button></header><div><section><h3>消除原权限问题</h3><p>使用原问题的账号、资源和检查要求，验证禁止的业务结果不再发生。</p></section><section><h3>保留正常功能</h3><p>正常允许的操作及其他相关业务继续接受回归检查。</p></section></div></section>}
    {reference && !contract && <Notice>没有找到与这个修复引用对应的原问题，请从报告重新打开。</Notice>}
    {register && <section className="jj-change-registration"><header><h2>登记已完成的修改</h2><p>界鉴会读取真实代码变化。登记完成后，再预览检查范围。</p></header><div><Field label="修改说明"><textarea disabled={busy || Boolean(pending)} value={reason} onChange={event => setReason(event.target.value)} placeholder="说明本次修改了什么"/></Field></div><footer><Button disabled={busy} onClick={() => setRegister(false)}>收起</Button>{pending ? <Button busy={busy} onClick={() => void act(async () => { const receipt = await developmentApi.receipt(projectId, 'DELIVER', pending); if (!receipt)
        throw new Error('原登记回执尚未找到，请稍后查询。'); assertProject(receipt.project_id, projectId); accept(); if (receipt.change_id)
        go('/changes?change_id=' + receipt.change_id); })}>查询本次登记</Button> : <Button kind="primary" disabled={!reason.trim() || Boolean(reference && !contract)} busy={busy} onClick={() => void act(async () => { const preview = await sourceChangesApi.registrationPreview(projectId); assertProject(preview.project_id, projectId); const operation = crypto.randomUUID().replaceAll('-', ''); sessionStorage.setItem('jiejian.studio.change:' + projectId, operation); setPending(operation); const receipt = await sourceChangesApi.register(projectId, { operation_id: operation, expected_registration_fingerprint: preview.fingerprint, reason: reason.trim(), claimed_paths: [], repair_reference: contract ? repairReference(contract) : null }); assertProject(receipt.project_id, projectId); accept(); if (receipt.change_id)
        go('/changes?change_id=' + receipt.change_id); })}>保存修改记录</Button>}</footer></section>}
    {changes?.length ? <section className="jj-changes-workspace"><header><h2>修改记录</h2><span>{changes.length} 次登记</span></header>
      {changes.map(item => {
                const id = item.manifest.change_id, open = expanded === id, verification = open ? detail.data?.verification : undefined;
                return <article className="jj-change-entry" key={id}>
        <button className="jj-change-select" aria-expanded={open} aria-controls={'change-' + id} onClick={() => setFocused(open ? undefined : id)} disabled={Boolean(selected)}>
          <span className="jj-change-time"><time>{date(item.manifest.created_at_us)}</time><small>{text(item.manifest.submitted_by || '本地登记')}</small></span>
          <span className="jj-change-name"><strong>{changeTitle(item.manifest.reason, official)}</strong><small>{item.change_set.status === 'NO_BASELINE' ? '尚无可比较的源码起点' : `${item.change_set.added_paths.length + item.change_set.modified_paths.length + item.change_set.removed_paths.length} 个文件发生变化`}{item.manifest.repair_reference ? '，按原题复验' : ''}</small></span>
          <Badge tone={item.revalidation.can_execute ? 'neutral' : 'caution'}>{readiness[item.revalidation.status]}</Badge><DownOutlined aria-hidden="true"/>
        </button>
        {open && <div className="jj-change-detail" id={'change-' + id}>
          <div className="jj-change-evidence"><section><h3>变化范围</h3><div className="jj-change-files">{([['added_paths', '新增'], ['modified_paths', '修改'], ['removed_paths', '删除']] as const).map(([key, label]) => item.change_set[key].length > 0 && <details key={key}><summary>{label} {item.change_set[key].length} 个文件</summary>{item.change_set[key].map(path => <p className="jj-path" key={path}>{path}</p>)}</details>)}</div>{item.change_set.status === 'NO_BASELINE' && <p className="jj-small jj-muted">缺少可比较的源码起点。</p>}
            {item.assessment.payload.action_impacts.length > 0 && <details className="jj-change-impacts"><summary>相关业务操作</summary>{item.assessment.payload.action_impacts.map(impact => <div key={impact.action_id}><strong>{text(workspace?.actions.find(action => action.action_id === impact.action_id && action.action_revision === impact.action_revision)?.display_name ?? '本次业务操作')}</strong><span>{impact.classification === 'DIRECTLY_AFFECTED' ? '直接受影响' : impact.classification === 'MAPPING_REVIEW_REQUIRED' ? '需核对实现对应' : '未发现直接影响证据'}</span></div>)}</details>}
          </section><section className="jj-change-verification"><h3>关联检查</h3>{detail.loading ? <Loading>正在读取关联记录</Loading> : detail.error ? <ErrorNote error={detail.error} onRetry={detail.reload}/> : verification?.run_id ? <><Badge tone={verification.verdict === 'PASS' ? 'positive' : verification.verdict === 'BLOCK' ? 'negative' : verification.verdict === 'INCONCLUSIVE' ? 'caution' : 'neutral'}>{verification.repair_status === 'VERIFIED' ? '已通过原题验证' : verification.verdict === 'PASS' ? '本次范围符合规则' : verification.verdict === 'BLOCK' ? '存在不符合规则的结果' : verification.verdict === 'INCONCLUSIVE' ? '部分结果尚未确认' : '尚未形成结论'}</Badge><Button kind="quiet" onClick={() => go('/reports?run_id=' + encodeURIComponent(verification.run_id!))}>阅读本批报告<ArrowRightOutlined aria-hidden="true"/></Button></> : verification?.same_source_run_id ? <><p>同版源码有检查记录，尚未关联本批。</p><Button kind="quiet" onClick={() => go('/reports?run_id=' + encodeURIComponent(verification.same_source_run_id!))}>查看同版源码报告<ArrowRightOutlined aria-hidden="true"/></Button></> : <p className="jj-small jj-muted">本批尚未关联检查。</p>}</section></div>
          <footer><span className="jj-small jj-muted">检查前会重新核对当前代码、规则和材料。</span><div className="jj-inline-actions">{item.revalidation.preparation_gaps.length > 0 && <Button onClick={() => go('/preparation?change_id=' + encodeURIComponent(id))}>核对准备材料</Button>}<Button kind="primary" onClick={() => go('/reports?view=plan&change_id=' + encodeURIComponent(id))}>{item.manifest.repair_reference ? '预览原题复验' : '预览修改后检查'}<ArrowRightOutlined aria-hidden="true"/></Button></div></footer>
        </div>}
      </article>;
            })}
    </section> : <Empty title="尚未登记源码修改" action={!register && <Button onClick={() => setRegister(true)} icon={<CodeOutlined aria-hidden="true"/>}>登记本地修改</Button>}>在开发工具完成修改后，再将实际变化登记到这里。</Empty>}
  </>;
}
function changeTitle(reason: string, official: boolean) {
    const match = official ? reason.match(/^预设演示[：:]\s*(BASELINE|VULNERABLE|EXPOSE_REVOKE|FIXED|PREVIEW_CHANGED)$/) : null;
    const labels: Record<string, string> = { BASELINE: '正常访问限制', VULNERABLE: '移除内部包下载限制', EXPOSE_REVOKE: '处理中开放后再撤回', FIXED: '恢复内部包访问限制', PREVIEW_CHANGED: '调整公开预览内容' };
    return text(match ? labels[match[1]] : reason);
}
