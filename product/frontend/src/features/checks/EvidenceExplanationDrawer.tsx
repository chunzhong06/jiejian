/* =============================================================================
 * 证据说明抽屉
 *
 * 定位
 *   结果页与现场验证共用的已发布证据解释入口。
 *
 * 职责
 *   固定展示来源、步骤、可证明与不可证明边界｜仅在事实存在时展示组件和时间
 *   ｜技术引用保持折叠｜不根据 Evidence 文本重算结论。
 * ============================================================================= */

import { Collapse, Descriptions, Drawer, Space, Tag, Typography } from 'antd'
import type { ResultEvidenceExplanationDto } from '../../api/results'
import { formatTimestamp } from '../../app/presentation'

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
  return <Drawer open={open} width="min(560px, calc(100vw - 24px))" title={title ? `证据说明 · ${title}` : '证据说明'} onClose={onClose}>
    {explanations.length === 0
      ? <Typography.Text type="secondary">当前检查项没有可展示的证据说明。</Typography.Text>
      : <Space direction="vertical" size="large" className="full-width evidence-explanation-list">
        {explanations.map((item, index) => <section className="evidence-explanation" key={`${item.label}-${index}`} aria-label={item.label}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="发生了什么">{item.label}</Descriptions.Item>
            <Descriptions.Item label="证据来源">{item.source}</Descriptions.Item>
            <Descriptions.Item label="发生步骤">{item.step}</Descriptions.Item>
            <Descriptions.Item label="可以证明"><Tag color="green">已支持</Tag>{item.proves}</Descriptions.Item>
            <Descriptions.Item label="不能证明"><Tag color="gold">边界</Tag>{item.does_not_prove}</Descriptions.Item>
            <Descriptions.Item label="为什么属于本轮">{item.relevance}</Descriptions.Item>
            {item.component && <Descriptions.Item label="责任组件">{item.component}</Descriptions.Item>}
            {item.observed_at_us !== null && <Descriptions.Item label="采集时间">{formatTimestamp(item.observed_at_us)}</Descriptions.Item>}
          </Descriptions>
          <Collapse ghost items={[{
            key: 'technical',
            label: '查看技术细节',
            children: <Descriptions column={1} size="small">
              <Descriptions.Item label="证据引用">{item.evidence_refs.length > 0 ? item.evidence_refs.join('、') : '未发布独立引用'}</Descriptions.Item>
            </Descriptions>,
          }]} />
        </section>)}
      </Space>}
  </Drawer>
}
