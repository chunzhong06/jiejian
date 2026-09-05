// 验证 AI 面板只冷读缓存，并把模型调用限制在显式点击之后。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AssistantPanel } from './AssistantPanel'

const mockAssistant = vi.hoisted(() => ({ project: vi.fn(), generateProject: vi.fn(), result: vi.fn(), generateResult: vi.fn(), generateError: vi.fn() }))
vi.mock('../api/assistant', () => ({ assistantApi: mockAssistant }))

const coldView = {
  status: 'REFRESH_NEEDED' as const,
  template_id: 'jiejian.next_step',
  template_version: '1' as const,
  subject_id: 'p1',
  state_fingerprint: 'a'.repeat(64),
  entities: [{ entity_id: 'task:check', entity_type: 'TASK', display_name: '开始权限检查', facts: [] }],
  suggestions: [],
  retry_after_us: null,
}

describe('AssistantPanel', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('项目 surface 初次渲染只冷读，点击后才生成受限建议', async () => {
    mockAssistant.project.mockResolvedValue(coldView)
    mockAssistant.generateProject.mockResolvedValue({
      ...coldView,
      status: 'READY',
      suggestions: [{ kind: 'PRIORITIZE', entity_ids: ['task:check'], explanation: '先完成当前可以执行的检查。' }],
    })

    render(<AssistantPanel projectId="p1" surface="preparation-explanation" focus={{ business_action_id: 'a1' }} title="下一步建议" actionLabel="生成 AI 建议" />)

    expect(await screen.findByText('尚未生成建议，点击按钮后才会连接模型服务。')).toBeInTheDocument()
    expect(mockAssistant.generateProject).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '生成 AI 建议' }))
    await waitFor(() => expect(mockAssistant.generateProject).toHaveBeenCalledWith('p1', 'preparation-explanation', false, { business_action_id: 'a1' }))
    expect(await screen.findByText('先完成当前可以执行的检查。')).toBeInTheDocument()
    expect(screen.getByText('开始权限检查')).toBeInTheDocument()
  })

  it('错误说明没有 GET 路径，用户点击前不调用任何模型 API', async () => {
    mockAssistant.generateError.mockResolvedValue({ ...coldView, status: 'READY', subject_id: 'error:E_TEST', entities: [], suggestions: [] })
    render(<AssistantPanel error={{ code: 'E_TEST', diagnosis: { route: '/settings/system', headline: '需要处理', short_message: '刷新状态', cleanup_warnings: [] } }} title="错误说明" actionLabel="AI 解释这个错误" />)

    expect(mockAssistant.project).not.toHaveBeenCalled()
    expect(mockAssistant.result).not.toHaveBeenCalled()
    expect(mockAssistant.generateError).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'AI 解释这个错误' }))
    await waitFor(() => expect(mockAssistant.generateError).toHaveBeenCalledWith('E_TEST', false))
  })

  it('结果 surface 先按 Run 冷读，点击后才请求结果解释', async () => {
    mockAssistant.result.mockResolvedValue({ ...coldView, template_id: 'jiejian.result_explanation', subject_id: 'run-1' })
    mockAssistant.generateResult.mockResolvedValue({ ...coldView, status: 'READY', template_id: 'jiejian.result_explanation', subject_id: 'run-1' })
    render(<AssistantPanel runId="run-1" title="这个结果的因果说明" actionLabel="AI 解读这个结果" />)

    await waitFor(() => expect(mockAssistant.result).toHaveBeenCalledWith('run-1'))
    expect(mockAssistant.generateResult).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'AI 解读这个结果' }))
    await waitFor(() => expect(mockAssistant.generateResult).toHaveBeenCalledWith('run-1', false))
  })
  it('唯一确定的事实不展示生成按钮或调用模型', async () => {
    mockAssistant.project.mockResolvedValue({ ...coldView, status: 'READY', can_generate: false })
    render(<AssistantPanel projectId="p1" surface="implementation-mapping" focus={{ business_actor_id: 'u1' }} title="候选解释" actionLabel="解释候选" />)
    await waitFor(() => expect(screen.queryByRole('button', { name: '解释候选' })).not.toBeInTheDocument())
    expect(mockAssistant.generateProject).not.toHaveBeenCalled()
  })
  it('切换焦点后丢弃旧生成结果', async () => {
    let finish!: (value: unknown) => void
    mockAssistant.project.mockResolvedValue(coldView)
    mockAssistant.generateProject.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    const { rerender } = render(<AssistantPanel projectId="p1" surface="implementation-mapping" focus={{ business_actor_id: 'u1' }} title="候选解释" actionLabel="解释候选" />)
    await waitFor(() => expect(screen.getByRole('button', { name: '解释候选' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '解释候选' }))
    rerender(<AssistantPanel projectId="p1" surface="implementation-mapping" focus={{ business_actor_id: 'u2' }} title="候选解释" actionLabel="解释候选" />)
    finish({ ...coldView, status: 'READY', suggestions: [{ kind: 'PRIORITIZE', entity_ids: [], explanation: '旧主体的建议' }] })
    await waitFor(() => expect(mockAssistant.project).toHaveBeenCalledWith('p1', 'implementation-mapping', { business_actor_id: 'u2' }))
    expect(screen.queryByText('旧主体的建议')).not.toBeInTheDocument()
  })

})
