import {fireEvent,render,screen,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {WorkflowSteps,type WorkflowStep} from './WorkflowSteps'
import {ActionLink} from './actions'
import {WorkflowContext} from '../lib/workflow'
import {Progress} from './Progress'
import {useState} from 'react'
import {TaskSurface} from './TaskSurface'

const steps:WorkflowStep[]=[{id:'scope',label:'允许读取',state:'pending'},{id:'check',label:'核对来源',state:'complete'},{id:'adopt',label:'用于检查',state:'blocked'}]

it('嵌入任务继承父工作面的标题层级',()=>{
  render(<><h1>本次检查</h1><TaskSurface level={2} title="调整检查范围" onBack={vi.fn()}>选定的规则</TaskSurface></>);
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
  expect(screen.getByRole('heading',{level:2,name:'调整检查范围'})).toBeVisible();
})

it('聚焦任务退出后保留输入，返回触发位置且不把关闭当作完成',()=>{
  const completed=vi.fn()
  function Work(){const [active,setActive]=useState(false);return <><button onClick={()=>setActive(true)}>打开当前任务</button><TaskSurface active={active} title="核对当前对象" onBack={()=>setActive(false)}><input aria-label="当前草稿"/><button onClick={completed}>确认处理</button></TaskSurface></>}
  render(<Work/>);
  const trigger=screen.getByRole('button',{name:'打开当前任务'});trigger.focus();fireEvent.click(trigger);
  fireEvent.change(screen.getByRole('textbox',{name:'当前草稿'}),{target:{value:'保留的内容'}});
  fireEvent.click(screen.getByRole('button',{name:'返回原工作'}));
  expect(trigger).toHaveFocus();expect(screen.queryByRole('textbox',{name:'当前草稿'})).not.toBeInTheDocument();
  fireEvent.click(trigger);expect(screen.getByRole('textbox',{name:'当前草稿'})).toHaveValue('保留的内容');
  expect(completed).not.toHaveBeenCalled();
})

it('阶段只呈现各自事实，不因后续完成而自动完成前项；只读没有按钮',()=>{
  render(<WorkflowSteps label="准备证明来源" steps={steps}/>)
  const rows=within(screen.getByRole('list',{name:'准备证明来源'})).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('待进行');expect(rows[1]).toHaveTextContent('已完成');expect(rows[2]).toHaveTextContent('需要处理')
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

it('可回访阶段使用稳定身份，未开放阶段仍由调用方禁用',()=>{
  const change=vi.fn()
  render(<WorkflowSteps label="设置流程" steps={[{id:'requests',label:'执行请求',state:'current'},{id:'review',label:'核对并使用',state:'pending',disabled:true}]} onStepChange={change}/>)
  fireEvent.click(screen.getByRole('button',{name:/执行请求/}));expect(change).toHaveBeenCalledExactlyOnceWith('requests')
  fireEvent.click(screen.getByRole('button',{name:/核对并使用/}));expect(change).toHaveBeenCalledOnce()
  expect(screen.getByRole('button',{name:/执行请求/}).closest('li')).toHaveAttribute('aria-current','step')
})

it('链接保留整页跳转与嵌入工作流的不同责任，修饰键不被截获',()=>{
  const open=vi.fn(),finish=vi.fn()
  render(<WorkflowContext.Provider value={{open,finish,label:'返回检查'}}><ActionLink href="#/permissions?rule_id=one">工作流中的规则</ActionLink><ActionLink navigationScope="page" href="#/reports?run_id=one">独立报告</ActionLink></WorkflowContext.Provider>)
  fireEvent.click(screen.getByRole('link',{name:'工作流中的规则'}));expect(open).toHaveBeenCalledExactlyOnceWith('/permissions?rule_id=one')
  fireEvent.click(screen.getByRole('link',{name:'独立报告'}));expect(location.hash).toContain('run_id=one');expect(open).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('link',{name:'工作流中的规则'}),{ctrlKey:true});expect(open).toHaveBeenCalledOnce()
})

it('可量化进度保留实际数值，未知进度不生成百分比',()=>{
  const view=render(<Progress label="检查进度" value={2} max={5}/>)
  expect(screen.getByRole('progressbar',{name:'检查进度'})).toHaveAttribute('value','2')
  view.rerender(<Progress label="检查进度"/>)
  expect(screen.getByRole('progressbar',{name:'检查进度'})).not.toHaveAttribute('value')
})
