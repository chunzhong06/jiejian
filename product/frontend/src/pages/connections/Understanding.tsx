import './understanding.css'
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useEffect, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import { projectsApi, type CandidateSelection } from '../../entities/application/api/projects';
import { Choice } from "../../shared/ui/Choice";
import { Button } from "../../shared/ui/actions";
import { ErrorNote, Loading } from "../../shared/ui/feedback";
import { Heading, Field } from "../../shared/ui/layout";
import { assertProject } from '../../shared/model/page';
import { go } from '../../shared/lib/navigation';
import { text } from '../../shared/lib/format';
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
    const act=async(task:()=>Promise<void>)=>{setBusy(true);setError(undefined);try{await task()}catch(value){setError(value)}finally{setBusy(false)}};
    const choices = state.data?.revision === draft?.revision ? draft?.choices ?? {} : {};
    const setChoices = (update: Record<string, CandidateSelection> | ((value: Record<string, CandidateSelection>) => Record<string, CandidateSelection>)) => { if (state.data) setDraft({revision: state.data.revision, choices: typeof update === 'function' ? update(choices) : update}); };
    useEffect(() => { savePending(draftKey, draft); }, [draftKey, draft]);
    if (state.loading)
        return embedded?<Loading/>:<PageSkeleton view="/application" title="业务名称"/>;
    if (state.error || !state.data)
        return <ErrorNote error={state.error}/>;
    const value = state.data;
    return <>
    {!embedded&&<><div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go('/application')}>应用与来源</Button></div>
    <Heading title="核对业务角色与操作">整理接口、源码与人工提供的业务线索，确认它们在当前应用中的含义。</Heading></>}
    <section className="jj-understanding-workspace">
      <header className="jj-understanding-toolbar"><p>核对业务含义，访问权限仍需单独确认。</p><div className="jj-inline-actions"><Button disabled={busy} onClick={()=>go('/permissions')}>返回权限规则</Button><Button kind="primary" busy={busy} disabled={!Object.keys(choices).length} onClick={()=>void act(async()=>{await projectsApi.decideCandidates(projectId,value.revision,Object.values(choices));setChoices({});state.reload();go('/permissions')})}>保存业务确认</Button></div></header>
      {Boolean(error)&&<ErrorNote error={error}/>}
      <div className="jj-understanding-groups">{([{kind:'ROLE',label:'业务角色',items:value.role_candidates},{kind:'ACTION',label:'业务操作',items:value.action_candidates}] as const).map(group=><section className="jj-understanding-group" key={group.kind}>
        <header><h2>{group.label}</h2><span>{group.items.length} 项线索</span></header>
        <div className="jj-understanding-add"><Field label={'补充'+group.label} hint={Object.keys(choices).length?'先保存当前审阅，再添加新项。':undefined}><input value={manual[group.kind]} disabled={busy} onChange={event=>setManual({...manual,[group.kind]:event.target.value})}/></Field><Button disabled={busy||!manual[group.kind].trim()||Boolean(Object.keys(choices).length)} onClick={()=>void act(async()=>{if(group.kind==='ROLE')await projectsApi.addRole(projectId,manual.ROLE.trim(),value.revision);else await projectsApi.addAction(projectId,manual.ACTION.trim(),'UNKNOWN',value.revision);setManual({...manual,[group.kind]:''});state.reload()})}>添加{group.kind==='ROLE'?'角色':'操作'}</Button></div>

        <div className="jj-understanding-list">{group.items.map(item=>{
          const selection=choices[item.candidate_id]??{kind:group.kind,candidate_id:item.candidate_id,decision:item.decision==='CONFIRMED'?'CONFIRMED':item.decision==='REJECTED'?'REJECTED':'PROPOSED',display_name:item.display_name};
          return <div className="jj-understanding-row" key={item.candidate_id}>
            <input disabled={busy} aria-label={group.label+'名称'} value={selection.display_name} onChange={event=>setChoices(current=>({...current,[item.candidate_id]:{...selection,display_name:event.target.value}}))}/>
            <Choice disabled={busy} aria-label={text(item.display_name)+'的处理方式'} value={selection.decision} onValueChange={decision=>setChoices(current=>({...current,[item.candidate_id]:{...selection,decision:decision as CandidateSelection['decision']}}))}><option value="PROPOSED">暂不决定</option><option value="CONFIRMED">与检查有关</option><option value="REJECTED">不属于当前业务</option></Choice>
            <details><summary>来源依据{item.stale?' · 需要更新':''}</summary>{item.origin==='MANUAL'&&<p className="jj-small">人工提供并确认的业务说明。</p>}{item.evidence.map((evidence,index)=><p className="jj-small" key={index}>{evidence.relative_path}{evidence.detector==='API_SOURCE'?' · '+evidence.symbol:'，第 '+evidence.line_start+' 行'}</p>)}</details>
          </div>
        })}</div>{!group.items.length&&<p className="jj-small jj-muted">尚未识别到可确认的线索。</p>}
      </section>)}</div>
    </section>
  </>;
}
