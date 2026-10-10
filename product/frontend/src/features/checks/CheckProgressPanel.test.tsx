// 进度只跟随服务端计数与阶段，时间流逝、停止或断线不能推演安全结果。
import {act,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {CheckProgressPanel} from './CheckProgressPanel'
import type {CheckStatus} from '../../api/checks/currentChecks'

const running={run:{lifecycle:'RUNNING'},job:{cancel_requested:false},progress:{phase:'EXECUTING',completed_cases:1,planned_cases:3},result_integrity:'NOT_PUBLISHED'} as CheckStatus
afterEach(()=>vi.useRealTimers())
it('停止且没有阶段记录时，不声称仍在准备或执行',()=>{
  render(<CheckProgressPanel status={{...running,run:{...running.run,lifecycle:'FAILED'},progress:null}} paused={false}/>)
  expect(screen.getByRole('heading',{name:'本轮执行已停止'})).toBeInTheDocument()
  expect(screen.getByText('本轮已停止，未取得完整准备记录。')).toBeInTheDocument()
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
})
it('等待、准备和发布各自说明真实状态，阶段快进后仍能回看',()=>{
  const saved={...running,run:{...running.run,run_id:'r1',policy_epoch:2,created_at_us:1780000000000000},job:{...running.job!,attempt:1}}
  const view=render(<CheckProgressPanel status={{...saved,run:{...saved.run,lifecycle:'QUEUED'},progress:null}} paused={false}/>)
  expect(screen.getByText('检查请求已保存，执行器领取后开始准备。')).toBeInTheDocument()
  expect(screen.queryByText('尚未取得检查项进度')).not.toBeInTheDocument()
  view.rerender(<CheckProgressPanel status={{...saved,progress:{phase:'PREPARING',planned_cases:3,completed_cases:0}}} paused={false}/>)
  expect(screen.getByText('3 项验证')).toBeInTheDocument()
  view.rerender(<CheckProgressPanel status={saved} paused={false}/>)
  fireEvent.click(screen.getByRole('button',{name:'查看等待阶段'}))
  expect(screen.getByRole('heading',{name:'检查请求已保存'})).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'返回最新阶段'}))
  expect(screen.getByRole('heading',{name:'正在执行并观察业务结果'})).toBeInTheDocument()
  view.rerender(<CheckProgressPanel status={{...saved,run:{...saved.run,lifecycle:'COMPLETED',finished_at_us:1780000001000000},progress:{phase:'FINALIZING',planned_cases:3,completed_cases:3},result_integrity:'VALID'}} paused={false}/>)
  expect(screen.getByRole('heading',{name:'结果已发布并核验'})).toBeInTheDocument()
  expect(screen.getByText('证据文件、发布记录和所属检查已通过读取核验。')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'查看执行阶段'}))
  expect(screen.getByText('执行已结束，逐项事实与证明可在本轮结果中查看。')).toBeInTheDocument()
})
it('时间流逝不增加计数，只有新读取改变进度条',()=>{
  vi.useFakeTimers()
  const view=render(<CheckProgressPanel status={running} paused={false}/>)
  const progress=screen.getByRole('progressbar',{name:'已处理检查项'})
  expect(progress).toHaveAttribute('aria-valuenow','1')
  act(()=>vi.advanceTimersByTime(30000))
  expect(progress).toHaveAttribute('aria-valuenow','1')
  view.rerender(<CheckProgressPanel status={{...running,progress:{...running.progress!,completed_cases:3,phase:'FINALIZING'}}} paused={false}/>)
  expect(progress).toHaveAttribute('aria-valuenow','3')
  expect(screen.getByRole('heading',{name:'正在核验并发布结果'})).toBeInTheDocument()
  expect(screen.queryByText('验证通过')).not.toBeInTheDocument()
})
it('缺少进度不绘制猜测的百分比，断线保留上次计数',()=>{
  const view=render(<CheckProgressPanel status={{...running,progress:null,run:{...running.run,lifecycle:'QUEUED'}}} paused={false}/>)
  expect(screen.getByRole('heading',{name:'等待执行器领取'})).toBeInTheDocument()
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  view.rerender(<CheckProgressPanel status={running} paused/> )
  expect(screen.getByRole('heading',{name:'暂时无法读取最新进度'})).toBeInTheDocument()
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow','1')
})
