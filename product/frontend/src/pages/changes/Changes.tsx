import {useEffect, useRef, useState} from 'react';
import {ChangeContinuation} from '../../entities/source-change/ui/ChangeContinuation';
import {CurrentDiscoveryCoverage} from '../../entities/permission/ui/DiscoveryCoverage';
import {sourceChangesApi, type SourceChangeViewDto} from '../../entities/source-change/api/sourceChanges';
import {ChangeRegistration, changeTargetOptions} from '../../entities/source-change/ui/ChangeRegistration';
import {RuntimeActivation} from '../../entities/source-change/ui/RuntimeActivation';
import {developmentApi, type DeliveryDetails} from '../../entities/source-change/api/development';
import {ruleWorkspaceApi} from '../../entities/permission/api/ruleWorkspace';
import {repairsApi, repairReference} from '../../entities/check/api/repairs';
import type {WorkspaceViewDto} from '../../entities/workspace/api/workspace';
import {assertProject, type PageProps} from '../../shared/model/page';
import {date, text} from '../../shared/lib/format';
import {go, returnDestination, returnDestinationLabel, withReturnDestination, scopedPath} from '../../shared/lib/navigation';
import {useRead} from '../../shared/lib/useRead';
import {useDirectoryState} from '../../shared/lib/directoryState';
import {Button, ActionLink} from '../../shared/ui/actions';
import {Badge, Empty, ErrorNote, Loading, Notice, PageError} from '../../shared/ui/feedback';
import {Heading, SectionHeading, TaskActions, TaskFrame} from '../../shared/ui/layout';
import {TaskSurface} from '../../shared/ui/TaskSurface';
import {PageSkeleton} from '../../shared/ui/PageSkeleton';
import {SearchField} from '../../shared/ui/SearchField';
import {ObjectTable} from '../../shared/ui/ObjectTable';
import './workspace.css';

const readiness:Record<SourceChangeViewDto['revalidation']['status'],string> = {READY:'可预览检查', NO_BASELINE:'缺少对照起点', SOURCE_STALE:'源码已更新', POLICY_STALE:'规则已更新', MAPPING_REVIEW_REQUIRED:'需核对业务实现'};
const submittedBy = (channel:string) => text(channel === 'LOCAL_GUI' ? '在界鉴中登记' : channel === 'MCP' ? '通过开发工具登记' : channel || '本地登记');
const fileCount = (item:SourceChangeViewDto) => item.change_set.added_paths.length + item.change_set.modified_paths.length + item.change_set.removed_paths.length;

export function Changes({projectId, official, onError, refresh, route, workspace}:PageProps & {workspace?:WorkspaceViewDto|null}) {
  const origin = returnDestination(route.query.get('return_to'));
  const before = route.query.get('before_change_id');
  const baseListPath = '/changes' + (before ? '?before_change_id=' + encodeURIComponent(before) : '');
  const listPath = origin ? withReturnDestination(baseListPath, origin) : baseListPath;
  const changePath = (id:string) => {const path='/changes?change_id='+encodeURIComponent(id)+(before?'&before_change_id='+encodeURIComponent(before):'');return origin?withReturnDestination(path,origin):path;};
  const selected = route.query.get('change_id'), reference = route.query.get('repair_reference');
  const [register, setRegister] = useState(route.query.get('view') === 'register');
  const [registrationBusy, setRegistrationBusy] = useState(false);
  useEffect(() => setRegister(route.query.get('view') === 'register'), [route.query.get('view')]);
  const state = useRead(!selected && !register ? 'changes:' + projectId + ':' + (before ?? 'latest') : null, async () => {
    const values = await sourceChangesApi.list(projectId,50,before??undefined);
    values.forEach(item => assertProject(item.manifest.project_id, projectId));
    return values;
  });
  // 准确深链独立读取，不受最近记录窗口限制，也不以另一条记录代替缺失对象。
  const record = useRead(selected && !register ? 'change:' + projectId + ':' + selected : null, async () => {
    const value = await sourceChangesApi.show(projectId, selected!);
    assertProject(value.manifest.project_id, projectId);
    if (value.manifest.change_id !== selected) throw new Error('修改记录与所选对象不一致。');
    return value;
  });
  const detail = useRead(selected && !register ? 'change-detail:' + projectId + ':' + selected : null, async () => {
    const value = await developmentApi.details(projectId, selected!);
    if (value) {
      assertProject(value.project_id, projectId);
      if (value.delivery.change_id !== selected) throw new Error('修改记录与检查关联不一致。');
    }
    return value;
  });
  const ruleState = useRead(register ? 'registration-rules:' + projectId : null, async () => {
    const value = await ruleWorkspaceApi.read(projectId); assertProject(value.project_id, projectId); return value;
  });
  const repairState = useRead(register && reference ? 'registration-repair:' + projectId + ':' + reference : null, async () => {
    const value = await repairsApi.project(projectId); assertProject(value.project_id, projectId); return value;
  });
  const contract = repairState.data?.tasks.find(item => item.contract.repair_fingerprint === reference)?.contract;
  const repairRule = ruleState.data?.rules.find(rule => rule.issues.some(issue => issue.contract.repair_fingerprint === reference));
  const finishRegistration = (id?:string) => {
    if (origin && reference) {
      const [path, query] = origin.split('?'), params = new URLSearchParams(query);
      if (id) params.set('change_id', id);
      go(path + (params.size ? '?' + params : ''));
    } else { setRegister(false); go(id ? changePath(id) : listPath); }
  };
  if (register) return <TaskSurface title="登记已完成的源码修改" context={repairRule?.title} onBack={() => finishRegistration()} backDisabled={registrationBusy} backLabel={origin && reference ? '返回原问题' : '返回源码修改'}>
    {ruleState.loading || repairState.loading ? <Loading>正在读取可关联的权限</Loading> : ruleState.error || repairState.error ? <ErrorNote error={ruleState.error || repairState.error}/> : reference && (!contract || !repairRule) ? <Notice tone="caution">原问题不在当前有效规则中，请从权限规则重新选择修改范围。</Notice> : <ChangeRegistration key={projectId + ':' + (reference ?? 'all')} draftScope={reference ?? undefined} embedded projectId={projectId} options={changeTargetOptions(ruleState.data?.rules ?? [], reference ?? undefined)} initialTargets={contract ? [{permission:repairRule!.permission, repair:repairReference(contract)}] : []} onClose={() => finishRegistration()} onBusyChange={setRegistrationBusy} onError={onError} onSaved={id => {setRegister(false); refresh(); finishRegistration(id);}}/>}
  </TaskSurface>;
  if (selected) return record.loading ? <TaskSurface title="读取源码修改" onBack={() => go(listPath)} backLabel="全部修改记录"><Loading>正在读取这次登记</Loading></TaskSurface> : !record.data ? <TaskSurface title="源码修改记录" onBack={() => go(listPath)} backLabel="全部修改记录"><ErrorNote error={record.error ?? new Error('没有找到这条修改记录。')}/></TaskSurface> : <ChangeReading item={record.data} readError={record.error} details={detail.data} loading={detail.loading} error={detail.error} projectId={projectId} official={official} workspace={workspace} path={changePath(selected)} onBack={() => go(listPath)} onError={onError} onChanged={() => {record.reload(); detail.reload(); refresh();}}/>;
  if (state.loading) return <PageSkeleton view="/changes"/>;
  if (state.error && !state.data) return <PageError title="源码修改" error={state.error}/>;
  return <ChangeDirectory key={projectId+':'+(before??'latest')} projectId={projectId} items={state.data ?? []} official={official} origin={origin} before={before} error={state.error} onOpen={id => go(changePath(id))} onRegister={() => setRegister(true)}/>;
}

function ChangeDirectory({projectId, items, official, origin, before, error, onOpen, onRegister}:{projectId:string;items:SourceChangeViewDto[];official:boolean;origin:string|null;before:string|null;error?:Error;onOpen:(id:string)=>void;onRegister:()=>void}) {
  const root = useRef<HTMLElement>(null);
  const directory = useDirectoryState('jiejian.directory.changes:' + projectId + ':' + (before??'latest'), {query:''}, true, root);
  const listHref=(cursor?:string)=>{const path='/changes'+(cursor?'?before_change_id='+encodeURIComponent(cursor):'');return '#'+scopedPath(origin?withReturnDestination(path,origin):path);};
  const query = directory.value.query.trim().toLocaleLowerCase();
  const visible = items.filter(item => [changeTitle(item.manifest.reason, official), submittedBy(item.manifest.submitted_by), ...item.change_set.added_paths, ...item.change_set.modified_paths, ...item.change_set.removed_paths].some(value => value.toLocaleLowerCase().includes(query)));
  return <TaskFrame as="section" className="jj-change-directory"><section ref={root}>
    {origin && <div className="jj-back-link"><ActionLink navigationScope="page" href={'#' + scopedPath(origin)} kind="quiet">{returnDestinationLabel(origin)}</ActionLink></div>}
    <Heading title="源码修改" actions={items.length > 0 && <Button data-directory-id="register" kind="primary" onClick={() => {directory.remember('register'); onRegister();}}>登记本地修改</Button>}>查阅每次登记的文件变化、关联检查，以及当前需要继续处理的事项。</Heading>
    {error && <ErrorNote error={error}/>}
    {!items.length ? before ? <Empty layout="section" title="没有更早的修改记录" action={<ActionLink href={listHref()}>返回最近记录</ActionLink>}>已读到这份修改历史的起点。</Empty> : <Empty layout="section" title="尚未登记源码修改" action={<Button data-directory-id="register" kind="primary" onClick={() => {directory.remember('register'); onRegister();}}>登记本地修改</Button>}>完成当前应用的代码修改后，在这里登记文件差异，再核对运行版本并复验。</Empty> : <>
      <div className="jj-change-directory-tools"><SearchField label="查找修改记录" placeholder="在本页按说明或文件路径查找" value={directory.value.query} onValueChange={query => directory.update({query})}/><p className="jj-small jj-muted">{visible.length} / {items.length} 条本页记录{!before && ' · 从最近登记开始'}</p></div>
      {visible.length ? <ObjectTable aria-label="修改记录" selection="" className="jj-change-history-table"><thead><tr><th scope="col">登记内容</th><th scope="col">文件变化</th><th scope="col">当前核对</th></tr></thead><tbody>{visible.map(item => <tr key={item.manifest.change_id}>
        <th scope="row"><button type="button" data-directory-id={item.manifest.change_id} className="jj-object-select" onClick={() => {directory.remember(item.manifest.change_id); onOpen(item.manifest.change_id);}}><strong>{changeTitle(item.manifest.reason, official)}</strong><small><time>{date(item.manifest.created_at_us)}</time> · {submittedBy(item.manifest.submitted_by)}</small></button></th>
        <td data-label="文件变化">{item.change_set.status === 'NO_BASELINE' ? '尚无比较起点' : fileCount(item) + ' 个文件'}{item.manifest.repair_reference && <small className="jj-table-secondary">关联原问题</small>}</td>
        <td data-label="当前核对"><Badge tone={item.revalidation.can_execute ? 'neutral' : 'caution'}>{readiness[item.revalidation.status]}</Badge></td>
      </tr>)}</tbody></ObjectTable> : <Empty layout="section" title="没有匹配的修改记录" action={<Button onClick={() => directory.update({query:''})}>清除查找</Button>}>调整修改说明或文件路径的查找条件。</Empty>}
      {(before || items.length === 50) && <TaskActions separated note="每次读取最多50条；查找只筛选当前页。">{before && <ActionLink href={listHref()}>返回最近记录</ActionLink>}{items.length === 50 && <ActionLink href={listHref(items[items.length-1].manifest.change_id)}>读取更早记录</ActionLink>}</TaskActions>}
    </>}
    <CurrentDiscoveryCoverage projectId={projectId}/>
  </section></TaskFrame>;
}

function ChangeReading({item, readError, details, loading, error, projectId, official, workspace, path, onBack, onError, onChanged}:{item:SourceChangeViewDto;readError?:Error;details?:DeliveryDetails|null;loading:boolean;error?:Error;projectId:string;official:boolean;workspace?:WorkspaceViewDto|null;path:string;onBack:()=>void;onError:(error:unknown)=>void;onChanged:()=>void}) {
  const [runtimeReady,setRuntimeReady]=useState<boolean>()
  const id = item.manifest.change_id, verification = details?.verification;
  const href = (destination:string) => '#' + scopedPath(withReturnDestination(destination, path),projectId);
  const linked = verification?.run_id, status = item.revalidation.status;
  const changed = item.continuation?.requirements.filter(requirement => requirement.status !== 'CURRENT') ?? [];
  const gaps = item.revalidation.preparation_gaps;
  const waitingRuntime=status==='READY'&&!item.revalidation.can_execute&&!loading&&!error&&Boolean(details)&&runtimeReady!==true;
  // 这里只安排现有核对事实的阅读顺序；预览和提交仍由原检查用例现场重核。
  const next = status === 'SOURCE_STALE' ? {title:'当前源码已有变化，先登记这次修改',description:'当前文件已与这次登记不同。先登记现在的代码，再为新的修改安排检查。',destination:'/changes?view=register',label:'登记当前源码修改'}
    : status === 'POLICY_STALE' ? {title:'当前规则已有变化，先核对变更要求',description:'这次登记保留当时采用的标准。先明确现在的要求和验证方式，再安排后续检查。',destination:'/permissions'+(changed[0]?'?rule_id='+encodeURIComponent(changed[0].permission.intent_id):''),label:'核对变更要求'}
    : status === 'MAPPING_REVIEW_REQUIRED' ? {title:'先核对业务与源码的对应',description:'当前业务操作与实现的对应需要复核，核对后再继续准备检查。',destination:'/application?view=business',label:'核对业务实现'}
    : status === 'NO_BASELINE' ? {title:'先确认源码比较起点',description:'这次登记缺少可比较的源码起点。先核对关联源码及运行配置，再查看可用的检查条件。',destination:'/application?view=source',label:'核对源码与运行'}
    : waitingRuntime ? {title:'先核对这批代码的运行版本',description:'原登记和关联报告继续保留。确认当前运行使用这次修改，再核对账号和材料。',destination:'/preparation?change_id='+encodeURIComponent(id),label:'查看所需材料'}
    : gaps.length ? {title:'先补齐本次检查的准备条件',description:'当前源码和规则已核对。继续处理所需账号、材料和连接条件，再确认执行范围。',destination:'/preparation?change_id='+encodeURIComponent(id),label:'核对准备材料'}
    : item.revalidation.can_execute ? {title:'可以预览这次修改的检查',description:'当前核对具备检查条件。预览实际范围并明确确认后，才会开始执行。',destination:'/reports?view=plan&change_id='+encodeURIComponent(id),label:item.manifest.repair_reference?'预览原问题复验':'预览修改后检查'}
    : {title:'继续核对运行与检查条件',description:'当前尚未具备执行条件。核对这批代码的运行状态，并在检查预览中查看具体前置事项。',destination:'/reports?view=plan&change_id='+encodeURIComponent(id),label:'查看检查前置条件'};
  const runtime = !loading && !error && details && <RuntimeActivation projectId={projectId} details={details} onError={onError} onChanged={onChanged} onReady={setRuntimeReady}/>;
  return <TaskSurface title={changeTitle(item.manifest.reason, official)} context="源码修改记录" description={<span><time>{date(item.manifest.created_at_us)}</time> · {submittedBy(item.manifest.submitted_by)}{item.manifest.repair_reference && ' · 关联原问题'}</span>} onBack={onBack} backLabel="全部修改记录">
    <div className="jj-change-reading">
      <section className="jj-change-current" aria-label="当前核对与后续检查">
        <SectionHeading title={readError ? '暂时无法核对当前条件' : next.title}/>
        <p>{readError ? '原登记和关联报告仍可阅读。恢复读取后，再准确安排本次后续检查。' : next.description}</p>
        {readError ? <Notice tone="caution" title="当前状态待重核">当前核对更新失败，已读取的原登记和关联报告继续保留。</Notice> : <>
          {status === 'POLICY_STALE' && changed.length > 0 && <ul className="jj-change-requirements">{changed.map(requirement => <li key={requirement.permission.intent_id}><span>{requirement.action_label} · {requirement.status === 'CHANGED' ? '要求已有新修订' : '已移出当前标准'}</span><ActionLink navigationScope="page" href={href('/permissions?rule_id='+encodeURIComponent(requirement.permission.intent_id))}>核对这项要求</ActionLink></li>)}</ul>}
          {status === 'READY' && !item.revalidation.can_execute && runtime}
        </>}
        {(!waitingRuntime||readError)&&<TaskActions note={readError ? '重新读取只更新当前核对。' : '原登记与历史报告继续对应当时的源码、规则和实际样本。'}>
          {readError ? <Button kind="primary" onClick={onChanged}>重新读取当前核对</Button> : <ActionLink navigationScope="page" kind={waitingRuntime?'quiet':'primary'} href={href(next.destination)}>{next.label}</ActionLink>}
        </TaskActions>}
      </section>
      <section className="jj-change-result"><SectionHeading title="已保留的关联检查" meta={!loading && !error && linked ? <Badge tone={verification!.verdict === 'PASS' ? 'positive' : verification!.verdict === 'BLOCK' ? 'negative' : 'caution'}>{verification!.repair_status === 'VERIFIED' ? '原问题修复已验证' : verification!.verdict === 'PASS' ? '符合当时的规则' : verification!.verdict === 'BLOCK' ? '当时存在不符合规则的结果' : verification!.verdict === 'INCONCLUSIVE' ? '部分检查证据不足' : '尚未形成结论'}</Badge> : undefined}/>
        {loading ? <Loading>正在读取关联检查</Loading> : error ? <><ErrorNote error={error}/><TaskActions><Button onClick={onChanged}>重新读取关联检查</Button></TaskActions></> : linked ? <><p>原报告对应这次登记及检查时采用的规则、源码和实际范围。</p><TaskActions><ActionLink navigationScope="page" href={href('/reports?run_id='+encodeURIComponent(linked))} kind="quiet">阅读本批报告</ActionLink></TaskActions></> : verification?.same_source_run_id ? <><p>同版源码有检查记录，尚未关联本批。</p><TaskActions><ActionLink navigationScope="page" href={href('/reports?run_id='+encodeURIComponent(verification.same_source_run_id))} kind="quiet">查看同版源码报告</ActionLink></TaskActions></> : <p className="jj-muted">这次修改还没有关联的检查记录。</p>}
      </section>
      <div className="jj-change-evidence"><h2 className="jj-title-group">详细依据</h2><details className="jj-change-recorded"><summary>登记时的文件变化 · {item.change_set.status === 'COMPARABLE' ? fileCount(item) + ' 个文件' : '缺少比较起点'}</summary><div>
        {item.change_set.status === 'NO_BASELINE' ? <p className="jj-muted">这次登记没有可比较的源码起点，不能据此列出完整文件变化。</p> : fileCount(item) ? <div className="jj-change-files">{([['added_paths','新增'],['modified_paths','修改'],['removed_paths','删除']] as const).map(([key,label]) => item.change_set[key].length > 0 && <details key={key}><summary>{label} {item.change_set[key].length} 个文件</summary>{item.change_set[key].map(file => <p className="jj-path" key={file}>{file}</p>)}</details>)}</div> : <p className="jj-muted">这次登记未发现文件内容变化。</p>}
        {item.assessment.payload.action_impacts.length > 0 && <details className="jj-change-impacts"><summary>登记时识别的业务影响</summary>{item.assessment.payload.action_impacts.map(impact => <div key={impact.action_id}><strong>{text(workspace?.actions.find(action => action.action_id === impact.action_id && action.action_revision === impact.action_revision)?.display_name ?? '业务操作 · 修订 ' + impact.action_revision)}</strong><span>{impact.classification === 'DIRECTLY_AFFECTED' ? '有直接变化证据' : impact.classification === 'MAPPING_REVIEW_REQUIRED' ? '需核对实现对应' : '未发现直接影响证据'}</span></div>)}</details>}
      </div></details>
      {!readError && <>{!(status === 'READY' && !item.revalidation.can_execute) && runtime && <details className="jj-change-support"><summary>这批代码的运行状态</summary>{runtime}</details>}<ChangeContinuation value={item} origin={path}/></>}</div>
    </div>
  </TaskSurface>;
}

function changeTitle(reason:string, official:boolean) {
  const match = official ? reason.match(/^预设演示[：:]\s*(BASELINE|VULNERABLE|EXPOSE_REVOKE|FIXED|PREVIEW_CHANGED)$/) : null;
  const labels:Record<string,string> = {BASELINE:'正常访问限制', VULNERABLE:'移除内部包下载限制', EXPOSE_REVOKE:'处理中开放后再撤回', FIXED:'恢复内部包访问限制', PREVIEW_CHANGED:'调整公开预览内容'};
  return text(match ? labels[match[1]] : reason);
}
