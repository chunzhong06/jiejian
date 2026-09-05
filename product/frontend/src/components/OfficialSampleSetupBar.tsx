// 官方样例工作台控制器：把当前版本、最近结果和唯一主操作放在一起，按钮本身不生成安全结论。

import { Button, Modal, Space, Tag, Typography } from 'antd'
import { useState } from 'react'
import type { OfficialExperienceDto, OfficialScenarioVersion } from '../api/experience'
import type { ProductStatusDto } from '../api/deferredChecks'
import type { RunDto } from '../api/runs'
import { verdictLabel } from '../app/presentation'

const versionCopy: Record<OfficialScenarioVersion, { label: string; tone: string; action: string }> = {
  VULNERABLE: { label: '问题版', tone: 'red', action: '检查问题版' },
  EVIDENCE_LIMITED: { label: '证据受限版', tone: 'gold', action: '检查证据受限版' },
  FIXED: { label: '修复版', tone: 'green', action: '复验修复版' },
}

export function OfficialSampleSetupBar({
  status,
  experience,
  busy,
  sourceBlockRunId,
  latestRun,
  onPrepare,
  onRun,
  onSwitchVersion,
  onOpenVerification,
  onOpenChanges,
  onOpenTests,
}: {
  status: ProductStatusDto | null
  experience: OfficialExperienceDto | null
  busy: boolean
  sourceBlockRunId?: string
  latestRun?: RunDto
  onPrepare: () => void
  onRun: () => void
  onSwitchVersion: (version: OfficialScenarioVersion, sourceRunId?: string) => void
  onOpenVerification?: () => void
  onOpenChanges?: () => void
  onOpenTests?: () => void
}) {
  const [targetVersion, setTargetVersion] = useState<OfficialScenarioVersion | null>(null)
  if (!status?.project || !experience?.active || status.project.project_id !== experience.project_id) return null
  const version = experience.scenario_version ?? 'VULNERABLE'
  const copy = versionCopy[version]
  const changedAt = experience.scenario_changed_at_us
  const latestResult = status.latest_result
  const latestRunAt = latestRun?.created_at_us ?? latestRun?.created_at
  const currentVersionVerified = Boolean(
    latestResult
    && latestRun?.run_id === latestResult.run_id
    && latestRun.result_integrity === 'VERIFIED'
    && typeof changedAt === 'number'
    && typeof latestRunAt === 'number'
    && latestRunAt >= changedAt,
  )
  const confirmSwitch = () => {
    if (!targetVersion) return
    onSwitchVersion(targetVersion, targetVersion === 'FIXED' ? sourceBlockRunId : undefined)
    setTargetVersion(null)
  }

  return <aside className={`official-sample-setup-bar is-${version.toLowerCase()}`} aria-label="官方样例状态">
    <div className="official-sample-heading">
      <div className="official-sample-setup-copy">
        <Space wrap><Tag color="blue">官方样例</Tag><Tag color={copy.tone}>{copy.label}</Tag></Space>
        <Typography.Title level={3}>协作空间权限实验</Typography.Title>
        <Typography.Text type="secondary">Bob 可以查看日常资料，但不能导出包含申报书、预算和评审材料的完整项目交付包。</Typography.Text>
      </div>
      <div className="official-sample-state">
        <Typography.Text className="workbench-secondary-label">当前版本</Typography.Text>
        <Tag color={currentVersionVerified ? 'green' : 'gold'}>{currentVersionVerified ? '已经独立检查' : '尚未验证'}</Tag>
      </div>
    </div>
    <div className="official-sample-summary">
      <section className="official-sample-current">
        <Typography.Text className="workbench-secondary-label">系统当前真实状态</Typography.Text>
        <Typography.Title level={3}>{experience.scenario_prepared ? scenarioHeadline(version) : '样例已经启动，等待应用公开设计合同'}</Typography.Title>
        <Typography.Paragraph type="secondary">{experience.scenario_prepared
          ? scenarioDescription(version)
          : '一键配置会建立角色、业务动作、测试账号、两条流程和三条公开权限规则；不会预先生成检查结论。'}</Typography.Paragraph>
      </section>
      <section className="official-sample-result">
        <Typography.Text className="workbench-secondary-label">与当前版本对应的结果</Typography.Text>
        {currentVersionVerified && latestResult ? <>
          <Tag color={latestResult.verdict === 'PASS' ? 'green' : latestResult.verdict === 'BLOCK' ? 'red' : 'gold'}>{verdictLabel(latestResult.verdict)}</Tag>
          <Typography.Title level={3}>{latestResult.headline}</Typography.Title>
          <Typography.Paragraph type="secondary">{latestResult.scope_statement}</Typography.Paragraph>
        </> : <>
          <Typography.Title level={3}>当前版本还没有可信结论</Typography.Title>
          <Typography.Paragraph type="secondary">{latestResult ? '最近结果属于切换前的版本；必须重新运行同一权限实验。' : '运行真实检查后，这里才会显示本版本结论。'}</Typography.Paragraph>
        </>}
      </section>
    </div>
    <div className="official-sample-setup-actions">
      <div className="official-sample-primary-actions">
        {!experience.scenario_prepared
          ? <Button type="primary" loading={busy} onClick={onPrepare}>一键应用样例配置</Button>
          : <Button type="primary" disabled={busy} onClick={onRun}>{copy.action}</Button>}
        {currentVersionVerified && onOpenVerification && <Button onClick={onOpenVerification}>查看当前结果</Button>}
        {experience.scenario_prepared && onOpenChanges && <Button type="link" onClick={onOpenChanges}>查看代码变化</Button>}
        {experience.scenario_prepared && onOpenTests && <Button type="link" onClick={onOpenTests}>查看测试范围</Button>}
      </div>
      {experience.scenario_prepared && <div className="official-sample-version-actions" aria-label="切换样例实验条件">
        <Typography.Text type="secondary">切换实验：</Typography.Text>
        <Button disabled={busy || version === 'VULNERABLE'} onClick={() => setTargetVersion('VULNERABLE')}>问题版</Button>
        <Button disabled={busy || !sourceBlockRunId || version === 'FIXED'} onClick={() => setTargetVersion('FIXED')}>交给 Agent 修复</Button>
        <Button disabled={busy || version === 'EVIDENCE_LIMITED'} onClick={() => setTargetVersion('EVIDENCE_LIMITED')}>证据受限实验</Button>
      </div>}
    </div>
    <Modal open={targetVersion !== null} title={targetVersion ? switchTitle(targetVersion) : ''} okText={targetVersion === 'FIXED' ? '生成修改并切换' : '确认切换'} cancelText="取消" confirmLoading={busy} onCancel={() => setTargetVersion(null)} onOk={confirmSwitch}>
      {targetVersion && <SwitchExplanation version={targetVersion} sourceBlockRunId={sourceBlockRunId} />}
    </Modal>
  </aside>
}

function SwitchExplanation({ version, sourceBlockRunId }: { version: OfficialScenarioVersion; sourceBlockRunId?: string }) {
  if (version === 'VULNERABLE') return <>
    <Typography.Paragraph>模拟 Vibe Coding Agent 为缩短导出等待，把后台任务创建提前到了权限判断之前。</Typography.Paragraph>
    <Typography.Paragraph strong>切换只恢复问题代码和完整观察能力；需要重新发起检查后，界鉴才会形成结论。</Typography.Paragraph>
  </>
  if (version === 'EVIDENCE_LIMITED') return <>
    <Typography.Paragraph>恢复与问题版相同的导出实现，并模拟两条关键业务结果观察暂时不可用：只读业务状态与最终 ZIP。界鉴仍会执行同一权限实验，但无法独立确认最终业务后果。</Typography.Paragraph>
    <Typography.Paragraph strong>代码问题可能仍然存在；证据不足时只能暂时不下结论，不能解释为安全。</Typography.Paragraph>
  </>
  return <>
    <Typography.Paragraph>这个按钮模拟 Codex 通过 MCP 读取界鉴对检查记录 {sourceBlockRunId ?? '尚未形成'} 发布的修复合同：</Typography.Paragraph>
    <ul><li>必须消失：Bob 的导出任务、队列消息和 ZIP 文件。</li><li>必须保留：Alice 仍能生成完整项目交付包。</li><li>不能改变：Bob 仍可查看日常协作资料，原权限规则和观察标准保持不变。</li></ul>
    <Typography.Paragraph>Codex 将修改 <code>authorization_policy.py</code>，把权限判断移动到后台任务创建之前；界鉴随后读取真实源码差异并在“变化”中登记。</Typography.Paragraph>
    <Typography.Paragraph strong>切换完成仍不代表修复成立，必须按原考题重新检查。</Typography.Paragraph>
  </>
}

function scenarioHeadline(version: OfficialScenarioVersion) {
  if (version === 'VULNERABLE') return 'Agent 修改已经进入应用，等待验证是否破坏既有权限'
  if (version === 'EVIDENCE_LIMITED') return '关键业务结果暂时不可读取，等待验证证据边界'
  return 'Agent 已按界鉴修复合同修改代码，等待原考题复验'
}

function scenarioDescription(version: OfficialScenarioVersion) {
  if (version === 'VULNERABLE') return '页面可能返回 403，但后台任务、消息和 ZIP 是否仍产生，需要真实检查确认。'
  if (version === 'EVIDENCE_LIMITED') return '同一权限实验将保留执行事实，但只读业务状态与最终 ZIP 都无法独立确认。'
  return '权限判断已移动到副作用之前；Alice 导出与 Bob 查看资料仍需一起回归。'
}

function switchTitle(version: OfficialScenarioVersion) {
  if (version === 'VULNERABLE') return '进入 Agent 写错的问题版？'
  if (version === 'EVIDENCE_LIMITED') return '进入证据受限实验？'
  return '把界鉴修复意见交给 Agent？'
}
