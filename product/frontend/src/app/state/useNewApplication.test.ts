// 新接入先释放旧上下文；未知停止只回读，迟到回执不能重新选回旧项目。
import {act,renderHook,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {useNewApplication} from './useNewApplication'
const api=vi.hoisted(()=>({status:vi.fn(),stop:vi.fn()}))
vi.mock('../../api/applications/experience',()=>({experienceApi:api}))
const running={active:true,lifecycle:'RUNNING',recovery_state:'OWNED_RUNNING',project_id:'sample'}
const exited={...running,active:false,lifecycle:'STOPPED',recovery_state:'EXITED'}
const props=()=>({onEnter:vi.fn(),onEnvironment:vi.fn(),onError:vi.fn()})
beforeEach(()=>vi.resetAllMocks())
it('先进入新上下文，再一次停止运行中的官方示例',async()=>{
 const p=props();api.status.mockResolvedValue(running);api.stop.mockResolvedValue(exited)
 const {result}=renderHook(()=>useNewApplication(p))
 act(()=>result.current.begin())
 expect(p.onEnter).toHaveBeenCalledOnce()
 await waitFor(()=>expect(result.current.state).toBe('READY'))
 expect(api.stop).toHaveBeenCalledTimes(1);expect(api.stop.mock.calls[0][0]).toMatch(/^[0-9a-f-]{36}$/)
 expect(p.onEnvironment).toHaveBeenLastCalledWith(exited)
})
it('没有官方实例时直接准备接入，不停止其他应用',async()=>{
 api.status.mockResolvedValue({active:false,lifecycle:'NOT_STARTED'})
 const {result}=renderHook(()=>useNewApplication(props()))
 act(()=>result.current.begin());await waitFor(()=>expect(result.current.state).toBe('READY'))
 expect(api.stop).not.toHaveBeenCalled()
})
it('停止响应丢失后查询状态，不重复提交停止',async()=>{
 const p=props();api.status.mockResolvedValue(running);api.stop.mockRejectedValue(new Error('response lost'))
 const {result}=renderHook(()=>useNewApplication(p))
 act(()=>result.current.begin());await waitFor(()=>expect(p.onError).toHaveBeenCalledOnce())
 await waitFor(()=>expect(api.status).toHaveBeenCalledTimes(2));expect(result.current.state).toBe('UNCONFIRMED')
 api.status.mockResolvedValue(exited)
 await act(async()=>{await result.current.reread()})
 expect(result.current.state).toBe('READY');expect(api.stop).toHaveBeenCalledTimes(1)
})
it('已有停止进行中时只读，不能再发一次停止',async()=>{
 api.status.mockResolvedValue({...running,lifecycle:'STOPPING',operation_state:'PENDING'})
 const {result}=renderHook(()=>useNewApplication(props()));act(()=>result.current.begin())
 await waitFor(()=>expect(result.current.state).toBe('UNCONFIRMED'));expect(api.stop).not.toHaveBeenCalled()
})
it('离开新接入后忽略尚未发出停止的旧环境响应',async()=>{
 let resolve!:(value:typeof running)=>void;api.status.mockReturnValue(new Promise(r=>{resolve=r}))
 const p=props(),{result}=renderHook(()=>useNewApplication(p));act(()=>result.current.begin());act(()=>result.current.abandon())
 await act(async()=>resolve(running));expect(api.stop).not.toHaveBeenCalled();expect(p.onEnvironment).not.toHaveBeenCalled()
})
