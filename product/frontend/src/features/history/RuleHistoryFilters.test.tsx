// 验证唯一历史入口、精确规则过滤、返回保留和整理未知回执；不发起权限检查。
import {cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react'
import {useState} from 'react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {CheckHistoryPage} from './CheckHistoryPage'
import {ApiError} from '../../api/http'
import {RuleHistoryFilters} from './RuleHistoryFilters'
import type {RuleHistoryPage} from '../../api/checks/currentChecks'
const api=vi.hoisted(()=>({historyRules:vi.fn(),history:vi.fn(),maintainHistory:vi.fn(),historyReceipt:vi.fn()}))
vi.mock('../../api/checks/currentChecks',()=>({currentChecksApi:api}))
const rule={intent_id:'rule',revision:2,intent_hash:'a'.repeat(64),expectation:'DENY' as const,effective_state:'ACTIVE',relation:'OTHER_ROLE',action_label:'取得文件',subject_label:'评审',owner_label:'负责人',latest_run_id:'run',case_results:[{case_id:'case',verdict:'VULNERABLE' as const}],result_integrity:'VALID',index_matches:true}
const page:RuleHistoryPage={project_id:'p',items:[rule],next_cursor:null,coverage:{project_id:'p',checkpoint:0,generation:0,processed:0,failed:0,missing:1,status:'NEEDS_SCAN'}}
const error=vi.fn()
function Harness(){const [path,setPath]=useState('/history');const search=path.split('?')[1]??'',params=new URLSearchParams(search)
  return <CheckHistoryPage project={{project_id:'p',name:'当前应用'}} onError={error} onNavigate={setPath} locationSearch={search} requestedRunId={params.get('run_id')}
    renderRun={(run,onBack)=><section><h1>检查详情 {run}</h1><p>{params.get('case_id')}</p><button onClick={onBack}>返回历史</button></section>}/>
}
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();vi.spyOn(window,'scrollTo').mockImplementation(()=>{});api.historyRules.mockResolvedValue(page)
  api.history.mockResolvedValue({project_id:'p',items:[{status:{run:{run_id:'run',project_id:'p',lifecycle:'COMPLETED',verdict:'BLOCK',policy_epoch:2,created_at_us:1},result_integrity:'VALID'},action_labels:['取得文件'],change_id:null,source_run_id:null,matching_cases:['case'],matching_verdicts:['VULNERABLE']}],next_cursor:null})})
afterEach(cleanup)
async function chooseRule(){
  fireEvent.mouseDown(await screen.findByRole('combobox',{name:'筛选权限规则'}))
  fireEvent.click(await screen.findByText('评审对负责人拥有的资源，不得取得文件 · 修订 2'))
}
it('同一检查列表筛选规则后进入准确检查项，返回保留筛选',async()=>{
  render(<Harness/>);expect(await screen.findByRole('region',{name:'历史检查列表'})).toBeInTheDocument()
  expect(screen.queryByRole('navigation',{name:'历史查看方式'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'按规则'})).not.toBeInTheDocument()
  await chooseRule()
  await waitFor(()=>expect(api.history).toHaveBeenLastCalledWith('p',expect.objectContaining({rule:{intent_id:'rule',revision:2,intent_hash:'a'.repeat(64)}})))
  fireEvent.click(within(screen.getByRole('region',{name:'历史检查列表'})).getByRole('button',{name:/取得文件/}))
  expect(await screen.findByRole('heading',{name:'检查详情 run'})).toBeInTheDocument();expect(screen.getByText('case')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'返回历史'}))
  expect(await screen.findByRole('combobox',{name:'筛选权限规则'})).toBeInTheDocument()
  expect(screen.getByText('含权限问题')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'清除筛选'}))
  await waitFor(()=>expect(api.history).toHaveBeenLastCalledWith('p',{cursor:null}))
})
it('进入结果再返回保留旧修订选项',async()=>{
  render(<Harness/>);fireEvent.click(await screen.findByRole('checkbox',{name:'包含旧修订与已停用规则'}))
  await waitFor(()=>expect(api.historyRules).toHaveBeenLastCalledWith('p',undefined,true))
  fireEvent.click(within(await screen.findByRole('region',{name:'历史检查列表'})).getByRole('button',{name:/取得文件/}))
  fireEvent.click(await screen.findByRole('button',{name:'返回历史'}))
  expect(screen.getByRole('checkbox',{name:'包含旧修订与已停用规则'})).toBeChecked()
})
it('整理响应未知时只查询原操作，成功回读后清除未决状态',async()=>{
  api.maintainHistory.mockRejectedValue(new Error('lost'))
  const props={projectId:'p',onError:error,onSelect:vi.fn()}
  const instance=render(<RuleHistoryFilters {...props}/>);fireEvent.click(await screen.findByRole('button',{name:'整理旧记录'}))
  await screen.findByText('这批整理的结果尚未确认，请先查询原操作。')
  const operation=api.maintainHistory.mock.calls[0][1].operation_id
  instance.unmount();render(<RuleHistoryFilters {...props}/>)
  api.historyReceipt.mockResolvedValue({status:'FOUND',receipt:{project_id:'p',operation_id:operation,checkpoint:1,processed:1,failed:0,complete:true}})
  fireEvent.click(await screen.findByRole('button',{name:'查询整理结果'}))
  await waitFor(()=>expect(screen.queryByRole('button',{name:'查询整理结果'})).not.toBeInTheDocument())
  expect(api.historyReceipt).toHaveBeenCalledWith('p',operation);expect(api.maintainHistory).toHaveBeenCalledTimes(1)
})
it('精确规则没有检查时保持空列表，不借其他修订结果',async()=>{
  render(<Harness/>);await screen.findByRole('region',{name:'历史检查列表'})
  api.history.mockResolvedValue({project_id:'p',items:[],next_cursor:null})
  await chooseRule();expect(await screen.findByText('没有匹配的检查记录')).toBeInTheDocument()
  expect(screen.queryByText('含权限问题')).not.toBeInTheDocument()
})
it('规则候选按原游标分页，项目切换清除旧候选',async()=>{
  api.historyRules.mockResolvedValueOnce({...page,next_cursor:'cursor'}).mockResolvedValueOnce({...page,items:[{...rule,intent_id:'other',action_label:'查看资料'}]})
  const props={onError:error,onSelect:vi.fn()};const instance=render(<RuleHistoryFilters {...props} projectId="p"/>)
  fireEvent.mouseDown(await screen.findByRole('combobox',{name:'筛选权限规则'}))
  fireEvent.click(await screen.findByRole('button',{name:'更多规则'}));await screen.findByText('评审对负责人拥有的资源，不得查看资料 · 修订 2')
  expect(api.historyRules).toHaveBeenLastCalledWith('p','cursor',false)
  api.historyRules.mockResolvedValue({...page,project_id:'q',coverage:{...page.coverage,project_id:'q'},items:[]})
  instance.rerender(<RuleHistoryFilters {...props} projectId="q"/>);await waitFor(()=>expect(api.historyRules).toHaveBeenLastCalledWith('q',undefined,false))
  expect(screen.queryByText('评审对负责人拥有的资源，不得取得文件 · 修订 2')).not.toBeInTheDocument()
})
it.each(['intent_id=rule','page_before_time=2','page_before_time=no&page_before_run=run'])('无效规则或分页定位不悄悄显示其他记录：%s',async search=>{
  render(<CheckHistoryPage project={{project_id:'p'}} onError={error} onNavigate={vi.fn()} locationSearch={search} renderRun={()=>null}/>)
  expect(screen.getByRole('alert')).toBeInTheDocument();expect(api.history).not.toHaveBeenCalled()
})

it('明确的checkpoint冲突释放未决操作并刷新，不重试旧批次',async()=>{
  api.maintainHistory.mockRejectedValue(new ApiError('STATE_PRECONDITION','位置已更新'))
  render(<RuleHistoryFilters projectId="p" onError={error} onSelect={vi.fn()}/>)
  fireEvent.click(await screen.findByRole('button',{name:'整理旧记录'}))
  await waitFor(()=>expect(error).toHaveBeenCalledWith(expect.objectContaining({code:'STATE_PRECONDITION'})))
  expect(screen.queryByRole('button',{name:'查询整理结果'})).not.toBeInTheDocument()
  expect(api.maintainHistory).toHaveBeenCalledTimes(1)
})
