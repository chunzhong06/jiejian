// 进度只跟随服务端计数与阶段，时间流逝、停止或断线不能推演安全结果。
import {act,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {CheckProgressPanel} from './CheckProgressPanel'
import type {CheckStatus} from '../../api/checks/currentChecks'

const running={run:{lifecycle:'RUNNING'},job:{cancel_requested:false},progress:{phase:'EXECUTING',completed_cases:1,planned_cases:3},result_integrity:'NOT_PUBLISHED'} as CheckStatus
afterEach(()=>vi.useRealTimers())
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
