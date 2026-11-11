import {afterEach,expect,it,vi} from 'vitest'

afterEach(()=>{delete (globalThis as any).__JIEJIAN_WORKFLOW_TIMING__;delete (globalThis as any).__JIEJIAN_TIMINGS__;vi.restoreAllMocks();vi.resetModules()})

it('关闭计量时不读取时钟，也不保存页面信息',async()=>{
 const clock=vi.spyOn(performance,'now')
 const {beginWorkflowTiming}=await import('./workflowTiming')
 clock.mockClear();beginWorkflowTiming('view.read')()
 expect(clock).not.toHaveBeenCalled()
 expect((globalThis as any).__JIEJIAN_TIMINGS__).toBeUndefined()
})

it('计量只记录固定阶段，有界保留且重复收口无副作用',async()=>{
 (globalThis as any).__JIEJIAN_WORKFLOW_TIMING__=true
 const {beginWorkflowTiming}=await import('./workflowTiming')
 const finish=beginWorkflowTiming('view.read');finish('ABORTED');finish()
 for(let index=0;index<2050;index++)beginWorkflowTiming('http.read')()
 const record=(globalThis as any).__JIEJIAN_TIMINGS__()
 expect(record.stages).toHaveLength(2048);expect(record.dropped).toBe(3)
 expect(record.stages[0].outcome).toBe('ABORTED')
 expect(Object.keys(record.stages[0]).sort()).toEqual(['duration_ms','outcome','phase','sequence'])
})

it('时钟倒退或User Timing不可用时，业务仍完成且时长标为未知',async()=>{
 (globalThis as any).__JIEJIAN_WORKFLOW_TIMING__=true
 vi.spyOn(performance,'now').mockReturnValueOnce(10).mockReturnValueOnce(5)
 vi.spyOn(performance,'mark').mockImplementation(()=>{throw new Error('unavailable')})
 const {beginWorkflowTiming}=await import('./workflowTiming')
 expect(()=>beginWorkflowTiming('http.command')()).not.toThrow()
 expect((globalThis as any).__JIEJIAN_TIMINGS__().stages[0]).toMatchObject({duration_ms:null,outcome:'COMPLETE'})
})
