import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {OfficialRules,matchesOfficialDraft} from './OfficialRules'
import {experienceApi} from '../../entities/application/api/experience'
import type {BoundaryProposalDto} from '../../entities/permission/api/businessBoundaries'

import {officialDraft as draft} from './OfficialRules.fixtures'

afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})

it('预置规则读取失败后停止加载，不把失败留在进行中',async()=>{
 vi.spyOn(experienceApi,'boundaryDraft').mockRejectedValue(new Error('示例当前未运行'))
 render(<OfficialRules projectId="app" name="示例" busy={false} uncertain={false} pending={[]} onApprove={vi.fn()} onReview={vi.fn()} onRecover={vi.fn()}/>)
 expect(await screen.findByText('示例当前未运行')).toBeVisible()
 expect(screen.queryByText('正在读取预置访问规则')).toBeNull()
 expect(screen.queryByRole('button',{name:'批准规则并继续'})).toBeNull()
})

it('读取与浏览规则不创建提案，只有明确批准提交当前展示的命令',async()=>{
 vi.spyOn(experienceApi,'boundaryDraft').mockResolvedValue(draft)
 const approve=vi.fn().mockResolvedValue(undefined)
 render(<OfficialRules projectId="app" name="示例" busy={false} uncertain={false} pending={[]} onApprove={approve} onReview={vi.fn()} onRecover={vi.fn()}/>)
 expect(await screen.findByRole('table',{name:'示例权限要求'})).toBeVisible()
 expect(screen.getByText('负责人的资源')).toBeVisible()
 expect(approve).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'批准规则并继续'}))
 await waitFor(()=>expect(approve).toHaveBeenCalledWith(draft,true))
})

it('原提交未知时保留提案回读，不允许重复批准',async()=>{
 vi.spyOn(experienceApi,'boundaryDraft').mockResolvedValue(draft)
 const approve=vi.fn(),recover=vi.fn()
 render(<OfficialRules projectId="app" name="示例" busy={false} uncertain pending={[]} onApprove={approve} onReview={vi.fn()} onRecover={recover}/>)
 expect(await screen.findByRole('button',{name:'批准规则并继续'})).toBeDisabled()
 fireEvent.click(screen.getByRole('button',{name:'读取待审提案'}))
 expect(recover).toHaveBeenCalledOnce();expect(approve).not.toHaveBeenCalled()
})

it('只接受当前项目及完整展示内容一致的服务端提案',()=>{
 const proposal={...draft.command,project_id:'app',proposal_id:'proposal'} as BoundaryProposalDto
 expect(matchesOfficialDraft(draft,proposal)).toBe(true)
 expect(matchesOfficialDraft(draft,{...proposal,project_id:'another'})).toBe(false)
 expect(matchesOfficialDraft(draft,{...proposal,proposed_permissions:[{...proposal.proposed_permissions[0],expectation:'DENY'}]})).toBe(false)
})
