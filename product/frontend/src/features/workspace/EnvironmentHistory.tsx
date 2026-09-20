// 已归档环境的历史只读入口；直接使用普通历史和结果组件，不查询执行准备或创建新检查。
import { Button, Spin } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../api/http'
import { projectsApi, type ProjectDto } from '../../api/projects'
import { currentChecksApi, type ResultStory } from '../../api/currentChecks'
import { CheckHistoryPage } from '../testing/CheckHistoryPage'
import { CurrentResultStory } from '../testing/CurrentResultStory'
import { SourceIdentityPanel } from '../changes/SourceIdentityPanel'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'

export function EnvironmentHistory({ projectId, onBack, onError }: { projectId: string; onBack: () => void; onError: (error: ApiError) => void }) {
  const [project, setProject] = useState<ProjectDto | null>(null), [runId, setRunId] = useState<string | null>(null), [failed, setFailed] = useState(false)
  const [caseId, setCaseId] = useState<string | null>(null)
  useEffect(() => {
    let valid = true
    setProject(null); setFailed(false); setRunId(null)
    void projectsApi.project(projectId).then(value => {
      if (value.project_id !== projectId) throw new ApiError('STATE_PRECONDITION', '历史项目关联不一致。')
      if (valid) setProject(value)
    }).catch(error => { if (valid) { setFailed(true); onError(error as ApiError) } })
    return () => { valid = false }
  }, [projectId, onError])
  const navigate = useCallback((path: string) => {
    const url = new URL(path, 'http://localhost')
    if (url.pathname === '/history' || url.pathname === '/tests') { setRunId(url.searchParams.get('run_id')); setCaseId(url.searchParams.get('case_id')) }
  }, [])
  return <><Button type="link" onClick={onBack}>返回环境记录</Button><p className="editorial-muted">正在查看原项目保存的历史，环境状态不会改写这些结果。</p>{failed ? <p role="alert">历史项目暂时无法读取，请返回后重试。</p> : !project ? <Spin/> : <CheckHistoryPage project={project} onError={onError} onNavigate={navigate} requestedRunId={runId} renderRun={(id, back) => <EnvironmentResult key={id} projectId={projectId} runId={id} caseId={caseId} onBack={back} onNavigate={navigate} onError={onError}/>}/>}</>
}
function EnvironmentResult({ projectId, runId, caseId, onBack, onNavigate, onError }: { projectId: string; runId: string; caseId: string | null; onBack: () => void; onNavigate: (path: string) => void; onError: (error: ApiError) => void }) {
  const [story, setStory] = useState<ResultStory | null>(null), [failed, setFailed] = useState(false), [source, setSource] = useState(false)
  useEffect(() => {
    let valid = true
    setStory(null); setFailed(false)
    void currentChecksApi.status(runId).then(async status => {
      if (status.run.project_id !== projectId || status.run.run_id !== runId) throw new ApiError('STATE_PRECONDITION', '检查所属项目不一致。')
      if (status.result_integrity !== 'VALID') throw new ApiError('ARTIFACT_MANIFEST', '这条记录尚无完整性校验通过的已发布结果。')
      const next = await currentChecksApi.story(runId)
      if (next.project_id !== projectId || next.run_id !== runId || next.verdict !== status.run.verdict) throw new ApiError('ARTIFACT_MANIFEST', '历史结果关联不一致。')
      if (valid) setStory(next)
    }).catch(error => { if (valid) { setFailed(true); onError(error as ApiError) } })
    return () => { valid = false }
  }, [projectId, runId, onError])
  const invalidate = (error: ApiError) => { setStory(null); setFailed(true); onError(error) }
  return <EditorialPage label="环境历史结果"><Button type="link" onClick={onBack}>返回原项目检查历史</Button>{failed ? <p role="alert">无法展示本轮已发布结论。返回列表可查看生命周期与完整性状态。</p> : !story ? <Spin/> : <><EditorialHeader eyebrow="原项目 / 已保存结果" title={story.judgement}/><nav className="result-view-switch" aria-label="历史结果视图"><Button aria-pressed={!source} type={!source ? 'primary' : 'text'} onClick={() => setSource(false)}>结果与证据</Button><Button aria-pressed={source} type={source ? 'primary' : 'text'} onClick={() => setSource(true)}>源码对应</Button></nav>{source ? <SourceIdentityPanel projectId={projectId} recordId={runId} kind="runs" historicalOnly onNavigate={() => setSource(false)} onIntegrityError={invalidate}/> : <CurrentResultStory historicalOnly requestedCaseId={caseId} story={story} onError={invalidate} onNavigate={onNavigate}/>}</>}</EditorialPage>
}
