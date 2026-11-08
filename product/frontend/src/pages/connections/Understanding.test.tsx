import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {Understanding} from './Understanding'
import {projectsApi,type ApplicationUnderstandingDto,type RoleCandidateDto} from '../../entities/application/api/projects'

const candidate=(id:string,name:string):RoleCandidateDto=>({candidate_id:id,canonical_key:id,display_name:name,confidence:'HIGH',decision:'PROPOSED',origin:'MANUAL',stale:false,evidence:[]})
let data:ApplicationUnderstandingDto
beforeEach(()=>{
 sessionStorage.clear();location.hash='#/application?view=business&project_id=business-ui'
 data={project_id:'business-ui',revision:1,role_candidates:[candidate('owner','负责人')],action_candidates:[{...candidate('read','读取订单'),risk_hint:'READ'}],source_root:null,confirmed_endpoint:null,endpoint_source_fingerprint:null,endpoint_confirmed_at_us:null,endpoint_last_checked_at_us:null,endpoint_reachable:null,source_analysis_authorized:false,source_analysis_authorized_at_us:null,source_fingerprint:null,analysis_completed_at_us:null,created_at_us:1,updated_at_us:1}
 vi.spyOn(projectsApi,'understanding').mockImplementation(async()=>data)
})
afterEach(()=>vi.restoreAllMocks())

it('直接比较业务线索，分类往返和重新进入仍恢复同一修订的各项草稿',async()=>{
 const first=render(<Understanding projectId="business-ui" embedded/> )
 fireEvent.change(await screen.findByRole('textbox',{name:'业务角色名称：负责人'}),{target:{value:'订单负责人'}})
 fireEvent.click(screen.getByRole('button',{name:'业务操作 1'}))
 fireEvent.change(await screen.findByRole('textbox',{name:'业务操作名称：读取订单'}),{target:{value:'查看订单备注'}})
 fireEvent.click(screen.getByRole('button',{name:'业务角色 1'}))
 expect(screen.getByRole('textbox',{name:'业务角色名称：负责人'})).toHaveValue('订单负责人')
 first.unmount();const second=render(<Understanding projectId="business-ui" embedded/> )
 expect(await screen.findByRole('textbox',{name:'业务角色名称：负责人'})).toHaveValue('订单负责人')
 fireEvent.click(screen.getByRole('button',{name:'业务操作 1'}))
 expect(await screen.findByRole('textbox',{name:'业务操作名称：读取订单'})).toHaveValue('查看订单备注')
 second.unmount();render(<Understanding projectId="business-ui" embedded/> )
 expect(await screen.findByRole('textbox',{name:'业务操作名称：读取订单'})).toHaveValue('查看订单备注')
 expect(screen.getByRole('button',{name:'业务操作 1'})).toHaveAttribute('aria-pressed','true')
})

it('保存失败保留两类修改，成功只确认业务含义并留在当前工作面',async()=>{
 const save=vi.spyOn(projectsApi,'decideCandidates').mockRejectedValueOnce(new Error('保存暂不可用')).mockImplementationOnce(async()=>{data={...data,revision:2,role_candidates:[{...data.role_candidates[0],display_name:'订单负责人'}]};return data})
 render(<Understanding projectId="business-ui" embedded/> )
 const input=await screen.findByRole('textbox',{name:'业务角色名称：负责人'})
 fireEvent.change(input,{target:{value:'订单负责人'}})
 fireEvent.click(screen.getByRole('button',{name:'保存业务确认'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('保存暂不可用')
 expect(input).toHaveValue('订单负责人')
 fireEvent.click(screen.getByRole('button',{name:'保存业务确认'}))
 await waitFor(()=>expect(save).toHaveBeenCalledTimes(2))
 expect(save.mock.calls[1][1]).toBe(1)
 expect(save.mock.calls[1][2]).toEqual([{kind:'ROLE',candidate_id:'owner',display_name:'订单负责人',decision:'PROPOSED'}])
 expect(await screen.findByText('业务确认已保存，可以继续维护访问规则。')).toBeVisible()
 expect(location.hash).toContain('/application?view=business')
})
