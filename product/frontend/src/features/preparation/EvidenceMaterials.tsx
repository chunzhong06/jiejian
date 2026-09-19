// 已保存材料的只读说明；查询失败或跨项目切换时撤下旧快照，不推导执行条件。
import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Empty, Spin } from 'antd'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import { ApiError } from '../../api/http'
import { preparationApi, type EvidenceMaterialDetail } from '../../api/preparation'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import './evidence-materials.css'

const statuses = { SATISFIED: '材料已准备', NEEDS_USER: '材料不足', STALE: '材料需要更新', BLOCKED: '需要先确认', NOT_REQUIRED: '无需此项材料' }
const reasons: Record<string, string> = {
  EVIDENCE_SNAPSHOT_CHANGED: '读取期间材料发生变化，请刷新后重新查看。',
  REGISTERED_OBSERVER_UNAVAILABLE: '当前环境中未找到已绑定的来源。历史结果仍保留原有证据。',
  PROOF_CAPABILITY_UNAVAILABLE: '当前没有可核对的能力声明，无法确认来源支持的范围。',
  EFFECT_EVIDENCE_REQUIRED: '这项业务结果尚缺少对应的证明材料。',
}
const capability = (value: boolean | null) => value === true ? '声明支持' : value === false ? '声明不支持' : '尚不能确认'

export function EvidenceMaterials({ projectId, actionId, onBack }: {
  projectId: string; actionId: string; onBack: () => void
}) {
  const [snapshot, setSnapshot] = useState<EvidenceMaterialDetail>()
  const [selected, setSelected] = useState<string>()
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const title = useRef<HTMLHeadingElement>(null)
  useEffect(() => { title.current?.focus() }, [])
  useEffect(() => {
    let active = true
    setSnapshot(undefined); setLoading(true); setFailed(false)
    void preparationApi.evidence(projectId, actionId).then(value => {
      if (!active) return
      if (value.project_id !== projectId || value.action_id !== actionId) throw new ApiError('STATE_PRECONDITION', '材料与当前动作不一致')
      setSnapshot(value)
      setSelected(previous => value.effects.some(item => item.effect_id === previous) ? previous : value.effects[0]?.effect_id)
    }).catch(() => { if (active) setFailed(true) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [projectId, actionId, revision])
  // 渲染时也校验归属，避免 effect 清理之前短暂显示上一项目的材料。
  const current = snapshot?.project_id === projectId && snapshot.action_id === actionId ? snapshot : undefined
  const effect = current?.effects.find(item => item.effect_id === selected)
  const snapshotChanged = effect?.reason_codes.includes('EVIDENCE_SNAPSHOT_CHANGED')
  return <EditorialPage label="证明要求与材料">
    <div className="proof-page-actions"><Button icon={<ArrowLeftOutlined aria-hidden="true" />} onClick={onBack}>返回准备材料</Button><Button icon={<ReloadOutlined aria-hidden="true" />} loading={loading} onClick={() => setRevision(value => value + 1)}>刷新材料详情</Button></div>
    <EditorialHeader eyebrow="当前工作 / 证明材料" title="看清每项结果的证明依据"><p className="editorial-muted">查看已保存的材料、来源声明与当前缺口。</p></EditorialHeader>
    <h2 className="proof-action-title" ref={title} tabIndex={-1}>{current?.action_label ?? '证明要求与材料'}</h2>
    {loading && <div role="status" className="proof-loading"><Spin /> 正在读取当前材料…</div>}
    {failed && <Alert type="warning" showIcon message="材料详情暂时无法读取" description="旧快照已撤下。请刷新重试；这不会修改材料或发起检查。" />}
    {current && !current.effects.length && <Empty description="当前动作没有需要说明的结果证明材料" />}
    {!!current?.effects.length && <div className="proof-workspace">
      <nav className="proof-index" aria-label="业务结果索引"><p className="editorial-eyebrow">需要证明的业务结果</p>{current.effects.map((item, index) => <button key={item.effect_id} aria-current={selected === item.effect_id ? 'true' : undefined} onClick={() => setSelected(item.effect_id)}><span className="proof-index-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{item.business_label}</strong><small>{statuses[item.material_status]}</small></span></button>)}</nav>
      {effect && <article className="proof-detail" aria-label={`${effect.business_label}的证明材料`}>
        <header><p className="editorial-eyebrow">当前材料 · {statuses[effect.material_status]}</p><h2>{effect.business_label}</h2><p className="editorial-muted">对应业务对象：{effect.resource_concept}</p></header>
        <section className="proof-source"><span className="editorial-eyebrow">已有材料</span><h3>{snapshotChanged ? '材料快照需要重新读取' : effect.source_label}</h3><p>{snapshotChanged ? '材料在读取期间发生了变化，当前来源尚未确认。请刷新查看。' : effect.source_kind === 'REGISTERED_OBSERVER' ? effect.registered_source_available === true ? '当前环境中已找到此来源。' : effect.registered_source_available === false ? '当前环境中未找到此来源。' : '当前环境尚不能确认此来源是否可用。' : effect.source_kind === 'RECORDED_OBSERVATION' ? '已保存的观察材料只说明准备情况，实际观察以每轮发布的证据为准。' : '尚无可用于说明这项业务结果的已保存材料。'}</p></section>
        {effect.source_kind === 'REGISTERED_OBSERVER' && <section><h3>来源声明了什么能力</h3><dl className="proof-capabilities"><div><dt>确认观察窗口结束<small>区分“尚未出现”和“观察已结束”。</small></dt><dd>{capability(effect.closure_supported)}</dd></div><div><dt>对应本次业务资源<small>核对观察是否属于指定的业务对象。</small></dt><dd>{capability(effect.resource_correlation_supported)}</dd></div></dl></section>}
        {!!effect.reason_codes.length && <section className="proof-limitations"><h3>当前限制</h3>{[...new Set(effect.reason_codes.map(code => reasons[code] ?? '材料与当前准备条件尚未完全对应，请结合准备页的具体缺口查看。'))].map(text => <p key={text}>{text}</p>)}</section>}
        <footer className="proof-boundary"><strong>材料与声明不等于检查结论</strong><p>这里说明已有材料。某次操作实际发生了什么，以及能够支持什么判断，请查看该轮检查记录中的证据。</p></footer>
      </article>}
    </div>}
  </EditorialPage>
}
