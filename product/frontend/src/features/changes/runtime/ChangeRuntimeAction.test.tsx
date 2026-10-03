// 验证运行加载在回执丢失后沿用原操作，不重复启动。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ChangeRuntimeAction } from './ChangeRuntimeAction'
import type { DevelopmentView } from '../../../api/changes/development'
const api=vi.hoisted(()=>({loadRuntime:vi.fn(),runtimeReceipt:vi.fn()}))
vi.mock('../../../api/changes/development',async()=>({...await vi.importActual<typeof import('../../../api/changes/development')>('../../../api/changes/development'),developmentApi:api}))
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear()})
it('先读未知回执，再显式恢复同一加载',async()=>{
 const value={task:{version:4},deliveries:[{delivery_id:'d1'}]} as DevelopmentView
 api.loadRuntime.mockRejectedValueOnce(new Error('lost')).mockImplementationOnce((_project,delivery,body)=>Promise.resolve({project_id:'p1',delivery_id:delivery,operation_id:body.operation_id,status:'SUCCEEDED'}))
 api.runtimeReceipt.mockImplementation((_project,id)=>Promise.resolve({project_id:'p1',delivery_id:'d1',operation_id:id,status:'UNKNOWN'}))
 const onChanged=vi.fn(),onError=vi.fn()
 render(<ChangeRuntimeAction projectId="p1" value={value} onChanged={onChanged} onError={onError}/>)
 fireEvent.click(screen.getByRole('button',{name:'加载这次修改'}))
 fireEvent.click(await screen.findByRole('button',{name:'查询加载回执'}))
 expect(api.loadRuntime).toHaveBeenCalledOnce()
 fireEvent.click(await screen.findByRole('button',{name:'恢复原加载'}))
 await waitFor(()=>expect(onChanged).toHaveBeenCalledOnce())
 expect(api.loadRuntime.mock.calls[1]).toEqual(api.loadRuntime.mock.calls[0])
 expect(api.runtimeReceipt).toHaveBeenCalledWith('p1',api.loadRuntime.mock.calls[0][2].operation_id)
})
