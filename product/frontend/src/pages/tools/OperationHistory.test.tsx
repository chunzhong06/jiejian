import {cleanup,fireEvent,render,screen,within} from '@testing-library/react'
import {afterEach,expect,it} from 'vitest'
import {OperationHistory} from './OperationHistory'

afterEach(cleanup)

it('保留超过四项的准确回执，早期失败和范围可展开阅读',()=>{
  const operations=Array.from({length:7},(_,index)=>({operation_id:'op-'+index,capability:'flows.save',title:'保存流程 '+index,state:index===0?'FAILED':'SUCCEEDED',arguments:{private_marker:'不应从参数生成说明'},summary:[{label:'业务操作',value:'读取资料 '+index}],result:null,...(index===0?{error_code:'FLOW_NOT_READY'}:{})}))
  render(<OperationHistory operations={operations}/>)
  const earlier=screen.getByText('更早的操作 · 3 项').closest('details')!
  expect(earlier).not.toHaveAttribute('open')
  expect(screen.getByText('保存流程 6')).toBeVisible()
  expect(screen.getByText('保存流程 0')).not.toBeVisible()
  fireEvent.click(within(earlier).getByText('更早的操作 · 3 项'))
  expect(screen.getByText('保存流程 0')).toBeVisible()
  const first=screen.getByText('保存流程 0').closest('li')!
  fireEvent.click(within(first).getByText('查看操作内容'))
  expect(within(first).getByText('读取资料 0')).toBeVisible()
  fireEvent.click(within(first).getByText('执行诊断'))
  expect(within(first).getByText('FLOW_NOT_READY')).toBeVisible()
  expect(screen.queryByText('不应从参数生成说明')).not.toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(screen.queryByText(/回执/)).not.toBeInTheDocument()
})

it('保存、检查提交与后台完成各自表达，未知状态不提前宣布成功',()=>{
  const operation={operation_id:'save',capability:'flows.save',title:'保存发布流程',state:'SUCCEEDED',arguments:{},result:null}
  render(<OperationHistory operations={[operation,{...operation,operation_id:'check',capability:'checks.start',title:'提交发布检查'},{...operation,operation_id:'unknown',title:'查询发布状态',state:'UNKNOWN'}]}/>)
  expect(screen.getByText('已保存')).toBeVisible()
  expect(screen.getByText('已提交检查')).toBeVisible()
  expect(screen.getByText('结果待核对')).toBeVisible()
  expect(screen.queryByText('检查通过')).not.toBeInTheDocument()
})
