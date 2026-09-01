/* =============================================================================
 * 证据说明抽屉
 *
 * 定位
 *   结果页与现场验证共用的已发布证据解释入口。
 *
 * 职责
 *   先展示真实核对位置、观察事实和支持范围｜把观察者、采集来源与技术引用保持折叠
 *   ｜整轮集中说明证据边界｜不根据 Evidence 文本重算结论。
 * ============================================================================= */

import { Collapse, Descriptions, Drawer, Space, Tag, Typography } from 'antd'
import type { ResultEvidenceExplanationDto } from '../../api/results'
import { formatTimestamp } from '../../app/presentation'

function observationPhaseLabel(value: ResultEvidenceExplanationDto['observation_phase']) {
  return ({ BASELINE: '操作前基线', BEFORE: '执行前', AFTER: '执行后', EVENTUAL: '最终闭合时点' } as const)[value ?? 'BASELINE']
}

export function EvidenceExplanationDrawer({
  open,
  title,
  explanations,
  onClose,
}: {
  open: boolean
  title?: string
  explanations: ResultEvidenceExplanationDto[]
  onClose: () => void
}) {
  const boundaries = explanations.map((item) => ({ source: item.source, statement: item.does_not_prove }))
  return <Drawer open={open} width="min(680px, calc(100vw - 24px))" title={title ? `证据说明 · ${title}` : '证据说明'} onClose={onClose}>
    {explanations.length === 0
      ? <Typography.Text type="secondary">当前检查项没有可展示的证据说明。</Typography.Text>
      : <Space direction="vertical" size="large" className="full-width evidence-explanation-list">
        <Typography.Paragraph type="secondary" className="evidence-explanation-intro">每项内容都来自本次检查已经发布的事实。先核对读取位置和观察内容，再看它支持哪一部分结论；单项边界统一放在列表末尾。</Typography.Paragraph>
        {explanations.map((item, index) => <section className="evidence-explanation" key={`${item.label}-${index}`} aria-label={item.label}>
          <div className="evidence-explanation-location"><Typography.Text className="evidence-explanation-label">在哪里看到</Typography.Text><Typography.Text strong>{item.location ?? `${item.source}的本轮已发布记录`}</Typography.Text><Typography.Text type="secondary">证据来源：{item.source}</Typography.Text></div>
          <div className="evidence-explanation-fact"><Typography.Text className="evidence-explanation-label">看到什么</Typography.Text><Typography.Paragraph>{item.label}</Typography.Paragraph></div>
          <div className="evidence-explanation-conclusion"><Typography.Text className="evidence-explanation-label">因此支持</Typography.Text><Space align="start"><Tag color="green">已支持</Tag><Typography.Paragraph>{item.proves}</Typography.Paragraph></Space></div>
          <Collapse ghost items={[{
            key: 'technical',
            label: '查看观察者与原始引用',
            children: <Descriptions column={1} size="small">
              {item.observer_id && <Descriptions.Item label="具体观察者">{item.observer_id}</Descriptions.Item>}
              {item.component && <Descriptions.Item label="责任组件">{item.component}</Descriptions.Item>}
              {item.observation_phase && <Descriptions.Item label="观察时点">{observationPhaseLabel(item.observation_phase)}</Descriptions.Item>}
              {item.provenance_type && <Descriptions.Item label="采集来源">{item.provenance_type}</Descriptions.Item>}
              {item.adapter_version && <Descriptions.Item label="适配器版本">{item.adapter_version}</Descriptions.Item>}
              <Descriptions.Item label="核对方式">{item.step}</Descriptions.Item>
              <Descriptions.Item label="为什么属于本轮">{item.relevance}</Descriptions.Item>
              {item.observed_at_us !== null && <Descriptions.Item label="采集时间">{formatTimestamp(item.observed_at_us)}</Descriptions.Item>}
              {item.source_sha256 && <Descriptions.Item label="源数据摘要"><Typography.Text code copyable>{item.source_sha256}</Typography.Text></Descriptions.Item>}
              <Descriptions.Item label="证据引用">{item.evidence_refs.length > 0 ? item.evidence_refs.join('、') : '未发布独立引用'}</Descriptions.Item>
            </Descriptions>,
          }]} />
        </section>)}
        <Collapse className="evidence-boundary-collapse" items={[{
          key: 'boundaries',
          label: `本轮证据边界（${boundaries.length} 条）`,
          children: <ul>{boundaries.map((item, index) => <li key={`${item.source}-${index}`}><Typography.Text strong>{item.source}：</Typography.Text>{item.statement}</li>)}</ul>,
        }]} />
      </Space>}
  </Drawer>
}
