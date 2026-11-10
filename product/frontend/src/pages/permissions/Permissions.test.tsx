import {experienceApi} from '../../entities/application/api/experience'
import {officialDraft} from './OfficialRules.fixtures'
import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import type {ReactNode} from 'react'
import {Permissions} from './Permissions'
import {businessBoundariesApi as api} from '../../entities/permission/api/businessBoundaries'
import {ruleCandidatesApi} from '../../entities/permission/api/ruleCandidates'

vi.mock('./ProposalReview',()=>({ProposalReview:({children}:{children:ReactNode})=><section>{children}</section>}))
const original='/reports?view=plan&scope_id=limited&plan_item=proof'
const proposal={proposal:{project_id:'app',proposal_id:'proposal',unresolved_questions:[]},review:{basis_state:'COMPLETE',current_state_changed:false},decision:null}
const boundary={project_id:'app',actors:[],actions:[],permission_intents:[]}
beforeEach(()=>{
 sessionStorage.clear();vi.spyOn(api,'editor').mockResolvedValue({project_id:'app',boundary} as never)
 vi.spyOn(ruleCandidatesApi,'context').mockResolvedValue({project_id:'app'} as never)
 vi.spyOn(api,'proposal').mockResolvedValue(proposal as never)
})
afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})
const show=()=>render(<Permissions projectId="app" name="订单" official={false} refresh={vi.fn()} onError={vi.fn()} route={{path:'/permissions',query:new URLSearchParams({proposal_id:'proposal',return_to:original})}}/>)
const approve=async()=>{fireEvent.click(await screen.findByRole('checkbox',{name:'我已核对全部访问规则及业务定义'}));fireEvent.click(screen.getByRole('button',{name:'批准权限规则'}))}
const returned=()=>{const url=new URL(screen.getByRole('link',{name:'返回检查范围'}).getAttribute('href')!.slice(1),'http://localhost');expect(url.searchParams.get('scope_id')).toBe('limited');expect(url.searchParams.get('plan_item')).toBe('proof')}

it('批准成功后读取失败仍保留回执和原检查，不重复批准',async()=>{
 const submit=vi.spyOn(api,'approve').mockResolvedValue(boundary as never)
 vi.mocked(api.proposal).mockResolvedValueOnce(proposal as never).mockRejectedValue(new Error('读取中断'))
 vi.mocked(api.editor).mockResolvedValueOnce({project_id:'app',boundary} as never).mockRejectedValue(new Error('详情未更新'))
 show();await approve();expect(await screen.findByText(/确认回执已保留/)).toBeVisible();returned()
 expect(submit).toHaveBeenCalledOnce();expect(screen.queryByRole('button',{name:'批准权限规则'})).not.toBeInTheDocument()
})

it('批准响应未知后回读同一提案，采用相同完成反馈和回程',async()=>{
 vi.spyOn(api,'approve').mockRejectedValue(new Error('连接中断'))
 vi.mocked(api.proposal).mockResolvedValueOnce(proposal as never).mockResolvedValue({...proposal,decision:{decision:'APPROVED'}} as never)
 show();await approve();fireEvent.click(await screen.findByRole('button',{name:'查询这次批准'}))
 await waitFor(()=>expect(screen.getByRole('link',{name:'返回检查范围'})).toBeVisible());returned()
 expect(api.approve).toHaveBeenCalledOnce();expect(sessionStorage.getItem('jiejian.studio.approval:app:proposal')).toBeNull()
})

it('放弃提案后明确保留现有规则，并能回到原检查',async()=>{
 vi.spyOn(api,'reject').mockResolvedValue({...proposal,decision:{decision:'REJECTED'}} as never)
 show();fireEvent.click(await screen.findByRole('button',{name:'放弃提案'}))
 expect(await screen.findByText('这份提案未被采用，现有权限保持原样。')).toBeVisible();returned()
})

it.each([false,true])('示例先展示完整规则，批准前核对服务端实际内容；内容变化=%s',async changed=>{
 const preview=vi.spyOn(experienceApi,'boundaryDraft').mockResolvedValue(officialDraft)
 const value={...proposal,proposal:{...officialDraft.command,project_id:'app',proposal_id:'official'}}
 if(changed)value.proposal.proposed_permissions=[{...value.proposal.proposed_permissions[0],expectation:'DENY'}]
 const create=vi.spyOn(experienceApi,'boundaryProposal').mockResolvedValue(value as never),submit=vi.spyOn(api,'approve').mockResolvedValue(boundary as never)
 vi.mocked(api.proposal).mockResolvedValue({...value,decision:{decision:'APPROVED'}} as never)
 vi.mocked(api.editor).mockResolvedValue({project_id:'app',boundary,pending_proposals:[]} as never)
 const error=vi.fn()
 render(<Permissions projectId="app" name="示例" official refresh={vi.fn()} onError={error} route={{path:'/permissions',query:new URLSearchParams()}}/>)
 expect(await screen.findByRole('table',{name:'示例权限要求'})).toBeVisible();expect(create).not.toHaveBeenCalled();expect(submit).not.toHaveBeenCalled();expect(preview).toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'批准规则并继续'}))
 await waitFor(()=>expect(create).toHaveBeenCalledOnce())
 if(changed){await waitFor(()=>expect(error).toHaveBeenCalled());expect(submit).not.toHaveBeenCalled()}
 else{expect(await screen.findByRole('heading',{name:'示例规则已确认'})).toBeVisible();expect(submit).toHaveBeenCalledOnce();expect(screen.getByRole('link',{name:'准备示例材料'})).toHaveAttribute('href',expect.stringContaining('prepare_example=1'))}
})
