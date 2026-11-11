import {TaskActions} from '../../shared/ui/layout'
import './understanding.css'
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useEffect, useRef, useState } from 'react';
import PlusOutlined from '@ant-design/icons/PlusOutlined';
import {Segmented} from '../../shared/ui/Segmented';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import { projectsApi, type CandidateSelection, type RoleCandidateDto } from '../../entities/application/api/projects';
import { Choice } from "../../shared/ui/Choice";
import {Button,ActionLink} from '../../shared/ui/actions'
import {Badge, ErrorNote, InlineFeedback, Loading, PageError} from "../../shared/ui/feedback";
import { Heading, Field } from "../../shared/ui/layout";
import { assertProject } from '../../shared/model/page';
import {go,scopedPath} from '../../shared/lib/navigation'
import { readPending, savePending } from '../../shared/lib/operations';
import { useRead } from '../../shared/lib/useRead';
export function Understanding({ projectId, embedded = false }: {
    projectId: string;
    embedded?: boolean;
}) {
    const state = useRead('business-understanding:' + projectId, async () => { const value = await projectsApi.understanding(projectId); assertProject(value.project_id, projectId); return value; });
    const draftKey = 'jiejian.studio.business-draft:' + projectId;
    const [draft, setDraft] = useState(() => readPending<{revision: number; choices: Record<string, CandidateSelection>}>(draftKey)), [busy, setBusy] = useState(false);
    const [manual,setManual]=useState({ROLE:'',ACTION:''});
    const [error,setError]=useState<unknown>();
    const [creating,setCreating]=useState<'ROLE'|'ACTION'>(),[saved,setSaved]=useState(false);
    // 分类只控制可见内容；各对象的修改仍保留在同一修订草稿中。
    const [chosenKind,setKind]=useState(()=>readPending<'ROLE'|'ACTION'>(draftKey+':view',(value):value is 'ROLE'|'ACTION'=>value==='ROLE'||value==='ACTION'));
    const nameInput=useRef<HTMLInputElement>(null);
    useEffect(()=>{if(creating)nameInput.current?.focus()},[creating]);
    const act=async(task:()=>Promise<void>)=>{setBusy(true);setError(undefined);try{await task()}catch(value){setError(value)}finally{setBusy(false)}};
    const choices = state.data?.revision === draft?.revision ? draft?.choices ?? {} : {};
    const setChoices = (update: Record<string, CandidateSelection> | ((value: Record<string, CandidateSelection>) => Record<string, CandidateSelection>)) => { if (state.data) setDraft({revision: state.data.revision, choices: typeof update === 'function' ? update(choices) : update}); };
    useEffect(() => { savePending(draftKey, draft); }, [draftKey, draft]);
    useEffect(() => { savePending(draftKey+':view', chosenKind); }, [draftKey, chosenKind]);
    if (state.loading)
        return embedded?<Loading/>:<PageSkeleton view="/application" title="业务角色与操作"/>;
    if (state.error || !state.data)
        return embedded?<ErrorNote error={state.error}/>:<PageError title="业务角色与操作" error={state.error}/>;
    const value = state.data;
    const groups = [{kind:'ROLE',label:'业务角色',items:value.role_candidates},{kind:'ACTION',label:'业务操作',items:value.action_candidates}] as const;
    const activeKind=chosenKind??(value.role_candidates.length?'ROLE':'ACTION');
    const group=groups.find(item=>item.kind===activeKind)!;
    const kind = creating??activeKind;
    const label = kind==='ROLE'?'业务角色':'业务操作';
    const selectionFor=(candidateKind:'ROLE'|'ACTION',item:RoleCandidateDto):CandidateSelection=>choices[item.candidate_id]??{
        kind:candidateKind,candidate_id:item.candidate_id,display_name:item.display_name,
        decision:item.decision==='CONFIRMED'?'CONFIRMED':item.decision==='REJECTED'?'REJECTED':'PROPOSED'
    };
    const changedCount=Object.keys(choices).length;
    const add=()=>void act(async()=>{
        const name=manual[kind].trim();
        if(kind==='ROLE')await projectsApi.addRole(projectId,name,value.revision);else await projectsApi.addAction(projectId,name,'UNKNOWN',value.revision);
        setCreating(undefined);setManual({...manual,[kind]:''});state.reload();
    });
    return <>
    {!embedded&&<><div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath('/application')} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}应用与来源</ActionLink></div>
    <Heading title="业务角色与操作"/></>}
    <section className="jj-understanding-workspace" data-kind={activeKind}>
      <header className="jj-business-heading"><h2>业务名称</h2><p className="jj-business-introduction">确认源码标识对应的业务名称，例如 owner 对应“项目负责人”。访问要求在“权限与覆盖”中设置。</p></header>
      {Boolean(error)&&<ErrorNote error={error}/>}
      {saved&&!changedCount&&<InlineFeedback tone="positive">业务确认已保存，可以继续维护访问规则。</InlineFeedback>}
      <header className="jj-business-toolbar">
        <Segmented label="线索类别" value={activeKind} items={groups.map(item=>({value:item.kind,label:<>{item.label}<span>{item.items.length}</span></>}))} disabled={busy} onValueChange={next=>{setKind(next);setCreating(undefined)}}/>
        {!creating&&<Button kind="quiet" icon={<PlusOutlined aria-hidden="true"/>} disabled={busy||Boolean(changedCount)} onClick={()=>setCreating(group.kind)}>添加{group.kind==='ROLE'?'角色':'操作'}</Button>}
      </header>
      {creating?<section className="jj-business-add" aria-label={'补充'+label}><h2>补充{label}</h2><Field label={label+'名称'}><input ref={nameInput} disabled={busy} value={manual[kind]} onChange={event=>setManual({...manual,[kind]:event.target.value})}/></Field><footer><Button disabled={busy} onClick={()=>setCreating(undefined)}>取消添加</Button><Button kind="primary" busy={busy} disabled={!manual[kind].trim()} onClick={add}>添加{kind==='ROLE'?'角色':'操作'}</Button></footer></section>:
      group.items.length?<div className="jj-scroll-table jj-business-table-wrap"><table className="jj-content-table jj-business-table" aria-label={group.label+'确认'}><thead><tr><th scope="col">{group.label}名称</th><th scope="col" className="jj-table-state">用于权限检查</th><th scope="col">来源依据</th></tr></thead><tbody>{group.items.map(item=>{
        const selection=selectionFor(group.kind,item);
        return <tr key={item.candidate_id}><td><label className="jj-sr-only" htmlFor={'business-name-'+item.candidate_id}>{group.label}名称：{item.display_name}</label><input id={'business-name-'+item.candidate_id} disabled={busy} value={selection.display_name} onChange={event=>{setSaved(false);setChoices(current=>({...current,[item.candidate_id]:{...selection,display_name:event.target.value}}))}}/>{choices[item.candidate_id]&&<small className="jj-business-unsaved">尚未保存</small>}</td>
        <td className="jj-table-state"><Choice align="center" className="jj-table-choice" aria-label={item.display_name+'的处理方式'} disabled={busy} value={selection.decision} onValueChange={decision=>{setSaved(false);setChoices(current=>({...current,[item.candidate_id]:{...selection,decision:decision as CandidateSelection['decision']}}))}}><option value="PROPOSED">暂不决定</option><option value="CONFIRMED">与检查有关</option><option value="REJECTED">不属于当前业务</option></Choice></td>
        <td><div className="jj-business-source">{item.stale&&<Badge tone="caution">来源需要更新</Badge>}{item.origin==='MANUAL'?<span>人工提供</span>:item.evidence.length?<><code>{item.evidence[0].relative_path}</code><span>{item.evidence[0].detector==='API_SOURCE'?item.evidence[0].symbol:'第 '+item.evidence[0].line_start+' 行'}</span>{item.evidence.length>1&&<details><summary>其他 {item.evidence.length-1} 处依据</summary>{item.evidence.slice(1).map((evidence,index)=><p key={index}><code>{evidence.relative_path}</code> · {evidence.detector==='API_SOURCE'?evidence.symbol:'第 '+evidence.line_start+' 行'}</p>)}</details>}</>:<span>尚无可读取的来源位置</span>}</div></td></tr>
      })}</tbody></table></div>:<p className="jj-understanding-empty">尚无线索，可以从已有资料发现或手动添加。</p>}
      {!creating&&<TaskActions separated note={<>{changedCount>0&&<p>已修改 {changedCount} 项，保存后更新业务名称和检查用途。</p>}</>}> <Button kind="quiet" disabled={busy} onClick={()=>go('/permissions')}>维护访问规则</Button><Button kind="primary" busy={busy} disabled={!changedCount||Object.values(choices).some(item=>!item.display_name.trim())} onClick={()=>void act(async()=>{await projectsApi.decideCandidates(projectId,value.revision,Object.values(choices));setChoices({});setSaved(true);state.reload()})}>保存业务确认</Button></TaskActions>}
    </section>
  </>;
}
