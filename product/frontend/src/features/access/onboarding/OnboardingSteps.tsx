/* 首次接入步骤视图：展示识别结果与四步表单，保存规则留在 Wizard 编排层。 */

import { Alert, Button, Card, Checkbox, Descriptions, Form, Input, List, Progress, Space, Steps, Typography } from 'antd'
import type { DiscoveryResult, OnboardingSession } from '../../../api/onboarding'

export type OnboardingFields = {
  targetAddress: string
  primaryName: string
  comparisonName: string
  primaryResource: string
  comparisonResource: string
  primaryPassword: string
  comparisonPassword: string
  readPath: string
  recoveryPath: string
}

export function OnboardingSteps({ session, discovery, path, projectName, step, loading, error, chooserMessage, selectedCandidateSource, fields, confirmations, missing, submitted, onProjectNameChange, onFieldChange, onConfirmationsChange, onSelectedCandidateSourceChange, onCopyCandidate, onRetryDiscovery, onCloseError, onCloseMessage, onBack, onNext, onQuickCheck }: {
  session: OnboardingSession
  discovery: DiscoveryResult | null
  path: string
  projectName: string
  step: number
  loading: boolean
  error: string
  chooserMessage: string
  selectedCandidateSource: string
  fields: OnboardingFields
  confirmations: OnboardingSession['confirmations']
  missing: string[]
  submitted: boolean
  onProjectNameChange: (value: string) => void
  onFieldChange: <K extends keyof OnboardingFields>(key: K, value: OnboardingFields[K]) => void
  onConfirmationsChange: (value: OnboardingSession['confirmations']) => void
  onSelectedCandidateSourceChange: (value: string) => void
  onCopyCandidate: (command: string) => void
  onRetryDiscovery: () => void
  onCloseError: () => void
  onCloseMessage: () => void
  onBack: () => void
  onNext: () => void
  onQuickCheck: () => void
}) {
  const candidateItems = discovery?.start_candidates ?? []
  const hintItems = [...(discovery?.config_hints ?? []), ...(discovery?.interface_hints ?? []), ...(discovery?.auth_hints ?? [])]
  return <Card className="onboarding-wizard" bordered={false}><Space direction="vertical" size="large" className="full-width">
    <div className="onboarding-heading"><Typography.Title level={3}>准备一次快速检查</Typography.Title><Typography.Text type="secondary">只读取少量配置；启动命令由你决定，界鉴不会替你执行。</Typography.Text></div>
    {submitted && <Alert type="success" showIcon message="检查已提交" description="这次新手检查已进入后台，当前会话不能再修改。请到开始检查查看真实状态。" />}
    {error && <Alert type="error" showIcon message={error} closable onClose={onCloseError} />}
    {chooserMessage && <Alert type="info" showIcon message={chooserMessage} closable onClose={onCloseMessage} action={chooserMessage.includes('暂时无法重新识别') ? <Button size="small" onClick={onRetryDiscovery} loading={loading}>重新识别</Button> : undefined} />}
    <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={[{ key: 'path', label: '应用文件夹', children: path || session.source_path }, { key: 'project', label: '项目名称', children: <Input aria-label="项目名称" value={projectName} disabled={submitted || loading} onChange={(event) => onProjectNameChange(event.target.value)} /> }]} />
    {discovery && <Card size="small" title="识别结果" className="onboarding-discovery"><Space direction="vertical" className="full-width"><Typography.Text>项目类型：{discovery.detected_types.length ? discovery.detected_types.join('、') : '暂未识别'}</Typography.Text>{candidateItems.length > 0 && <List size="small" header="可能的启动方式（只可复制，不会执行）" dataSource={candidateItems} renderItem={(candidate) => <List.Item actions={[<Button key="select" disabled={submitted || loading} type={selectedCandidateSource === candidate.source ? 'primary' : 'link'} onClick={() => onSelectedCandidateSourceChange(candidate.source)}>{selectedCandidateSource === candidate.source ? '已记录来源' : '记录来源'}</Button>, <Button key="copy" disabled={submitted || loading} type="link" onClick={() => onCopyCandidate(candidate.command)}>复制</Button>]}><Space direction="vertical" size={0}><Typography.Text>{candidate.label}</Typography.Text><Typography.Text code>{candidate.command}</Typography.Text><Typography.Text type="secondary">{candidate.safety_note}</Typography.Text></Space></List.Item>} />}{hintItems.length > 0 && <List size="small" header="配置、API 和认证线索" dataSource={hintItems} renderItem={(hint) => <List.Item><Typography.Text>{hint.detail}（来源：{hint.source}）</Typography.Text></List.Item>} />}{discovery.warnings.map((warning) => <Alert key={`${warning.code}-${warning.message}`} type="warning" showIcon message={warning.message} />)}</Space></Card>}
    <Steps current={step} responsive items={[{ title: '启动应用' }, { title: '允许访问的地址' }, { title: '两个测试账号' }, { title: '检查与恢复' }]} />
    {step === 0 && <Card title="应用怎样启动" size="small"><Typography.Paragraph>用途：告诉界鉴应用已经由你启动。示例：复制候选命令，在本机自行启动后勾选确认。</Typography.Paragraph><Checkbox disabled={submitted || loading} checked={confirmations.app_started} onChange={(event) => onConfirmationsChange({ ...confirmations, app_started: event.target.checked })}>应用已经在本机运行</Checkbox><Typography.Paragraph type="secondary">安全影响：候选命令只供复制，界鉴不会运行脚本或安装依赖。</Typography.Paragraph></Card>}
    {step === 1 && <Card title="允许访问哪些地址" size="small"><Typography.Paragraph>快速检查只访问明确授权的本机回环地址，不扫描公网。</Typography.Paragraph><Form layout="vertical"><Form.Item label="目标地址" required extra="示例：http://127.0.0.1:8765"><Input aria-label="目标地址" disabled={submitted || loading} value={fields.targetAddress} onChange={(event) => onFieldChange('targetAddress', event.target.value)} placeholder="http://127.0.0.1:8765" /></Form.Item><Checkbox disabled={submitted || loading} checked={confirmations.target_authorized} onChange={(event) => onConfirmationsChange({ ...confirmations, target_authorized: event.target.checked })}>我已授权界鉴只访问这个回环地址</Checkbox></Form></Card>}
    {step === 2 && <Card title="测试账号有哪些" size="small"><Typography.Paragraph>用途：用两个身份互换资源，检查权限边界。密码只在本次提交时使用，成功后立即清空；刷新后若已配置，可以留空。</Typography.Paragraph><div className="onboarding-form-grid"><Form.Item label="主账号显示名" required><Input aria-label="主账号显示名" disabled={submitted || loading} value={fields.primaryName} onChange={(event) => onFieldChange('primaryName', event.target.value)} /></Form.Item><Form.Item label="对照账号显示名" required><Input aria-label="对照账号显示名" disabled={submitted || loading} value={fields.comparisonName} onChange={(event) => onFieldChange('comparisonName', event.target.value)} /></Form.Item><Form.Item label="主账号拥有的资源标识" required><Input aria-label="主账号拥有的资源标识" disabled={submitted || loading} value={fields.primaryResource} onChange={(event) => onFieldChange('primaryResource', event.target.value)} placeholder="owner-resource" /></Form.Item><Form.Item label="对照账号拥有的资源标识" required><Input aria-label="对照账号拥有的资源标识" disabled={submitted || loading} value={fields.comparisonResource} onChange={(event) => onFieldChange('comparisonResource', event.target.value)} placeholder="attacker-resource" /></Form.Item><Form.Item label="主账号密码"><Input.Password aria-label="主账号密码" disabled={submitted || loading} autoComplete="new-password" value={fields.primaryPassword} onChange={(event) => onFieldChange('primaryPassword', event.target.value)} /></Form.Item><Form.Item label="对照账号密码"><Input.Password aria-label="对照账号密码" disabled={submitted || loading} autoComplete="new-password" value={fields.comparisonPassword} onChange={(event) => onFieldChange('comparisonPassword', event.target.value)} /></Form.Item></div></Card>}
    {step === 3 && <Card title="检查后怎样恢复数据" size="small"><Typography.Paragraph>界鉴会在每个用例后调用恢复接口，避免演示或测试数据互相影响。</Typography.Paragraph><div className="onboarding-form-grid"><Form.Item label="只读路径" required extra="示例：/resources/{resource_id}"><Input aria-label="只读路径" disabled={submitted || loading} value={fields.readPath} onChange={(event) => onFieldChange('readPath', event.target.value)} /></Form.Item><Form.Item label="恢复路径" required extra="示例：/reset"><Input aria-label="恢复路径" disabled={submitted || loading} value={fields.recoveryPath} onChange={(event) => onFieldChange('recoveryPath', event.target.value)} /></Form.Item></div><Checkbox disabled={submitted || loading} checked={confirmations.recovery_confirmed} onChange={(event) => onConfirmationsChange({ ...confirmations, recovery_confirmed: event.target.checked })}>我已确认恢复方式</Checkbox><br /><Checkbox disabled={submitted || loading} checked={confirmations.dangerous_inference_confirmed} onChange={(event) => onConfirmationsChange({ ...confirmations, dangerous_inference_confirmed: event.target.checked })}>系统将按我确认的归属和路径生成检查</Checkbox></Card>}
    {missing.length > 0 && <Alert type="warning" showIcon message="还缺什么" description={missing.join('、')} />}
    <Space wrap>{step > 0 && <Button onClick={onBack} disabled={submitted || loading}>上一步</Button>}{step < 3 && <Button type="primary" onClick={onNext} loading={loading} disabled={submitted}>保存并继续</Button>}{step === 3 && <Button type="primary" onClick={onQuickCheck} loading={loading} disabled={submitted}>开始快速检查</Button>}</Space>
    <Progress percent={Math.round(((step + 1) / 4) * 100)} showInfo={false} />
  </Space></Card>
}
