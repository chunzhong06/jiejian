import {TaskSurface} from '../../shared/ui/TaskSurface'
import {DisclosureMarker} from '../../shared/ui/DisclosureMarker'
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import './workspace.css'
import { useEffect, useState } from 'react';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import CodeOutlined from '@ant-design/icons/CodeOutlined';
import { sourceChangesApi, type SourceChangeViewDto } from '../../entities/source-change/api/sourceChanges';
import { ChangeRegistration, changeTargetOptions } from '../../entities/source-change/ui/ChangeRegistration';
import { ruleWorkspaceApi } from '../../entities/permission/api/ruleWorkspace';
import { RuntimeActivation } from '../../entities/source-change/ui/RuntimeActivation';
import { developmentApi } from '../../entities/source-change/api/development';
import { repairsApi, repairReference } from '../../entities/check/api/repairs';
import type { WorkspaceViewDto } from '../../entities/workspace/api/workspace';
import {Button,ActionLink} from '../../shared/ui/actions'
import {PageError,  Badge, Empty, ErrorNote, Loading, Notice } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
import { assertProject, type PageProps } from '../../shared/model/page';
import { date, text } from '../../shared/lib/format';
import {go,returnDestination,returnDestinationLabel,withReturnDestination,scopedPath} from '../../shared/lib/navigation'
import { useRead } from '../../shared/lib/useRead';
const readiness: Record<SourceChangeViewDto['revalidation']['status'], string> = { READY: '可预览检查', NO_BASELINE: '缺少对照起点', SOURCE_STALE: '源码已更新', POLICY_STALE: '规则已更新', MAPPING_REVIEW_REQUIRED: '需核对业务实现' };
export function Changes({ projectId, official, onError, refresh, route, workspace }: PageProps & {
    workspace?: WorkspaceViewDto | null;
}) {
    const origin=returnDestination(route.query.get('return_to'))
    const changePath=(id:string)=>{const path='/changes?change_id='+encodeURIComponent(id);return origin?withReturnDestination(path,origin):path}
    const [register, setRegister] = useState(route.query.get('view') === 'register'), [focused, setFocused] = useState<string>();
    useEffect(() => { if (route.query.get('view') === 'register') setRegister(true); }, [route.query.get('view')]);
    const ruleState = useRead('registration-rules:' + projectId + ':' + register, async () => {
        if (!register) return null;
        const value = await ruleWorkspaceApi.read(projectId); assertProject(value.project_id, projectId); return value;
    });
    const state = useRead('changes:' + projectId, async () => { const [changes, repair] = await Promise.all([sourceChangesApi.list(projectId), repairsApi.project(projectId)]); assertProject(repair.project_id, projectId); changes.forEach(item => assertProject(item.manifest.project_id, projectId)); return { changes, repair }; });
    const reference = route.query.get('repair_reference'), selected = route.query.get('change_id'), expanded = selected ?? focused;
    const detail = useRead('change-detail:' + projectId + ':' + expanded, async () => { if (!expanded)
        return null; const value = await developmentApi.details(projectId, expanded); if (value) {
        assertProject(value.project_id, projectId);
        if (value.delivery.change_id !== expanded)
            throw new Error('修改记录与检查关联不一致。');
    } return value; });
    const contract = state.data?.repair.tasks.find(item => item.contract.repair_fingerprint === reference)?.contract;
    const repairRule = ruleState.data?.rules.find(rule => rule.issues.some(issue => issue.contract.repair_fingerprint === reference));
    const changes = selected ? state.data?.changes.filter(item => item.manifest.change_id === selected) : state.data?.changes;
    if (state.loading)
        return <PageSkeleton view="/changes"/>;
    if (state.error)
        return <PageError title="源码修改" error={state.error}/>;
    if(register)return <TaskSurface title="登记已完成的源码修改" context={repairRule?.title} onBack={()=>setRegister(false)} backLabel="返回源码修改">{ruleState.loading ? <Loading>正在读取可关联的权限</Loading> : ruleState.error ? <ErrorNote error={ruleState.error}/> : reference && (!contract || !repairRule) ? <Notice tone="caution">原问题不在当前有效规则中，请从权限规则重新选择修改范围。</Notice> : <ChangeRegistration embedded projectId={projectId} options={changeTargetOptions(ruleState.data?.rules ?? [])} initialTargets={contract ? [{permission: repairRule!.permission, repair: repairReference(contract)}] : []} onClose={() => setRegister(false)} onError={onError} onSaved={id => { setRegister(false); state.reload(); refresh(); go(changePath(id)); }}/>}</TaskSurface>;
    return <>
    {origin&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin)} kind="quiet">{returnDestinationLabel(origin)}</ActionLink></div>}
    <Heading title="源码修改" actions={!register && Boolean(changes?.length) && <Button kind="primary" onClick={() => setRegister(true)}>登记本地修改</Button>}/>
    {selected && <div className="jj-back-link"><Button kind="quiet" onClick={() => { setFocused(undefined); go('/changes'); }}>全部修改记录</Button></div>}
    {contract && <section className="jj-repair-scope"><header><Badge tone="accent">原问题修复</Badge><h2>本次修复范围</h2><ActionLink navigationScope="page" href={'#'+scopedPath('/reports?run_id=' + encodeURIComponent(contract.source_run_id) + '&case_id=' + encodeURIComponent(contract.source_case_id) + '&return_to=' + encodeURIComponent('/changes?'+route.query))} kind="quiet">阅读原问题依据<ArrowRightOutlined aria-hidden="true"/></ActionLink></header><div><section><h3>消除原权限问题</h3><p>使用原问题的账号、资源和检查要求，验证禁止的业务结果不再发生。</p></section><section><h3>保留正常功能</h3><p>正常允许的操作及其他相关业务继续接受回归检查。</p></section></div></section>}
    {reference && !contract && <Notice tone="caution">没有找到与这个修复引用对应的原问题，请从报告重新打开。</Notice>}

    {!register&&changes?.length ? <section className="jj-changes-workspace"><header><h2>修改记录</h2><span>{changes.length} 次登记</span></header>
      {changes.map(item => {
                const id = item.manifest.change_id, open = expanded === id, verification = open ? detail.data?.verification : undefined;
                return <article className="jj-change-entry" key={id}>
        <button className="jj-change-select" aria-expanded={open} aria-controls={'change-' + id} onClick={() => setFocused(open ? undefined : id)} disabled={Boolean(selected)}>
          <span className="jj-change-time"><time>{date(item.manifest.created_at_us)}</time><small>{text(item.manifest.submitted_by === 'LOCAL_GUI' ? '在界鉴中登记' : item.manifest.submitted_by === 'MCP' ? '通过开发工具登记' : item.manifest.submitted_by || '本地登记')}</small></span>
          <span className="jj-change-name"><span className="jj-object-line"><strong>{changeTitle(item.manifest.reason, official)}</strong><Badge tone={item.revalidation.can_execute ? 'neutral' : 'caution'}>{readiness[item.revalidation.status]}</Badge></span><small>{item.change_set.status === 'NO_BASELINE' ? '尚无可比较的源码起点' : `${item.change_set.added_paths.length + item.change_set.modified_paths.length + item.change_set.removed_paths.length} 个文件发生变化`}{item.manifest.repair_reference ? '，按原问题复验' : ''}</small></span>
          <DisclosureMarker expanded={open}/>
        </button>
        {open && <div className="jj-change-detail" id={'change-' + id}>
          {detail.data && <RuntimeActivation projectId={projectId} details={detail.data} onError={onError} onChanged={() => { detail.reload(); refresh(); }}/>}<div className="jj-change-evidence"><section><h3>变化范围</h3><div className="jj-change-files">{([['added_paths', '新增'], ['modified_paths', '修改'], ['removed_paths', '删除']] as const).map(([key, label]) => item.change_set[key].length > 0 && <details key={key}><summary>{label} {item.change_set[key].length} 个文件</summary>{item.change_set[key].map(path => <p className="jj-path" key={path}>{path}</p>)}</details>)}</div>{item.change_set.status === 'NO_BASELINE' && <p className="jj-small jj-muted">缺少可比较的源码起点。</p>}
            {item.assessment.payload.action_impacts.length > 0 && <details className="jj-change-impacts"><summary>相关业务操作</summary>{item.assessment.payload.action_impacts.map(impact => <div key={impact.action_id}><strong>{text(workspace?.actions.find(action => action.action_id === impact.action_id && action.action_revision === impact.action_revision)?.display_name ?? '本次业务操作')}</strong><span>{impact.classification === 'DIRECTLY_AFFECTED' ? '直接受影响' : impact.classification === 'MAPPING_REVIEW_REQUIRED' ? '需核对实现对应' : '未发现直接影响证据'}</span></div>)}</details>}
          </section><section className="jj-change-verification"><div className="jj-object-line"><h3>关联检查</h3>{!detail.loading&&!detail.error&&verification?.run_id&&<Badge tone={verification.verdict === 'PASS' ? 'positive' : verification.verdict === 'BLOCK' ? 'negative' : verification.verdict === 'INCONCLUSIVE' ? 'caution' : 'neutral'}>{verification.repair_status === 'VERIFIED' ? '已通过原问题验证' : verification.verdict === 'PASS' ? '本次范围符合规则' : verification.verdict === 'BLOCK' ? '存在不符合规则的结果' : verification.verdict === 'INCONCLUSIVE' ? '部分检查证据不足' : '尚未形成结论'}</Badge>}</div>{detail.loading ? <Loading>正在读取关联记录</Loading> : detail.error ? <ErrorNote error={detail.error}/> : verification?.run_id ? <><ActionLink navigationScope="page" href={'#'+scopedPath('/reports?run_id=' + encodeURIComponent(verification.run_id!) + '&return_to=' + encodeURIComponent(changePath(id)))} kind="quiet">阅读本批报告<ArrowRightOutlined aria-hidden="true"/></ActionLink></> : verification?.same_source_run_id ? <><p>同版源码有检查记录，尚未关联本批。</p><ActionLink navigationScope="page" href={'#'+scopedPath('/reports?run_id=' + encodeURIComponent(verification.same_source_run_id!) + '&return_to=' + encodeURIComponent(changePath(id)))} kind="quiet">查看同版源码报告<ArrowRightOutlined aria-hidden="true"/></ActionLink></> : <p className="jj-small jj-muted">这次修改还没有关联的检查记录。</p>}</section></div>
          <footer><span className="jj-small jj-muted">检查前会重新核对当前代码、规则和材料。</span><div className="jj-inline-actions">{item.revalidation.preparation_gaps.length > 0 && <ActionLink navigationScope="page" href={'#'+scopedPath('/preparation?change_id=' + encodeURIComponent(id) + '&return_to=' + encodeURIComponent(changePath(id)))}  kind="default">核对准备材料</ActionLink>}<ActionLink navigationScope="page" href={'#'+scopedPath('/reports?view=plan&change_id=' + encodeURIComponent(id) + '&return_to=' + encodeURIComponent(changePath(id)))} kind="primary">{item.manifest.repair_reference ? '预览原问题复验' : '预览修改后检查'}<ArrowRightOutlined aria-hidden="true"/></ActionLink></div></footer>
        </div>}
      </article>;
            })}
    </section> : !register && <Empty layout="section" title="尚未登记源码修改" action={!register && <Button kind="primary" onClick={() => setRegister(true)} icon={<CodeOutlined aria-hidden="true"/>}>登记本地修改</Button>}>完成当前应用的代码修改后，在这里登记文件差异，再核对运行版本并复验。</Empty>}
  </>;
}
function changeTitle(reason: string, official: boolean) {
    const match = official ? reason.match(/^预设演示[：:]\s*(BASELINE|VULNERABLE|EXPOSE_REVOKE|FIXED|PREVIEW_CHANGED)$/) : null;
    const labels: Record<string, string> = { BASELINE: '正常访问限制', VULNERABLE: '移除内部包下载限制', EXPOSE_REVOKE: '处理中开放后再撤回', FIXED: '恢复内部包访问限制', PREVIEW_CHANGED: '调整公开预览内容' };
    return text(match ? labels[match[1]] : reason);
}
