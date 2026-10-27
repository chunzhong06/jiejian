import { ruleWorkspaceApi } from '../../entities/permission/api/ruleWorkspace';
import { sourceChangesApi } from '../../entities/source-change/api/sourceChanges';
import { assertProject } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import { useRead } from '../../shared/lib/useRead';
import { Badge, ErrorNote, Loading } from "../../shared/ui/feedback";
export function RuleCheckScope({ projectId, changeId }: {
    projectId: string;
    changeId: string;
}) {
    const state = useRead('rule-check-scope:' + projectId + ':' + changeId, async () => {
        const [workspace, change] = await Promise.all([ruleWorkspaceApi.read(projectId), sourceChangesApi.show(projectId, changeId)]);
        assertProject(workspace.project_id, projectId);
        assertProject(change.manifest.project_id, projectId);
        if (change.manifest.change_id !== changeId)
            throw new Error('修复记录与本次检查不一致。');
        return { workspace, change };
    });
    if (state.loading)
        return <Loading>正在读取本次修复目标</Loading>;
    if (state.error)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    if (!state.data)
        return null;
    const { workspace, change } = state.data;
    const rules = workspace.rules.filter(rule => change.rule_targets?.some(target => target.permission.intent_id === rule.permission.intent_id && target.permission.revision === rule.permission.revision && target.permission.intent_hash === rule.permission.intent_hash) || rule.issues.some(issue => issue.contract.repair_fingerprint === change.manifest.repair_reference?.repair_fingerprint));
    return rules.length > 0 ? <section className="jj-rule-check-scope"><header><Badge tone="accent">修复复验</Badge><h2>本次修改针对的规则</h2></header><div>{rules.map(rule => <article key={rule.permission.intent_id}><strong>{text(rule.title)}</strong><span>{text(rule.resource_scope)}</span></article>)}</div><footer><span>复查原违规场景</span><span>确认正常功能保留</span><span>检查相关权限是否退化</span></footer></section> : null;
}
