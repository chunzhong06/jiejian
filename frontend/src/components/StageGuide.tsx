import { Button, Card, Space, Typography } from 'antd'

type StageGuideProps = {
  stage: string
  what: string
  why: string
  missing?: string
  next: string
  onNext?: () => void
  nextLabel?: string
  nextDisabled?: boolean
}

export function StageGuide({ stage, what, why, missing = '尚未确认', next, onNext, nextLabel = '下一步', nextDisabled }: StageGuideProps) {
  return <Card className="stage-guide" size="small" title={`${stage}：现在要做什么`}>
    <div className="stage-guide-grid">
      <div><Typography.Text strong>正在做什么</Typography.Text><Typography.Paragraph>{what}</Typography.Paragraph></div>
      <div><Typography.Text strong>为什么需要</Typography.Text><Typography.Paragraph>{why}</Typography.Paragraph></div>
      <div><Typography.Text strong>还缺什么</Typography.Text><Typography.Paragraph>{missing || '尚未确认'}</Typography.Paragraph></div>
      <div><Typography.Text strong>下一步</Typography.Text><Typography.Paragraph>{next}</Typography.Paragraph></div>
    </div>
    {onNext && <Space><Button onClick={onNext} disabled={nextDisabled}>{nextLabel}</Button></Space>}
  </Card>
}
