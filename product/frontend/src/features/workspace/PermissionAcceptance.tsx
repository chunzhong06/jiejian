// 只读取指定 Run 的已发布事实；不以相同源码、最近时间或准备状态替代本批检查。
import { Button } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { currentChecksApi, type ResultStory } from '../../api/currentChecks'
import { ApiError } from '../../api/http'
import { useLiveRead } from '../../app/useLiveRead'

export function PermissionAcceptance({ projectId, runId, onNavigate }: { projectId: string; runId: string | null; onNavigate: (path: string) => void }) {
  const [story, setStory] = useState<ResultStory | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const key = `${projectId}:${runId ?? ''}`
  const currentKey = useRef(key); currentKey.current = key
  useEffect(() => { setStory(null); setUnavailable(false) }, [key])
  const live = useLiveRead(runId ? key : undefined, async () => {
    try {
      const value = await currentChecksApi.story(runId!)
      if (currentKey.current !== key) return
      if (value.project_id !== projectId || value.run_id !== runId) throw new ApiError('ARTIFACT_MANIFEST', '检查结果关联不一致。')
      setStory(value); setUnavailable(false)
    } catch (error) {
      if (currentKey.current === key) { setUnavailable(true); setStory(null) }
      throw error
    }
  }, 10000)
  const current = story?.project_id === projectId && story.run_id === runId ? story : null
  return <section className="workbench-acceptance" aria-label="本轮权限验收">
    <header className="workbench-section-heading"><div><h2>本轮权限验收</h2><p>{!runId ? '当前交付尚无关联结果；历史检查保留在记录与证据中。' : current ? `权限版本 ${current.policy_epoch} · 每一行对应本轮实际执行的检查项。` : unavailable ? '暂时无法核验本轮结果，不展示缓存结论。' : '正在读取本轮已发布事实。'}</p></div><Button type="link" onClick={() => onNavigate('/permissions')}>全部权限要求 →</Button></header>
    {current && <><p className="acceptance-scope">{current.runtime_status === 'MATCHED' ? '检查前后已核对受控运行实例。' : current.runtime_status === 'UNCONFIRMED' ? '本轮运行对应未确认，不能据此认定当前交付已验收。' : '本轮未独立核对运行版本，结论仅属于记录中的检查范围。'}</p>
      <div className="acceptance-table-wrap"><table className="acceptance-table"><thead><tr><th scope="col">已确认要求</th><th scope="col">实际结果</th><th scope="col">本项判断</th><th scope="col">依据</th></tr></thead><tbody>{current.actions.map(item => <tr key={item.case_id}>
        <td data-label="已确认要求"><strong>{item.fact_comparison.planned_identity.label ?? item.fact_comparison.planned_identity.actor_label ?? '计划账号'}{item.permission.expectation === 'DENY' ? '不得' : '可以'}{item.display_name}</strong><small>资源属于：{item.fact_comparison.planned_resource_owner?.label ?? '以本轮冻结记录为准'}</small></td>
        <td data-label="实际结果"><span className="acceptance-response">{item.fact_comparison.http_surface.http_status === null ? '未取得 HTTP 状态' : `HTTP ${item.fact_comparison.http_surface.http_status}`} · {item.fact_comparison.http_explanation}</span>{item.fact_comparison.effects.map(effect => <p key={effect.effect_id}>{effect.business_label}：{effect.judgement}</p>)}</td>
        <td data-label="本项判断"><span className="acceptance-judgement">{item.judgement}</span></td><td data-label="依据"><Button type="link" aria-label={`查看${item.fact_comparison.planned_identity.label ?? '计划账号'}${item.display_name}的证据`} onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(current.run_id)}&case_id=${encodeURIComponent(item.case_id)}`)}>证据 →</Button></td>
      </tr>)}</tbody></table></div></>}
    {(unavailable || live.retrying) && <p role="status" className="workbench-sync">{live.stopped ? '结果读取校验未通过，请进入记录与证据核对。' : '读取未成功，正在重试。'}</p>}
  </section>
}
