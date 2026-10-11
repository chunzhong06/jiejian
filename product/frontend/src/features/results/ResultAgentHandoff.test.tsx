// 验证结果解读只交接指定发布记录，READ 足够，跨轮响应不得进入剪贴板。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ResultAgentHandoff } from './ResultAgentHandoff'
import { story } from '../../shared/testing/results'

const api = vi.hoisted(() => ({ story: vi.fn(), status: vi.fn() }))
vi.mock('../../api/checks/currentChecks', () => ({ currentChecksApi: api }))
vi.mock('../../api/system/mcp', async () => ({ ...await vi.importActual('../../api/system/mcp'), mcpAccessApi: api }))
const copy = vi.fn()
beforeEach(() => {
  vi.clearAllMocks()
  api.status.mockResolvedValue({ paired: true, accepting_connections: true, connection_state: 'CONNECTED', project_grants: [] })
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: copy } })
})

it('只读连接复制指定检查项及逐条取证请求', async () => {
  const value = story(); api.story.mockResolvedValue(value)
  render(<ResultAgentHandoff story={value} caseId={value.actions[0].case_id} onNavigate={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button', { name: 'Agent 协助' }))
  await screen.findByText('查看协助请求')
  fireEvent.click(screen.getByRole('button', { name: '复制协助请求' }))
  await waitFor(() => expect(copy).toHaveBeenCalledOnce())
  const request = copy.mock.calls[0][0]
  expect(request).toContain(`run_id=${value.run_id}`)
  expect(request).toContain(`case_id=${value.actions[0].case_id}`)
  expect(request).toContain('jiejian_evidence_show')
  expect(request).toContain('record_ref')
  expect(await screen.findByText('协助请求已复制。请粘贴到原来的 Agent 对话中。')).toBeInTheDocument()
})

it('同一项目返回另一轮记录时拒绝复制', async () => {
  const value = story(); api.story.mockResolvedValue({ ...value, run_id: 'another-run' })
  render(<ResultAgentHandoff story={value} onNavigate={vi.fn()}/>)
  fireEvent.click(screen.getByRole('button', { name: 'Agent 协助' }))
  expect(await screen.findByText('暂时无法核对协助内容，请重新读取。')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '复制协助请求' })).toBeDisabled()
  expect(copy).not.toHaveBeenCalled()
})
