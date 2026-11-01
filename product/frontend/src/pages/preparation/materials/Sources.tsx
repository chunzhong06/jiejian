import {PageSkeleton} from '../../../shared/ui/PageSkeleton'
import {SourceConfiguration} from './SourceConfiguration'
import { useEffect, useRef, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import CheckOutlined from '@ant-design/icons/CheckOutlined';
import FileDoneOutlined from '@ant-design/icons/FileDoneOutlined';
import { ApiError } from '../../../shared/api/http';
import { proofSourcesApi as api, type AdoptionPreview, type ProofOperationKind, type ProofSource } from '../../../entities/preparation/api/proofSources';
import { assertProject } from '../../../shared/model/page';
import { text } from '../../../shared/lib/format';
import { useRead } from '../../../shared/lib/useRead';
import { Badge, Empty, ErrorNote, Notice } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import { Heading } from "../../../shared/ui/layout";
import { Dialog } from "../../../shared/ui/Dialog";
function sourceState(source: ProofSource): {
    label: string;
    tone: 'positive' | 'caution' | 'neutral' | 'accent';
} {
    const current = source.usable || source.preflight?.state === 'SUCCEEDED' && source.preflight.current_basis && source.preflight.report?.assessment === 'USABLE';
    if (source.adopted && current && source.read_scope_confirmed)
        return { label: '已用于检查', tone: 'positive' };
    if (['PENDING', 'RUNNING', 'RETRY_WAIT'].includes(source.preflight?.state ?? ''))
        return { label: '正在核对', tone: 'accent' };
    if (current && source.read_scope_confirmed)
        return { label: '可用于检查', tone: 'accent' };
    if (source.adopted || source.preflight)
        return { label: '需要重新核对', tone: 'caution' };
    return { label: '待准备', tone: 'neutral' };
}
const methodLabels = { SQLITE_OBJECTS: '确认操作是否真正创建了新数据，以及新数据属于谁。', SQLITE_AUDIT: '比较这份测试数据在操作前后的字段变化，只使用已提交的业务记录。', REFERENCE_FILE: '将本次实际收到的完整文件与已确认的参照比对。', MANAGED_TRANSACTION_RECORDS: '读取独立业务记录，核对本次操作是否产生对应结果。', CREATED_OBJECT_RECORDS: '通过独立记录确认本次创建的业务对象。', JSON_HTTP_RESOURCE: '读取本次资源的业务状态或指定字段，核对实际结果。' };
const checkLabels: Record<string, string> = { MAPPING_READABLE: '记录字段可以读取', IDENTITY_CONFIRMED: '测试身份可以对应', ACTUAL_IDENTITY_MATCH: '实际账号与测试账号一致', RESOURCE_CORRELATED: '记录可以对应测试资源', CLOSURE_SUPPORTED: '能够确认完整观察范围', PROTECTED_FIELD_READABLE: '所需业务字段可以读取', RESOURCE_OWNER_MATCH: '资源与所有者一致', SOURCE_CONTRACT_VERIFIED: '来源符合采集要求', REFERENCE_ARTIFACT_VERIFIED: '完整参照文件已核对', PROTECTED_FIELD_MISSING: '缺少所需业务字段', RESOURCE_OWNER_MISMATCH: '资源或所有者不对应', CONTRACT_UNVERIFIED: '记录来源尚未核对' };
const mappingLabels: Record<string, string> = { owner_id: '资源所有者', resource_id: '资源编号', subject_id: '操作账号', state: '业务状态' };
export function Sources({ projectId, actionId, requestedSource, onLocate, onBack, onError }: {
    projectId: string;
    actionId?: string;
    requestedSource?: string | null;
    onLocate?: (id: string) => void;
    onBack: () => void;
    onError: (error: unknown) => void;
}) {
    const state = useRead('sources:' + projectId, async (signal) => { const value = await api.context(projectId, 'full', signal); assertProject(value.project_id, projectId); return value; }, value => value?.sources.some(item => ['PENDING', 'RUNNING', 'RETRY_WAIT'].includes(item.preflight?.state ?? '')) ? 1500 : 0);
    const key = 'jiejian.studio.proof:' + projectId;
    const [configuring,setConfiguring]=useState<'new'|'edit'|null>(null);
    const [file, setFile] = useState<File>(), [selected, setSelected] = useState(requestedSource ?? ''), [review, setReview] = useState<'scope' | 'adoption'>(), [adoption, setAdoption] = useState<AdoptionPreview>(), [ack, setAck] = useState(false), [busy, setBusy] = useState(false), [notice, setNotice] = useState(''), [pending, setPending] = useState<{
        kind: ProofOperationKind;
        operation: string;
    } | undefined>(() => { try {
        return JSON.parse(sessionStorage.getItem(key) ?? 'null') ?? undefined;
    }
    catch {
        return undefined;
    } });
    const lock = useRef(false), context = state.data;
    const [revoke, setRevoke] = useState(false);
    useEffect(() => { if (requestedSource)
        setSelected(requestedSource); }, [requestedSource]);
    const sources = context?.sources.filter(item => Boolean(requestedSource) || !actionId || item.config.action_id === actionId) ?? [];
    const source = sources.find(item => item.source_id === selected) ?? (!requestedSource ? sources[0] : undefined);
    const action = context?.actions.find(item => item.action_id === source?.config.action_id), effect = action?.effects.find(item => item.effect_id === source?.config.effect_id);
    const resource = context?.resources.find(item => item.resource_binding_id === source?.config.resource_binding_id);
    const usable = source?.usable || source?.preflight?.state === 'SUCCEEDED' && source.preflight.current_basis && source.preflight.report?.assessment === 'USABLE';
    const checking = ['PENDING', 'RUNNING', 'RETRY_WAIT'].includes(source?.preflight?.state ?? '');
    const scope = source?.read_scope_confirmed === true;
    useEffect(() => { setFile(undefined); setReview(undefined); setAdoption(undefined); }, [source?.source_id]);
    useEffect(() => setAck(false), [source?.source_id, source?.revision, context?.basis_id]);
    const write = async (kind: ProofOperationKind, body: object, content?: ArrayBuffer) => {
        if (lock.current || pending)
            return;
        const next = { kind, operation: crypto.randomUUID().replaceAll('-', '') };
        lock.current = true;
        setBusy(true);
        sessionStorage.setItem(key, JSON.stringify(next));
        setPending(next);
        try {
            const receipt = await api.write(projectId, kind, { ...body, operation_id: next.operation }, content);
            assertProject(receipt.project_id, projectId);
            if (receipt.operation_id !== next.operation || receipt.operation_kind !== kind)
                throw new Error('材料操作回执不匹配。');
            sessionStorage.removeItem(key);
            setPending(undefined);
            setReview(undefined);
            setNotice(kind === 'ADOPT_SOURCE' ? '此来源已用于后续检查。' : '操作已保存。');
            state.reload();
            return true;
        }
        catch (error) {
            if (error instanceof ApiError && ['INPUT_INVALID', 'STATE_PRECONDITION', 'STORAGE_SECRET', 'API_VALIDATION_ERROR', 'RECORD_NOT_FOUND'].includes(error.code)) {
                sessionStorage.removeItem(key);
                setPending(undefined);
            }
            onError(error);
        }
        finally {
            lock.current = false;
            setBusy(false);
        }
    };
    const recover = async () => { if (!pending || lock.current)
        return; lock.current = true; setBusy(true); try {
        const result = await api.receipt(projectId, pending.kind, pending.operation);
        assertProject(result.project_id, projectId);
        if (result.operation_id !== pending.operation || result.operation_kind !== pending.kind)
            throw new Error('材料操作回执不匹配。');
        sessionStorage.removeItem(key);
        setPending(undefined);
        setReview(undefined);
        state.reload();
    }
    catch (error) {
        onError(error);
    }
    finally {
        lock.current = false;
        setBusy(false);
    } };
    const openAdoption = async () => { if (!source?.preflight || lock.current || pending)
        return; lock.current = true; setBusy(true); try {
        const value = await api.adoptionPreview(projectId, source.source_id, source.preflight.preflight_id);
        assertProject(value.project_id, projectId);
        if (value.source_id !== source.source_id || value.revision !== source.revision)
            throw new Error('材料版本已变化，请重新读取。');
        setAdoption(value);
        setAck(false);
        setReview('adoption');
    }
    catch (error) {
        onError(error);
    }
    finally {
        lock.current = false;
        setBusy(false);
    } };
    if (state.loading)
        return <PageSkeleton view="/preparation" title="证明来源"/>;
    if (!context)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    if (requestedSource && !source)
        return <Empty title="没有找到指定的证明来源" action={<Button onClick={onBack}>返回检查准备</Button>}/>;
    const common = source ? { source_id: source.source_id, revision: source.revision, basis_id: context.basis_id } : undefined;
    const title = effect?.label ?? '业务结果证明';
    const staleAdoption = Boolean(review === 'adoption' && adoption && (adoption.basis_id !== context.basis_id || adoption.source_id !== source?.source_id || adoption.revision !== source?.revision || adoption.preflight_id !== source?.preflight?.preflight_id));
    if (review && source)
        return <>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} disabled={busy} onClick={() => setReview(undefined)}>证明来源</Button></div>
    <Heading eyebrow={review === 'scope' ? '读取范围' : '用于检查'} title={review === 'scope' ? '核对允许读取的内容' : '确认这份证明的用途'}/>
    <section className="jj-source-review">
      <header><h2>{text(title)}</h2><Badge tone={review === 'scope' && scope ? 'positive' : 'neutral'}>{review === 'scope' && scope ? '已授权' : '等待确认'}</Badge></header>
      <div className="jj-source-review-body"><p className="jj-proof-method">{methodLabels[source.config.source_kind]}</p><dl className="jj-facts">
        <div><dt>应用地址</dt><dd>{context.runtime_origin ?? '当前运行地址尚未确认'}</dd></div>
        <div><dt>读取账号</dt><dd>{source.config.identity_claims.map(claim => context.identities.find(item => item.identity_id === claim.identity_id)?.label ?? '未找到对应账号').map(text).join('、')}</dd></div>
        <div><dt>测试资源</dt><dd>{[resource?.resource_id, ...context.resources.filter(item=>item.action_id===source.config.action_id&&item.case_specific).map(item=>item.resource_id)].filter(Boolean).join('、') || '测试数据已有变化'}</dd></div>
        {['SQLITE_AUDIT','SQLITE_OBJECTS'].includes(source.config.source_kind)?<><div><dt>测试数据库</dt><dd>{source.config.database_path}</dd></div><div><dt>数据表与读取字段</dt><dd>{source.config.table} / {[source.config.resource_column,source.config.owner_column,...(source.config.observed_columns??[source.config.protected_column])].join('、')}</dd></div></>:<div><dt>结果记录位置</dt><dd>{source.config.relative_path_template}</dd></div>}
        {[...new Set(source.config.identity_claims.map(item => item.request_path).filter(Boolean))].map(path => <div key={path}><dt>身份核对位置</dt><dd>{path}</dd></div>)}
        {source.config.collection && <div><dt>记录集合</dt><dd>{source.config.collection}</dd></div>}
        <div><dt>单次读取限制</dt><dd>{Math.ceil(source.config.max_response_bytes / 1024)} KiB，{source.config.timeout_us / 1000000} 秒</dd></div>
      </dl>
      {adoption && review === 'adoption' && <section className="jj-adoption-impact"><h3>用于检查后的变化</h3><p>{adoption.replaces_existing ? '替换当前对应的证明材料。' : '建立这项业务结果的证明材料。'}</p>{adoption.recheck.length > 0 && <ul>{adoption.recheck.map((item, index) => <li key={index}>{text(item)}</li>)}</ul>}</section>}
      {staleAdoption && review === 'adoption' && <Notice>账号、数据或读取记录已有变化，请返回重新核对。</Notice>}</div>
      <footer className="jj-source-consent">{review === 'scope' && scope ? <p className="jj-small jj-muted">后续读取仍限于上述账号、资源和记录。</p> : <label className="jj-checkbox"><input type="checkbox" checked={ack && !staleAdoption} disabled={busy || Boolean(pending) || staleAdoption} onChange={event => setAck(event.target.checked)}/><span>{review === 'scope' ? '允许读取上述账号、资源与记录' : '我已核对数据归属和使用后的变化'}</span></label>}
        <div className="jj-inline-actions"><Button disabled={busy} onClick={() => setReview(undefined)}>返回来源</Button>{!(review === 'scope' && scope) && <Button kind="primary" busy={busy} disabled={!ack || Boolean(pending) || !resource || !context.runtime_available || staleAdoption} onClick={() => void (review === 'scope' ? write('GRANT_SCOPE', { ...common, confirmed: true }) : adoption && write('ADOPT_SOURCE', { source_id: adoption.source_id, revision: adoption.revision, basis_id: adoption.basis_id, preflight_id: adoption.preflight_id, confirmed: true }))}>{review === 'scope' ? '允许读取' : '确认用于检查'}</Button>}</div>
      </footer>
    </section>
  </>;
    return <>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>检查准备</Button></div>
    <Heading title="准备业务结果证明" actions={<Button kind="quiet" onClick={state.reload}>刷新状态</Button>}/>

    {state.error && <ErrorNote error={state.error}/>}
    {notice && !(source?.adopted&&usable&&scope) && <Notice tone="positive">{notice}</Notice>}
    {pending && <Notice>上次操作的结果尚未确认。<Button busy={busy} onClick={() => void recover()}>查询这次操作</Button></Notice>}
    {configuring&&<SourceConfiguration projectId={projectId} context={context} actionId={actionId} initial={configuring==='edit'?source?.config:undefined} onClose={()=>setConfiguring(null)} onSave={config=>write('SAVE_SOURCE',{basis_id:context.basis_id,config,...(configuring==='edit'&&source?{source_id:source.source_id,expected_revision:source.revision}:{})})}/>}
    {!sources.length ? <Empty title="如何确认操作真的产生了结果" action={<Button kind="primary" onClick={()=>setConfiguring('new')}>选择判断方式</Button>}>例如修改工单后，读取对应记录中的业务字段，确认数据是否改变。</Empty> : <section className={'jj-proof-workspace' + (sources.length === 1 ? ' is-single-source' : '')}>
      {sources.length > 1 && <nav className="jj-source-index" aria-label="证明来源"><h2>业务结果</h2>{sources.map(item => { const label = context.actions.find(action => action.action_id === item.config.action_id)?.effects.find(effect => effect.effect_id === item.config.effect_id)?.label ?? '业务结果', status = sourceState(item); return <button aria-current={source?.source_id === item.source_id ? 'page' : undefined} disabled={busy || Boolean(pending)} key={item.source_id} onClick={() => { setSelected(item.source_id); onLocate?.(item.source_id); }}><span>{text(label)}</span><small data-tone={status.tone}>{status.label}</small></button>; })}</nav>}
      {source && <div className="jj-proof-detail" key={source.source_id}>
        <header><div><p className="jj-eyebrow">{text(action?.label ?? '当前业务操作')}</p><div className="jj-item-heading"><h2>{text(title)}</h2><Badge tone={sourceState(source).tone}>{sourceState(source).label}</Badge></div></div></header>
        <ol className="jj-proof-stages">
          <li data-complete={scope}><span>{scope ? <CheckOutlined aria-hidden="true"/> : '1'}</span><div><strong>允许读取</strong><small>{scope ? '已确认范围' : '待确认范围'}</small></div></li>
          <li data-complete={usable}><span>{usable ? <CheckOutlined aria-hidden="true"/> : '2'}</span><div><strong>检查是否可用</strong><small>{usable ? '可以使用' : checking ? '正在核对' : '待核对'}</small></div></li>
          <li data-complete={source.adopted && usable && scope}><span>{source.adopted && usable && scope ? <CheckOutlined aria-hidden="true"/> : '3'}</span><div><strong>用于正式检查</strong><small>{source.adopted && usable && scope ? '已用于检查' : '等待确认使用'}</small></div></li>
        </ol>
        {(!source.adopted||!usable||!scope)&&<div className="jj-proof-next" role="status"><h3>{!scope?'先确认允许读取哪些内容':checking?'正在检查能否正确读取':!usable?'检查账号和业务记录能否对应':!source.adopted?'核对通过，可以用于检查':'这项结果的判断方式已准备好'}</h3><p>{!scope?'下一步会列出账号、测试数据和读取字段，由你确认。':checking?'核对完成后，本页会更新结果；离开页面不会中断。':!usable?'只读取已授权的范围，确认记录属于当前账号和测试数据。':!source.adopted?'确认使用后，后续检查会依据这份业务记录判断结果。':'新检查会重新读取实际记录；已有报告保留。'}</p></div>}
        <div className="jj-proof-reading">
          <section className="jj-proof-input"><h3>用什么判断结果</h3><p className="jj-proof-method">{methodLabels[source.config.source_kind]}</p>
            <dl className="jj-facts"><div><dt>测试资源</dt><dd>{resource?.resource_id ?? '测试数据需要重新确认'}</dd></div><div><dt>资源所有者</dt><dd>{text(context.identities.find(item => item.identity_id === resource?.owner_identity_id)?.label ?? '尚未确认')}</dd></div><div><dt>读取记录</dt><dd>{source.config.table??source.config.collection??'应用业务记录'}{source.config.protected_column?' / '+source.config.protected_column:''}</dd></div></dl>
            {source.config.source_kind === 'REFERENCE_FILE' && !source.config.reference_artifact && <section className="jj-reference-upload"><h3>准备完整参照文件</h3><p>选择属于上述资源和所有者的正确测试文件，最大 4 MiB。</p><input type="file" aria-label="选择完整测试参照文件" disabled={busy || Boolean(pending)} onChange={event => setFile(event.target.files?.[0])}/>{file && <><p>{file.name}，{Math.ceil(file.size / 1024)} KiB</p><Button disabled={busy || Boolean(pending)} onClick={() => void (async () => { if (file.size === 0 || file.size > 4194304) {
                onError(new Error('请选择非空且不超过 4 MiB 的文件。'));
                return;
            } const content = await file.arrayBuffer(), hash = await crypto.subtle.digest('SHA-256', content), sha256 = [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join(''); await write('UPLOAD_REFERENCE', { basis_id: context.basis_id, action_id: source.config.action_id, action_revision: source.config.action_revision, resource_binding_id: source.config.resource_binding_id, confirmed: true, size: content.byteLength, sha256 }, content); })().catch(onError)}>确认资源归属并上传</Button></>}</section>}
            {source.config.source_kind === 'REFERENCE_FILE' && <section className="jj-reference-choices"><h3>可用的完整参照</h3>{context.reference_inputs?.filter(item => item.state === 'COMPLETE' && item.manifest && item.action_id === source.config.action_id && item.action_revision === source.config.action_revision && item.owner_identity_id === resource?.owner_identity_id && item.resource_id === resource?.resource_id).map((item, index) => <div className="jj-reference-choice" key={item.asset_id}><span><FileDoneOutlined aria-hidden="true"/>完整参照 {index + 1}<small>{Math.ceil(item.manifest!.size / 1024)} KiB</small></span>{source.config.reference_artifact?.asset_id === item.asset_id ? <Badge tone="positive">当前参照</Badge> : <Button disabled={busy || Boolean(pending)} onClick={() => void write('SAVE_SOURCE', { basis_id: context.basis_id, source_id: source.source_id, expected_revision: source.revision, config: { ...source.config, reference_artifact: item.manifest, reference_origin: item.origin, reference_resource_id: item.resource_id, reference_owner_identity_id: item.owner_identity_id } })}>用于这项结果</Button>}</div>)}</section>}
          </section>
          <section className="jj-source-verification"><h3>{source.preflight && !source.preflight.current_basis ? '上次来源核对' : '来源核对'}</h3>{source.preflight?.report ? <details open={source.preflight.current_basis&&!usable}><summary>{!source.preflight.current_basis?'查看上次核对结果':usable?'已能读取所需账号与业务记录':'查看尚未通过的核对项目'}</summary><div className="jj-source-checks">{source.preflight.report.checks.filter((item, index, all) => all.findIndex(other => other.code === item.code && other.status === item.status && other.mapping_key === item.mapping_key) === index).map((item, index) => <div key={index}><span>{item.code === 'MAPPING_READABLE' && item.mapping_key ? (mappingLabels[item.mapping_key] ?? '关联字段') + '可以读取' : checkLabels[item.code] ?? '其他来源核对'}{item.mapping_key && item.code !== 'MAPPING_READABLE' && <small>{mappingLabels[item.mapping_key] ?? '关联字段'}</small>}</span><span data-confirmed={item.status === 'CONFIRMED'}>{item.status === 'CONFIRMED' ? <><CheckOutlined aria-hidden="true"/><span className="jj-sr-only">已确认</span></> : item.status === 'UNSUPPORTED' ? '当前不支持' : '尚未确认'}</span></div>)}</div></details> : <p className="jj-small jj-muted">确认读取范围后，可以核对账号、资源与记录的对应关系。</p>}
            <details><summary>读取位置与技术引用</summary><p className="jj-path">{source.config.relative_path_template}</p><pre>{JSON.stringify(source.config.mappings, null, 2)}</pre></details>
          </section>
        </div>
        <footer className="jj-proof-actions"><details className="jj-proof-management"><summary>查看与调整设置</summary><div><Button kind="quiet" disabled={busy || Boolean(pending)} onClick={()=>{setAck(false);setReview('scope')}}>查看读取范围</Button>{['SQLITE_AUDIT','SQLITE_OBJECTS'].includes(source.config.source_kind)&&<Button kind="quiet" disabled={busy||Boolean(pending)} onClick={()=>setConfiguring('edit')}>调整判断方式</Button>}<Button kind="quiet" disabled={busy||Boolean(pending)} onClick={()=>setConfiguring('new')}>新增判断方式</Button>{scope&&<Button kind="quiet" disabled={busy||Boolean(pending)} onClick={()=>setRevoke(true)}>撤销读取授权</Button>}</div></details>
          {!scope?<Button kind="primary" disabled={busy||Boolean(pending)} onClick={()=>{setAck(false);setReview('scope')}}>核对并允许读取</Button>:checking&&source.preflight?<Button disabled={busy||Boolean(pending)} onClick={()=>void write('CANCEL_PREFLIGHT',{preflight_id:source.preflight!.preflight_id})}>取消本次核对</Button>:!usable?<Button kind="primary" busy={busy} disabled={Boolean(pending)||!resource||!context.runtime_available||source.config.source_kind==='REFERENCE_FILE'&&!source.config.reference_artifact} onClick={()=>void write('START_PREFLIGHT',common!)}>检查是否可用</Button>:!source.adopted?<Button kind="primary" busy={busy} disabled={Boolean(pending)} onClick={()=>void openAdoption()}>核对并用于检查</Button>:<Button kind="primary" onClick={onBack}>继续准备检查</Button>}
        </footer>
      </div>}
    </section>}
    {revoke && source?.matching_read_scope_id && <Dialog title="撤销这份读取授权" onClose={() => setRevoke(false)} actions={dismiss => <><Button onClick={dismiss}>保留授权</Button><Button kind="danger" busy={busy} onClick={() => void write('REVOKE_SCOPE', { scope_id: source.matching_read_scope_id }).then(() => setRevoke(false))}>撤销授权</Button></>}><p>使用同一授权的证明来源将无法继续读取，需要重新核对材料。已发布报告保留。</p></Dialog>}
  </>;
}
