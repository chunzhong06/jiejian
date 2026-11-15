import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {RecordingProgress} from './RecordingProgress'
import type {RecordingViewDto} from '../api/recordings'
import {recordingNeedsPolling} from '../model/recordingState'

const view:RecordingViewDto={recording:{recording_id:'original',project_id:'app',state:'STARTING',purpose:'TARGET',subject_test_identity_id:'owner',resource_owner_test_identity_id:'owner'},job:{job_id:'job',state:'RUNNING'},capture_phase:'AWAITING_CAPTURE'}
const props=()=>({view,action:'发布资料',accounts:[{test_identity_id:'owner',label:'负责人'}],busy:false,uncertain:false,onStart:vi.fn(),onStop:vi.fn(),onCancel:vi.fn(),onRefresh:vi.fn(),onBack:vi.fn()})

it('浏览器等待开始与采集中分别表达，等待就绪不冒充已记录业务步骤',()=>{
 const p=props(),node=render(<RecordingProgress {...p}/>);
 expect(screen.getByRole('heading',{name:'浏览器已就绪'})).toBeVisible()
 expect(screen.queryByRole('button',{name:'结束采集并核对'})).not.toBeInTheDocument()
 expect(p.onStart).not.toHaveBeenCalled()
 fireEvent.click(screen.getByRole('button',{name:'开始记录这个操作'}));expect(p.onStart).toHaveBeenCalledOnce()
 node.rerender(<RecordingProgress {...p} view={{...view,capture_phase:'CAPTURING',recording:{...view.recording!,state:'RECORDING'}}}/>);
 expect(screen.getByRole('heading',{name:'在独立浏览器中完成操作'})).toBeVisible()
 expect(screen.queryByRole('button',{name:'开始记录这个操作'})).not.toBeInTheDocument()
})

it.each(['FAILED','CANCELLED','COMPLETED','SAFETY_STOPPED'])('终态%s优先于残留采集阶段，只返回原准备，不重新执行',state=>{
 const p=props();render(<RecordingProgress {...p} view={{...view,capture_phase:'CAPTURING',recording:{...view.recording!,state,reason_codes:['SESSION_REFERENCE_EXPIRED']}}}/>);
 expect(screen.queryByRole('button',{name:'取消本次录制'})).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'结束采集并核对'})).not.toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:'返回准备并核对现场'}));expect(p.onBack).toHaveBeenCalledOnce()
 expect(p.onStart).not.toHaveBeenCalled();expect(p.onStop).not.toHaveBeenCalled();expect(p.onCancel).not.toHaveBeenCalled()
 expect(recordingNeedsPolling(state)).toBe(false)
})

it('响应边界停止显示具体原因，清理阶段和待审阅保持各自语义',()=>{
 render(<RecordingProgress {...props()} view={{...view,capture_phase:'FINISHED',recording:{...view.recording!,state:'SAFETY_STOPPED',reason_codes:['UNSUPPORTED_RESPONSE','STREAMING_UNSUPPORTED']}}}/>);
 expect(screen.getByRole('heading',{name:'这次录制已停止'})).toBeVisible()
 expect(screen.getByText(/流式传输/)).toBeVisible()
 expect(screen.queryByText('应用返回了本次录制不能安全采集的响应。')).not.toBeInTheDocument()
 expect(recordingNeedsPolling('CLEANING')).toBe(true)
 expect(recordingNeedsPolling('PENDING_REVIEW')).toBe(false)
})

it('读取失败保留原对象，禁用旧控制动作，仅显式重新读取',()=>{
 const p=props();render(<RecordingProgress {...p} error={new Error('读取中断')}/>);
 expect(screen.getByRole('button',{name:'开始记录这个操作'})).toBeDisabled()
 expect(screen.getByRole('button',{name:'取消本次录制'})).toBeDisabled()
 fireEvent.click(screen.getByRole('button',{name:'重新读取原录制'}));expect(p.onRefresh).toHaveBeenCalledOnce();expect(p.onStart).not.toHaveBeenCalled()
})
