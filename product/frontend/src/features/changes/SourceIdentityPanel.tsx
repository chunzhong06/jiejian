// 按精确项目和记录读取源码对照；陈旧响应撤下，读取失败不冒充“内容相同”。
import { Button, Spin } from 'antd'
import { CodeOutlined, FileTextOutlined } from '@ant-design/icons'
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/http'
import { sourceIdentityApi, type SourceIdentity } from '../../api/sourceIdentity'
import { formatTimestamp } from '../../app/presentation'
import './delivery.css'

const titles = { SAME: '记录范围内的源码内容一致', CHANGED: '当前源码已不同于这份记录', NO_BASELINE: '缺少可比较的源码记录', UNAVAILABLE: '暂时无法核对当前源码' }
export function SourceIdentityPanel({ projectId, recordId, kind, onNavigate, onIntegrityError, historicalOnly }: {
  projectId: string; recordId: string; kind: 'runs' | 'source-changes'; onNavigate: (path: string) => void; onIntegrityError?: (error: ApiError) => void; historicalOnly?: boolean
}) {
  const [value, setValue] = useState<SourceIdentity | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [revision, setRevision] = useState(0)
  const reportIntegrity = useRef(onIntegrityError)
  reportIntegrity.current = onIntegrityError
  useEffect(() => {
    let valid = true
    setValue(null); setLoading(true); setFailed(false)
    void sourceIdentityApi.read(projectId, kind, recordId).then(next => {
      if (next.project_id !== projectId || (kind === 'runs' ? next.run_id !== recordId || next.change_id !== null : next.change_id !== recordId || next.run_id !== null))
        throw new ApiError('STATE_PRECONDITION', '源码记录关联不一致。')
      if (valid) setValue(next)
    }).catch(error => { if (valid) {
      setFailed(true)
      // 发布包损坏或记录错配时，父页面同时撤下旧的安全结论；普通网络失败只影响本投影。
      if (error instanceof ApiError && (error.code.startsWith('ARTIFACT_') || error.code === 'STATE_PRECONDITION')) reportIntegrity.current?.(error)
    } }).finally(() => { if (valid) setLoading(false) })
    return () => { valid = false }
  }, [projectId, recordId, kind, revision])
  // props 改变后的首帧也不能展示上一条记录，不能只等待 effect 清理。
  const current = value?.project_id === projectId && (kind === 'runs' ? value.run_id === recordId : value.change_id === recordId) ? value : null
  const git = current?.current_git
  const recorded = current?.recorded
  const historicalGit = !recorded || recorded.git_status === 'NOT_RECORDED' ? '当时的 Git 提交未记录，不能用当前提交补填。' : recorded.git_status === 'NOT_A_REPOSITORY' ? '当时未使用 Git，保留内容身份。' : recorded.git_status === 'UNBORN' ? '当时仓库尚无首次提交。' : recorded.git_status === 'UNAVAILABLE' || recorded.consistency === 'UNAVAILABLE' ? '当时未能可靠核对 Git 上下文。' : recorded.has_local_changes == null ? '当时工作区状态未能核对。' : recorded.has_local_changes ? '当时存在未提交修改。' : '当时源码目录无未提交修改。'
  const sameCommitChanged = Boolean(recorded?.head && recorded.head === git?.head && current?.comparison === 'CHANGED' && recorded.consistency === 'CONSISTENT')
  const gitLabel = !git || git.status === 'UNAVAILABLE' ? 'Git 上下文暂不可用' : git.status === 'NOT_A_REPOSITORY' ? '未使用 Git' : git.status === 'UNBORN' ? '仓库尚无首次提交' : git.has_local_changes === null ? '已读取提交，工作区状态未核对' : git.has_local_changes ? '源码目录含未提交修改' : '源码目录无未提交修改'
  return <section className="source-identity" aria-label="源码对应">
    <header className="delivery-heading"><div><p className="editorial-eyebrow">{kind === 'runs' ? '本轮结果 / 源码对应' : '本批修改 / 源码对应'}</p><h2>{loading ? '正在核对源码记录' : failed || !current ? '源码对应读取失败' : sameCommitChanged ? '同一提交，源码内容已经不同' : titles[current.comparison]}</h2><p className="editorial-muted">内容指纹比较只覆盖受控扫描范围；历史记录不会随本地修改而改变。</p></div><Button loading={loading} onClick={() => setRevision(n => n + 1)}>重新核对源码</Button></header>
    {loading && <Spin aria-label="正在读取源码对应"/>}
    {failed && <p role="alert">暂时无法读取源码对应，请重试。原检查结果仍属于当时的记录，不能据此判断当前源码。</p>}
    {current && <>
      <div className="source-comparison">
        <section><div className="source-column-title"><FileTextOutlined aria-hidden/><span>本{kind === 'runs' ? '轮关联' : '批登记'}的源码记录</span></div><h3>{current.recorded ? '内容指纹已保存' : '尚无可用内容记录'}</h3><p>{current.recorded?.file_count != null ? `记录范围包含 ${current.recorded.file_count} 个文件` : '文件清单未取得，不推算记录范围'}</p><p className="editorial-muted">{historicalGit}</p><span className="source-tag">{recorded?.head && recorded.consistency === 'CONSISTENT' ? `当时提交 ${recorded.head.slice(0,10)}` : current.recorded ? '保留原记录' : '缺少基线'}</span></section>
        <section><div className="source-column-title"><CodeOutlined aria-hidden/><span>当前本地源码</span></div><h3>{gitLabel}</h3><p>{current.comparison === 'SAME' ? '与所选记录的内容指纹一致' : current.comparison === 'CHANGED' ? '与所选记录的内容指纹不同' : '内容一致性尚不能确认'}</p><p className="editorial-muted">Git 状态与内容对照分别读取；提交相同也可能存在本地修改。</p><span className="source-tag">{git?.head ? `提交 ${git.head.slice(0, 10)}` : '以内容记录为依据'}</span></section>
      </div>
      {sameCommitChanged && <aside className="source-comparison-explanation"><strong>为什么提交相同，内容仍不同？</strong><p>Git 提交不包含未提交修改，内容指纹才反映本次记录范围。历史记录保持不变。</p></aside>}
      <aside className="source-boundary"><strong>运行目标版本 · 尚无独立标识</strong><p>本地源码身份不能证明目标服务正在运行这一版。{kind === 'runs' ? '原结论继续保留，但不自动代表当前源码或当前部署。' : '修改登记和源码一致均不表示修复已经通过验证。'}</p></aside>
      <details className="delivery-technical"><summary>查看完整源码引用</summary><dl><dt>记录内容指纹</dt><dd><code>{current.recorded?.fingerprint ?? '未记录'}</code></dd><dt>记录引用</dt><dd><code>{current.recorded?.snapshot_id ?? '未记录'}</code></dd><dt>当时 Git 提交</dt><dd><code>{recorded?.head ?? '未记录'}</code></dd><dt>历史观察时间</dt><dd>{recorded?.observed_at_us == null ? '未记录' : formatTimestamp(recorded.observed_at_us)}</dd><dt>历史观察引用</dt><dd><code>{recorded?.observation_id ?? '未记录'}</code></dd><dt>当前内容指纹</dt><dd><code>{current.current_fingerprint ?? '未取得'}</code></dd><dt>当前 Git 提交</dt><dd><code>{git?.head ?? '未取得'}</code></dd><dt>本次读取时间</dt><dd>{formatTimestamp(current.observed_at_us)}</dd></dl></details>
      {kind === 'runs' && !historicalOnly && <Button onClick={() => onNavigate('/changes')}>查看当前代码变化</Button>}
    </>}
  </section>
}
