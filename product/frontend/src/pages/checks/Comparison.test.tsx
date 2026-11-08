import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {Comparison} from './Comparison'
import {comparisonApi} from '../../entities/check/api/comparison'

const baseline='run_'+'1'.repeat(32),current='run_'+'2'.repeat(32),earlier='run_'+'0'.repeat(32),key='a'.repeat(64),project='comparison-ui'
const run=(id:string,time:number)=>({run_id:id,created_at_us:time,lifecycle:'COMPLETED',integrity:'VALID',environment:null,source_fingerprint:null,deployment:'UNKNOWN'})
const observation={case_id:'case_'+'b'.repeat(32),verdict:'VULNERABLE',expectation:'DENY',resource_id:'order-1',identity_status:'MATCH',execution_outcome:'ACCEPTED',control_verdict:'SAFE',evidence_ids:[]}
const props=()=>({projectId:project,name:'订单',official:false,refresh:vi.fn(),onError:vi.fn(),route:{path:'/reports',query:new URLSearchParams({view:'compare',baseline,current,earlier,return_to:'/reports?query=订单'})}})
beforeEach(()=>{
 sessionStorage.clear()
 vi.spyOn(comparisonApi,'read').mockResolvedValue({project_id:project,baseline:run(baseline,1000),current:run(current,2000),earlier:run(earlier,0),limitations:['DEPLOYMENT_VERSION_UNCONFIRMED'],counts:{INSUFFICIENT:1},items:[{key,action_label:'读取订单',subject_label:'成员',state:'INSUFFICIENT',reasons:['CURRENT_NOT_COVERED'],before:observation,after:null}],next_cursor:null} as never)
 vi.spyOn(comparisonApi,'detail').mockResolvedValue({project_id:project,before:null,after:null})
})
afterEach(()=>vi.restoreAllMocks())

it.each([['SAFE','符合规则','positive'],['VULNERABLE','不符合规则','negative'],['INCONCLUSIVE','尚未确认','caution'],[null,'无可用结果','neutral']])('正常对照状态只呈现已发布事实：%s',async(verdict,label,tone)=>{
 const story={display_name:'读取订单',permission:{expectation:'DENY'},fact_comparison:{planned_identity:{label:'成员'},effects:[],allow_control:verdict?{verdict}:null,resource_id:'order-1'}}
 vi.mocked(comparisonApi.detail).mockResolvedValue({project_id:project,before:story,after:null} as never)
 render(<Comparison {...props()}/>)
 const row=(await screen.findByText('正常业务对照')).parentElement!
 expect(row).toHaveTextContent(label!)
 expect(row.querySelector('.jj-badge')).toHaveClass('is-'+tone)
 expect(screen.queryByText('已验证修复')).not.toBeInTheDocument()
})

it('未覆盖的原问题保持证据不足，回到原报告仍携带准确比较对象',async()=>{
 render(<Comparison {...props()}/>)
 expect(await screen.findByText('这次检查未覆盖这项内容')).toBeVisible()
 expect(screen.queryByText('已验证修复')).not.toBeInTheDocument()
 expect(screen.queryByRole('link',{name:'阅读这次证据'})).not.toBeInTheDocument()
 const link=screen.getByRole('link',{name:'阅读参照报告'}),url=new URL(link.getAttribute('href')!.slice(1),'http://localhost')
 expect(url.searchParams.get('run_id')).toBe(baseline)
 const back=new URL(url.searchParams.get('return_to')!,'http://localhost')
 expect(back.searchParams.get('baseline')).toBe(baseline)
 expect(back.searchParams.get('current')).toBe(current)
 expect(back.searchParams.get('earlier')).toBe(earlier)
 expect(back.searchParams.get('return_to')).toBe('/reports?query=订单')
 await waitFor(()=>expect(comparisonApi.detail).toHaveBeenCalledWith(project,baseline,current,key))
 fireEvent.click(screen.getByRole('button',{name:'收起比较说明'}))
 expect(screen.queryByRole('region',{name:'成员的读取订单比较说明'})).not.toBeInTheDocument()
 expect(screen.getByRole('button',{name:'读取订单 成员'})).toHaveFocus()
})

it('手工深链接缺少准确记录时拒绝比较，不退回最近或全部记录',()=>{
 const value=props();value.route.query.delete('baseline')
 render(<Comparison {...value}/>)
 expect(screen.getByText('请选择用作参照和这次比较的准确记录，不会自动替换成最近记录。')).toBeVisible()
 expect(comparisonApi.read).not.toHaveBeenCalled()
})

it('在结果原行展开对应说明，切换和收起仍保持准确报告对象',async()=>{
 const second='c'.repeat(64),secondCase='case_'+'d'.repeat(32)
 vi.mocked(comparisonApi.read).mockResolvedValue({project_id:project,baseline:run(baseline,1000),current:run(current,2000),limitations:[],counts:{UNCHANGED:2},items:[
  {key,action_label:'读取订单',subject_label:'成员',state:'UNCHANGED',reasons:[],before:observation,after:observation},
  {key:second,action_label:'下载报告',subject_label:'负责人',state:'UNCHANGED',reasons:[],before:{...observation,case_id:secondCase},after:{...observation,case_id:secondCase}},
 ],next_cursor:null} as never)
 render(<Comparison {...props()}/>)
 expect(await screen.findByRole('region',{name:'成员的读取订单比较说明'})).toBeVisible()
 const secondRow=screen.getByRole('button',{name:'下载报告 负责人'})
 fireEvent.click(secondRow)
 expect(await screen.findByRole('region',{name:'负责人的下载报告比较说明'})).toBeVisible()
 expect(screen.queryByRole('region',{name:'成员的读取订单比较说明'})).not.toBeInTheDocument()
 expect(secondRow).toHaveAttribute('aria-expanded','true')
 const link=await screen.findByRole('link',{name:'阅读这次证据'})
 expect(new URLSearchParams(link.getAttribute('href')!.split('?')[1]).get('case_id')).toBe(secondCase)
 fireEvent.keyDown(screen.getByRole('region',{name:'负责人的下载报告比较说明'}),{key:'Escape'})
 expect(secondRow).toHaveAttribute('aria-expanded','false')
 expect(secondRow).toHaveFocus()
})
