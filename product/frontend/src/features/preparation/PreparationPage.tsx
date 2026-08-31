// 测试准备页只展示后端实时投影，并通过一个主操作推进下一项准备工作。

import { useState } from 'react'
import { Alert, Button, Card, Tag, Typography } from 'antd'
import type {
  PreparationItemStatus,
  ProjectReadinessDto,
} from '../../api/projects'
import { PageTaskHeader } from '../../components/PageTaskHeader'

const statusPresentation: Record<PreparationItemStatus, { label: string; color: string }> = {
  READY: { label: '当前可用', color: 'green' },
  AUTO: { label: '可以自动准备', color: 'blue' },
  USER: { label: '需要你处理', color: 'orange' },
  BLOCKED: { label: '暂时受阻', color: 'red' },
}

export function PreparationPage({ readiness, onPrepareSafe, onNavigate }: {
  readiness: ProjectReadinessDto
  onPrepareSafe: () => Promise<void>
  onNavigate: (path: string) => void
}) {
  const [preparing, setPreparing] = useState(false)
  const preparation = readiness.preparation
  const readyCount = preparation?.items.filter((item) => item.status === 'READY').length ?? 0
  const itemCount = preparation?.items.length ?? 0
  const nextBlocker = preparation?.external_blockers.find(
    (item) => item.key === preparation.next_item_key,
  )
  const nextItem = preparation?.items.find((item) => item.key === preparation.next_item_key)
  const canContinue = Boolean(
    preparation?.ready
    || nextItem?.status === 'AUTO'
    || preparation?.next_path,
  )

  const continuePreparation = async () => {
    if (!preparation) return
    if (preparation.ready) {
      onNavigate('/validation')
      return
    }
    if (nextItem?.status === 'AUTO') {
      setPreparing(true)
      try {
        await onPrepareSafe()
      } finally {
        setPreparing(false)
      }
      return
    }
    if (preparation.next_path) onNavigate(preparation.next_path)
  }

  return <div className="preparation-page">
    <PageTaskHeader
      title="测试准备"
      description="界鉴会自动复用已经准备好的内容，并只把真正需要你登录、录制或确认的部分交给你。"
      status={preparation?.ready ? '全部准备完成' : `${readyCount}/${itemCount} 项可用`}
    />
    {nextBlocker && <Alert
      type="warning"
      showIcon
      message={nextBlocker.label}
      description={`${nextBlocker.description} ${nextBlocker.next_label}`}
    />}
    {!preparation && <Alert
      type="info"
      showIcon
      message="正在形成测试准备清单"
      description="刷新当前应用状态后，界鉴会列出需要复用、自动准备或由你完成的内容。"
    />}
    {preparation && <Card className="preparation-list-card">
      <div className="preparation-list" aria-label="测试准备清单">
        {preparation.items.map((item) => {
          const presentation = statusPresentation[item.status]
          return <div className="preparation-list-item" data-status={item.status} key={item.key}>
            <div className="preparation-list-copy">
              <Typography.Text strong>{item.label}</Typography.Text>
              <Typography.Text type="secondary">{item.description}</Typography.Text>
              {item.status !== 'READY' && item.next_label && <Typography.Text type="secondary">
                建议：{item.next_label}
              </Typography.Text>}
            </div>
            <Tag color={presentation.color}>{presentation.label}</Tag>
          </div>
        })}
      </div>
    </Card>}
    <div className="preparation-footer">
      <Button
        type="primary"
        loading={preparing}
        disabled={!canContinue}
        onClick={() => { void continuePreparation() }}
      >
        {preparation?.ready ? '前往验证运行' : preparation?.next_label ?? '继续准备'}
      </Button>
    </div>
  </div>
}
