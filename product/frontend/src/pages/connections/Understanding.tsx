import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { useEffect, useState } from 'react';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { projectsApi, type CandidateSelection } from '../../entities/application/api/projects';
import { Choice } from "../../shared/ui/Choice";
import { Button } from "../../shared/ui/actions";
import { ErrorNote } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
import { assertProject } from '../../shared/model/page';
import { go } from '../../shared/lib/navigation';
import { text } from '../../shared/lib/format';
import { readPending, savePending } from '../../shared/lib/operations';
import { useRead } from '../../shared/lib/useRead';
export function Understanding({ projectId, onError }: {
    projectId: string;
    onError: (error: unknown) => void;
}) {
    const state = useRead('business-understanding:' + projectId, async () => { const value = await projectsApi.understanding(projectId); assertProject(value.project_id, projectId); return value; });
    const draftKey = 'jiejian.studio.business-draft:' + projectId;
    const [draft, setDraft] = useState(() => readPending<{revision: number; choices: Record<string, CandidateSelection>}>(draftKey)), [busy, setBusy] = useState(false);
    const choices = state.data?.revision === draft?.revision ? draft?.choices ?? {} : {};
    const setChoices = (update: Record<string, CandidateSelection> | ((value: Record<string, CandidateSelection>) => Record<string, CandidateSelection>)) => { if (state.data) setDraft({revision: state.data.revision, choices: typeof update === 'function' ? update(choices) : update}); };
    useEffect(() => { savePending(draftKey, draft); }, [draftKey, draft]);
    if (state.loading)
        return <PageSkeleton view="/application" title="业务名称"/>;
    if (state.error || !state.data)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    const value = state.data;
    return <>
    <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => go('/application')}>应用连接</Button></div>
    <Heading title="核对业务名称"/>
    <section className="jj-understanding-workspace">
      {([{ kind: 'ROLE', label: '业务角色', items: value.role_candidates }, { kind: 'ACTION', label: '业务操作', items: value.action_candidates }] as const).map(group => <section className="jj-understanding-group" key={group.kind}>
        <header><h2>{group.label}</h2><span>{group.items.length} 项源码线索</span></header>
        <div className="jj-understanding-list">{group.items.map(item => {
                const selection = choices[item.candidate_id] ?? { kind: group.kind, candidate_id: item.candidate_id, decision: item.decision === 'CONFIRMED' ? 'CONFIRMED' : item.decision === 'REJECTED' ? 'REJECTED' : 'PROPOSED', display_name: item.display_name };
                return <div className="jj-understanding-row" key={item.candidate_id}>
          <input disabled={busy} aria-label={group.label + '名称'} value={selection.display_name} onChange={event => setChoices(current => ({ ...current, [item.candidate_id]: { ...selection, display_name: event.target.value } }))}/>
          <Choice disabled={busy} aria-label={text(item.display_name) + '的处理方式'} value={selection.decision} onValueChange={value => setChoices(current => ({ ...current, [item.candidate_id]: { ...selection, decision: value as CandidateSelection['decision'] } }))}><option value="PROPOSED">暂不决定</option><option value="CONFIRMED">确认采用</option><option value="REJECTED">不属于当前业务</option></Choice>
          <details><summary>源码线索{item.stale ? '需要更新' : ''}</summary>{item.evidence.map((evidence, index) => <p className="jj-small" key={index}>{evidence.relative_path}，第 {evidence.line_start} 行</p>)}</details>
        </div>;
            })}</div>{!group.items.length && <p className="jj-small jj-muted">尚未识别到可确认的线索。</p>}
      </section>)}
      <footer className="jj-workspace-footer"><p>名称确认用于整理业务线索，访问规则仍需单独审阅。</p><div className="jj-inline-actions"><Button disabled={busy} onClick={() => go('/permissions')}>返回权限规则</Button><Button kind="primary" busy={busy} disabled={!Object.keys(choices).length} onClick={() => void (async () => { setBusy(true); try {
        await projectsApi.decideCandidates(projectId, value.revision, Object.values(choices));
        setChoices({});
        state.reload();
        go('/permissions');
    }
    catch (error) {
        onError(error);
    }
    finally {
        setBusy(false);
    } })()}>保存业务确认</Button></div></footer>
    </section>
  </>;
}
import './styles.css'
