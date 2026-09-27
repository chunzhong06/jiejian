// 定位说明保持服务端精度；未提供端点时不按图形位置猜测范围。
import { Button } from 'antd'
import { FileSearchOutlined } from '@ant-design/icons'
import type { ActionResultStory } from '../../api/currentChecks'
import { breakpointLabels, precisionDescriptions, traceLimitations } from './tracePresentation'

export function DiagnosisSummary({ action, onEvidence }: { action: ActionResultStory; onEvidence: () => void }) {
  const breakpoint = action.breakpoint
  return <section className="diagnosis-summary" aria-label="定位依据与边界">
    <p className="editorial-eyebrow">定位依据</p>
    <h3>{breakpoint?.breakpoint_type ? breakpointLabels[breakpoint.breakpoint_type] : '当前没有可确认的断裂位置'}</h3>
    <p>{breakpoint ? precisionDescriptions[breakpoint.precision] : '没有定位结果不等于权限安全，请以本轮已发布结论和业务证据为准。'}</p>
    {breakpoint && breakpoint.precision !== 'EXACT' && <div className="diagnosis-limitations"><strong>为什么不能进一步定位</strong>{traceLimitations(action).map(text => <p key={text}>{text}</p>)}</div>}
    {!!breakpoint?.evidence_refs.length && <Button icon={<FileSearchOutlined aria-hidden="true" />} onClick={onEvidence}>{breakpoint.precision === 'RANGE' ? '查看区间的定位证据' : '查看定位证据'}</Button>}
    <p className="diagnosis-footnote">定位解释已有事实，不改变本轮结论。</p>
  </section>
}
