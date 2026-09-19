// 候选草稿在回执不明、版本变化和页面卸载时保持写入边界。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { CandidateReview } from './CandidateReview'
import type { ApplicationUnderstandingDto } from '../../api/projects'

const api = vi.hoisted(() => ({ decideCandidates: vi.fn(), understanding: vi.fn() }))
vi.mock('../../api/projects', () => ({ projectsApi: api }))
const value = {
  project_id: 'p1', revision: 3, role_candidates: [
    { candidate_id: `role_${'1'.repeat(32)}`, display_name: '成员', confidence: 'HIGH', decision: 'PROPOSED', origin: 'DETECTED', stale: false, evidence: [] },
    { candidate_id: `role_${'2'.repeat(32)}`, display_name: '可能的访客', confidence: 'LOW', decision: 'PROPOSED', origin: 'DETECTED', stale: false, evidence: [] },
  ], action_candidates: [],
} as unknown as ApplicationUnderstandingDto
beforeEach(() => vi.resetAllMocks())
function begin() { fireEvent.click(screen.getByRole('button', { name: '审阅本次选择' })); fireEvent.click(screen.getByRole('button', { name: '确认这些业务信息' })) }

it('低置信项不默认纳入；排除明确列入摘要且审阅之前不写入', () => {
  render(<CandidateReview value={value} onApplied={vi.fn()} manual={null} staleReview={null}/>)
  expect(screen.getByRole('checkbox', { name: '纳入可能的访客' })).not.toBeChecked()
  fireEvent.click(screen.getByRole('checkbox', { name: '纳入成员' }))
  fireEvent.click(screen.getByRole('button', { name: '审阅本次选择' }))
  expect(screen.getByRole('region', { name: '本次选择完整摘要' })).toHaveTextContent('排除成员')
  expect(api.decideCandidates).not.toHaveBeenCalled()
})

it('回执不明后只回读；匹配的新 revision 恢复成功并且不再次提交', async () => {
  api.decideCandidates.mockRejectedValue(new Error('lost acknowledgement'))
  api.understanding.mockResolvedValue({ ...value, revision: 4, role_candidates: value.role_candidates.map((item, index) => index ? item : { ...item, decision: 'CONFIRMED' }) })
  const applied = vi.fn()
  render(<CandidateReview value={value} onApplied={applied} manual={null} staleReview={null}/>)
  begin()
  fireEvent.click(await screen.findByRole('button', { name: '核对保存结果' }))
  expect(await screen.findByText('本次业务信息已确认，权限规则尚未改变。')).toBeInTheDocument()
  expect(api.decideCandidates).toHaveBeenCalledOnce()
  expect(api.understanding).toHaveBeenCalledWith('p1')
  expect(applied).toHaveBeenCalledWith(expect.objectContaining({ revision: 4 }))
})

it('新 revision 不覆盖输入，且不可按旧 revision 提交', async () => {
  const props = { onApplied: vi.fn(), manual: null, staleReview: null }
  const view = render(<CandidateReview {...props} value={value}/>)
  fireEvent.change(screen.getByDisplayValue('成员'), { target: { value: '保留的本地名称' } })
  view.rerender(<CandidateReview {...props} value={{ ...value, revision: 4 }}/>)
  expect(screen.getByDisplayValue('保留的本地名称')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '审阅本次选择' })).toBeDisabled()
  expect(api.decideCandidates).not.toHaveBeenCalled()
})

it('卸载后的旧提交回执不会更新新项目，连续点击只发送一次', async () => {
  let resolve!: (value: ApplicationUnderstandingDto) => void
  api.decideCandidates.mockImplementation(() => new Promise(done => { resolve = done }))
  const applied = vi.fn()
  const view = render(<CandidateReview value={value} onApplied={applied} manual={null} staleReview={null}/>)
  fireEvent.click(screen.getByRole('button', { name: '审阅本次选择' }))
  const submit = screen.getByRole('button', { name: '确认这些业务信息' })
  fireEvent.click(submit); fireEvent.click(submit)
  expect(api.decideCandidates).toHaveBeenCalledOnce()
  view.unmount(); resolve({ ...value, revision: 4 })
  await waitFor(() => expect(applied).not.toHaveBeenCalled())
})
