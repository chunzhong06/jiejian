// 完成页与结果页共用同一交接：复制准确引用，Agent 通过 MCP 读取，界鉴保留原始结论。
import { currentChecksApi, type ResultStory } from '../../api/checks/currentChecks'
import { ApiError } from '../../api/http'
import { AgentAssistEntry } from '../../shared/ui/AgentAssistEntry'

export function ResultAgentHandoff({ story, caseId, onNavigate }: {
  story: ResultStory; caseId?: string; onNavigate: (path: string) => void
}) {
  const returnTo = `/tests?run_id=${encodeURIComponent(story.run_id)}${caseId ? `&case_id=${encodeURIComponent(caseId)}` : ''}`
  return <section className="result-agent-handoff" aria-label="让 Agent 解释检查结果"><AgentAssistEntry
    projectId={story.project_id} contextKey={`result:${story.run_id}:${caseId ?? 'all'}`} requiredLevel="READ"
    heading={<div><h3>回到 Agent 解读这轮检查</h3><p className="editorial-muted">结果已保存。复制请求到原来的 Agent 对话中，它会通过 MCP 读取结果和证据；原始记录仍可在界鉴查看。</p></div>}
    title="从实验结果继续讨论与修改" description="先解释权限要求、实际操作、业务结果和证据缺口。需要修复时，再由你决定下一步；复制请求不代表 Agent 已经收到或读取。"
    returnTo={returnTo} onNavigate={onNavigate}
    loadContext={async () => {
      const value = await currentChecksApi.story(story.run_id)
      if (value.run_id !== story.run_id || value.project_id !== story.project_id || (caseId && !value.actions.some(item => item.case_id === caseId)))
        throw new ApiError('ARTIFACT_MANIFEST', '结果对象已经不可读。')
      return { projectId: story.project_id, revisionKey: `${story.run_id}:${caseId ?? 'all'}`,
        requestText: `请通过界鉴 MCP 解读本轮检查。project_id=${story.project_id}，run_id=${story.run_id}${caseId ? `，case_id=${caseId}` : ''}。
1. 调用 jiejian_result_show，${caseId ? '聚焦指定检查项' : '逐项解释本轮检查'}。不要取最近一次结果代替这一轮。
2. 按返回的 case_id、evidence_refs 调用 jiejian_evidence_show；先读索引，再用 record_ref 读取必要证明及 Trace 事件。说明原权限要求、测试账号、资源、界鉴实际操作、观察到的结果和已发布结论。
3. 区分必要证明、辅助事件和未知信息。路径缺失时核对采集缺口，不按时间或响应补造因果。引用 run_id、case_id、evidence_id、record_ref 和返回的 review_url，方便回到界鉴核对。
4. BLOCK 时读取 jiejian_repair_show，说明必须消除的后果和必须保留的正常业务；INCONCLUSIVE 时说明缺哪项证据；PASS 时说明验证范围。
5. 先向我解释并讨论下一步。获得修改授权后，沿用界鉴任务上下文和修复引用，登记实际源码变化、核对新运行实例，再按现有授权预览并提交复验；用原问题和正常业务对照解释复验结果。不要自动改写权限、采用来源、修改应用或发起新检查。` }
    }}/></section>
}
