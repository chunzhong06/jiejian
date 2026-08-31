// 验证官方示例状态条只投影 ProductStatus 待办和正式结果，不保存独立步骤。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { OfficialSampleSetupBar } from './OfficialSampleSetupBar'

const experience = {
  available: true,
  display_name: '协作空间',
  unavailable_reason: null,
  active: true,
  experience_id: `exp_${'a'.repeat(32)}`,
  experience_mode: 'GUIDED' as const,
  project_id: 'p1',
  origin: 'http://127.0.0.1:12345',
  identities_ready: false,
  authorization_order: 'ENQUEUE_BEFORE_AUTHORIZE' as const,
  blob_observation: 'AVAILABLE' as const,
  repair_change_id: null,
}

function status(label: string, route: string, withResult = false) {
  return {
    project: { project_id: 'p1', name: '协作空间', status: 'DRAFT', target_type: 'WEB' as const },
    readiness: null,
    areas: [],
    attention_items: [{ key: 'current', label, description: '继续处理当前正式产品待办', route, tone: 'ACTION' }],
    latest_change: null,
    latest_result: withResult ? { run_id: 'run-1', verdict: 'BLOCK', headline: '发现权限问题', scope_statement: '当前范围已检查。', verified_change_id: null } : null,
  }
}

describe('OfficialSampleSetupBar', () => {
  it('展示正式工作区当前待办，不生成第二套示例步骤', () => {
    render(<OfficialSampleSetupBar status={status('确认新增权限规则', '/permissions') as never} experience={{ ...experience, identities_ready: true }} preparingIdentities={false} onPrepareIdentities={vi.fn()} />)
    expect(screen.getByText('官方示例运行中')).toBeInTheDocument()
    expect(screen.getByText('确认新增权限规则')).toBeInTheDocument()
    expect(screen.getByText('继续处理当前正式产品待办')).toBeInTheDocument()
    expect(screen.queryByText(/\d+\/\d+/)).not.toBeInTheDocument()
  })

  it('官方测试账号未准备时提供明确动作', () => {
    const prepare = vi.fn()
    render(<OfficialSampleSetupBar status={status('完善测试准备', '/preparation') as never} experience={experience} preparingIdentities={false} onPrepareIdentities={prepare} />)
    fireEvent.click(screen.getByRole('button', { name: '准备官方测试账号' }))
    expect(prepare).toHaveBeenCalledOnce()
  })

  it('未启动示例或当前项目不匹配时不显示状态条', () => {
    const { rerender } = render(<OfficialSampleSetupBar status={status('完善测试准备', '/preparation') as never} experience={{ ...experience, active: false }} preparingIdentities={false} onPrepareIdentities={vi.fn()} />)
    expect(screen.queryByLabelText('官方示例状态')).not.toBeInTheDocument()
    rerender(<OfficialSampleSetupBar status={{ ...status('完善测试准备', '/preparation'), project: { project_id: 'p2', name: '其他应用', status: 'DRAFT', target_type: 'WEB' } } as never} experience={experience} preparingIdentities={false} onPrepareIdentities={vi.fn()} />)
    expect(screen.queryByLabelText('官方示例状态')).not.toBeInTheDocument()
  })

  it('存在正式结果时提供现场验证入口', () => {
    const openVerification = vi.fn()
    render(<OfficialSampleSetupBar status={status('查看检查结果', '/results', true) as never} experience={{ ...experience, identities_ready: true }} preparingIdentities={false} onPrepareIdentities={vi.fn()} onOpenVerification={openVerification} />)
    fireEvent.click(screen.getByRole('button', { name: '查看现场验证' }))
    expect(openVerification).toHaveBeenCalledOnce()
  })
})
