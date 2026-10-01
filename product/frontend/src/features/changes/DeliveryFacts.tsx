// 将已保存交付差异、声明与精确检查并列；只读结果不能触发第二次提交。
import { Button, Segmented } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { developmentApi, type DeliveryDetails } from '../../api/development'
import type { SourceChangeViewDto } from '../../api/sourceChanges'
import { ApiError } from '../../api/http'
import { useLiveRead } from '../../app/useLiveRead'
import { repairLabels } from '../../api/repairs'

export function DeliveryFacts({ projectId, change, acceptanceOnly = false, changesOnly = false, providedDetails, onNavigate, onError }: { projectId: string; change: SourceChangeViewDto; acceptanceOnly?: boolean; changesOnly?: boolean; providedDetails?: DeliveryDetails | null; onNavigate: (path: string) => void; onError: (error: ApiError) => void }) {
  const [details, setDetails] = useState<DeliveryDetails | null>(null), [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false), [basis, setBasis] = useState('relative')
  const key = `${projectId}:${change.manifest.change_id}`, currentKey = useRef(key); currentKey.current = key
  useEffect(() => { setDetails(null); setLoaded(false); setFailed(false); setBasis('relative') }, [key])
  // 列表已取得同一精确交付时直接复用，避免切换页签再次校验整套发布包。
  useLiveRead(providedDetails === undefined ? key : undefined, async () => {
    try { const next = await developmentApi.details(projectId, change.manifest.change_id)
      if (currentKey.current !== key) return
      if (next && (next.project_id !== projectId || next.delivery.change_id !== change.manifest.change_id || next.context.context_id !== next.delivery.context_id || next.context.project_id !== projectId || next.context.task_id !== next.delivery.task_id)) throw new ApiError('STATE_PRECONDITION', '交付详情关联不一致。')
      setDetails(next); setLoaded(true); setFailed(false)
    } catch (error) { if (currentKey.current === key) { setDetails(null); setFailed(true); setLoaded(true); onError(error as ApiError) }; throw error }
  }, 10000)
  const effective = providedDetails === undefined ? details : providedDetails
  const ready = providedDetails !== undefined || loaded
  const current = effective?.delivery.change_id === change.manifest.change_id && effective.project_id === projectId ? effective : null
  const comparison = current ? basis === 'cumulative' ? current.cumulative_change : current.relative_change : change.change_set
  const actual = [...change.change_set.added_paths, ...change.change_set.modified_paths, ...change.change_set.removed_paths]
  const unclaimed = change.manifest.claimed_paths.length ? actual.filter(path => !change.manifest.claimed_paths.includes(path)) : []
  const unobserved = change.manifest.claimed_paths.filter(path => !actual.includes(path))
  const verification = current?.verification
  const summary = verification?.run_id ? verification.verdict === 'BLOCK' ? '发现权限问题' : verification.verdict === 'PASS' ? verification.runtime_status === 'MATCHED' ? '本批权限要求已验证' : '检查已通过，交付运行对应未确认' : verification.verdict === 'INCONCLUSIVE' ? '证据不足，尚不能确认' : '检查结果尚未发布或未通过完整性核验' : current ? '这批交付尚无关联检查' : '历史修改未关联精确检查'
  return <div className="delivery-facts" aria-label="交付差异与验收">
    {!ready && <p role="status">正在核对这次修改的检查记录…</p>}
    {providedDetails === undefined && failed && <p role="alert">交付关联暂时无法核对，正在重试。不能将其它检查当作本批结果。</p>}
    {current && <div className="delivery-scope"><span>第 {current.delivery.ordinal} 批交付</span><span>关联修订 {current.context.revision}</span><span>沿用 {current.context.permission_refs.length} 条批准权限</span></div>}
    {!acceptanceOnly && <section className="delivery-file-section"><header><div><h3>实际文件变化</h3><p>根据已保存的源码快照比较。</p></div>{current && <Segmented aria-label="选择差异起点" value={basis} onChange={value => setBasis(String(value))} options={[{ label: current.delivery.ordinal === 1 ? '本次变化' : '相对上次修改', value: 'relative' }, { label: '相对起始快照', value: 'cumulative' }]}/>}</header>
      {comparison.status === 'NO_BASELINE' ? <p>缺少可比较基线，不推算文件增删改。</p> : <ul className="delivery-file-list">{(['added_paths', 'modified_paths', 'removed_paths'] as const).flatMap((field, i) => comparison[field].map(path => <li key={field + path}><span>{['新增', '修改', '删除'][i]}</span><code>{path}</code></li>))}{!comparison.added_paths.length && !comparison.modified_paths.length && !comparison.removed_paths.length && <li>该比较范围内没有文件内容变化。</li>}</ul>}
      <div className="delivery-declaration"><h4>声明与实际变化</h4>{change.change_set.status === 'NO_BASELINE' ? <p>缺少基线，暂不能核对文件声明与实际变化的差异。</p> : !change.manifest.claimed_paths.length ? <p>本批未提供文件声明；上方列表来自实际源码。</p> : <><p>{unclaimed.length ? `发现 ${unclaimed.length} 个声明外的变化文件。` : '实际变化均已列入文件声明。'}</p>{unclaimed.map(path => <code key={path}>{path}</code>)}{!!unobserved.length && <><p>声明中未观察到内容变化的文件：</p>{unobserved.map(path => <code key={path}>{path}</code>)}</>}</>}<p>文件变化不能单独证明作者身份或修复有效。</p></div>
    </section>}
    {ready && (providedDetails !== undefined || !failed) && !changesOnly && <section className="delivery-acceptance"><header><div><p className="editorial-eyebrow">验收结果</p><h3>{summary}</h3></div>{verification?.run_id ? <Button type="primary" onClick={() => onNavigate('/history?run_id=' + encodeURIComponent(verification.run_id!))}>查看本批检查记录</Button> : <Button type="primary" disabled={!change.revalidation.can_execute} onClick={() => onNavigate('/tests?change_id=' + encodeURIComponent(change.manifest.change_id))}>检查这次变化</Button>}</header>
      {verification?.repair_status && <p>原题复验：{repairLabels[verification.repair_status as keyof typeof repairLabels] ?? verification.repair_status}</p>}
      {verification?.run_id && <p>只对应这批交付关联的检查；查看记录不会再次提交检查。</p>}

      <p className="editorial-muted">登记修改不表示权限通过；开发需求继续在原客户端讨论。</p>
      <Button type="link" onClick={() => onNavigate('/tests?change_id=' + encodeURIComponent(change.manifest.change_id) + '&materials=1')}>核对本批检查材料</Button>
    </section>}
  </div>
}
