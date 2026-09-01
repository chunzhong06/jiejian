// 测试模块汇总条件、运行和结果；三个入口共享后端事实，但不组成强制步骤条。

import { Button, Tag, Typography } from 'antd'
import type { ProductStatusDto, ProjectReadinessDto } from '../../api/projects'
import type { RunDto } from '../../api/runs'
import { formatTimestamp, lifecycleLabel, verdictLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'

export function TestingPage({ status, readiness, runs, latestResult = status.latest_result, onNavigate }: {
  status: ProductStatusDto
  readiness: ProjectReadinessDto
  runs: RunDto[]
  latestResult?: ProductStatusDto['latest_result']
  onNavigate: (path: '/preparation' | '/validation' | '/results') => void
}) {
  const area = status.areas.find((item) => item.key === 'tests')
  const latestRun = runs[0]
  const activeRun = readiness.active_tasks.find((item) => item.kind === 'RUN')
  const preparationReady = readiness.preparation?.ready === true

  return <div className="testing-page">
    <PageTaskHeader
      title="测试"
      description="围绕同一份权限规则准备真实条件、运行检查并查看结果；可以直接进入任一区域。"
      status={area?.status_label ?? '正在读取测试状态'}
    />

    <section className="testing-overview" aria-labelledby="testing-overview-title">
      <Typography.Text className="workbench-eyebrow">当前测试判断</Typography.Text>
      <Typography.Title id="testing-overview-title" level={2}>{activeRun
        ? '界鉴正在检查当前代码版本的真实业务结果。'
        : readiness.current_scope_runnable
          ? '当前权限规则和测试条件已经可以开始检查。'
          : latestResult
            ? latestResult.headline
            : '还需要补齐测试条件，才能形成可信结论。'}</Typography.Title>
      <Typography.Paragraph type="secondary">测试模块不会把准备、运行和结果锁成一次性向导；每次 Agent 变化后，相关状态会在这里重新汇总。</Typography.Paragraph>
    </section>

    <section className="testing-area-panel" aria-label="测试模块三个区域">
      <div className="testing-area-grid">
        <article>
          <div><Typography.Text className="workbench-secondary-label">测试条件</Typography.Text><Tag color={preparationReady ? 'green' : 'gold'}>{preparationReady ? '当前可用' : '需要补充'}</Tag></div>
          <Typography.Title level={3}>{preparationReady ? '身份、流程与观察条件已准备' : `仍有 ${readiness.remaining_gap_count} 项条件需要处理`}</Typography.Title>
          <Typography.Paragraph type="secondary">核对测试账号、业务流程、真实结果观察和安全恢复。</Typography.Paragraph>
          <Button type="link" onClick={() => onNavigate('/preparation')}>管理测试条件</Button>
        </article>
        <article>
          <div><Typography.Text className="workbench-secondary-label">运行检查</Typography.Text><Tag color={activeRun ? 'blue' : readiness.current_scope_runnable ? 'green' : 'default'}>{activeRun ? '正在运行' : readiness.current_scope_runnable ? '可以开始' : '等待条件'}</Tag></div>
          <Typography.Title level={3}>{activeRun ? '当前检查正在形成事实' : '核对范围并发起独立检查'}</Typography.Title>
          <Typography.Paragraph type="secondary">先验证合法路径，再尝试不应允许的操作，并观察真实业务后果。</Typography.Paragraph>
          <Button type="link" onClick={() => onNavigate('/validation')}>{activeRun ? '查看检查进度' : '进入运行检查'}</Button>
        </article>
        <article>
          <div><Typography.Text className="workbench-secondary-label">结果与历史</Typography.Text>{latestResult && <Tag>{verdictLabel(latestResult.verdict)}</Tag>}</div>
          <Typography.Title level={3}>{latestResult?.headline ?? '当前版本还没有检查结果'}</Typography.Title>
          <Typography.Paragraph type="secondary">{latestRun ? `${lifecycleLabel(latestRun.lifecycle)} · ${formatTimestamp(latestRun.created_at_us ?? latestRun.created_at)}` : '检查完成后，这里会保留结论、证据和历次变化。'}</Typography.Paragraph>
          <Button type="link" onClick={() => onNavigate('/results')}>查看结果与历史</Button>
        </article>
      </div>
    </section>
  </div>
}
