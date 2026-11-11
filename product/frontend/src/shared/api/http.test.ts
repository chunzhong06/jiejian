import {expect,it,vi} from 'vitest'
import {request,ApiError} from './http'

const response=(data:unknown,status=200)=>new Response(JSON.stringify({schema_version:'1',data}),{status})

it('接纳结果和字段原因只消费白名单；缺失或非法状态保持未知',async()=>{
 const error=new ApiError('INPUT_INVALID','输入错误',undefined,undefined,false,undefined,'NOT_ACCEPTED',[
  {field:'name',reason:'TOO_LONG',input:'not-public'}, {field:'password',reason:'INVALID'}, {field:'name',reason:'raw-private-reason'}])
 expect(error.requestOutcome).toBe('NOT_ACCEPTED')
 expect(error.fieldErrors).toEqual([{field:'name',reason:'TOO_LONG'}])
 expect(new ApiError('INPUT_INVALID','输入错误').requestOutcome).toBe('UNKNOWN')
 expect(new ApiError('INPUT_INVALID','输入错误',undefined,undefined,false,undefined,'SUCCEEDED').requestOutcome).toBe('UNKNOWN')
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({schema_version:'1',error:{code:'INPUT_INVALID',message:'名称过长',details:{request_outcome:'NOT_ACCEPTED',field_errors:[{field:'name',reason:'TOO_LONG'}]}}}),{status:422})))
 try{await expect(request('/api/applications',{method:'POST'})).rejects.toMatchObject({requestOutcome:'NOT_ACCEPTED',fieldErrors:[{field:'name',reason:'TOO_LONG'}]})}finally{vi.unstubAllGlobals()}
})

it('只传递有界公开原因码与执行门禁，支持未开始操作的就地恢复',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({schema_version:'1',error:{code:'LOCAL_MAINTENANCE_FAILED',message:'正在准备',details:{execution_started:false,reason:'ENVIRONMENT_BUSY',private:'ignored'}}}),{status:409})))
 try{await expect(request('/api/system/maintenance/clear-all',{method:'POST'})).rejects.toMatchObject({executionStarted:false,reason:'ENVIRONMENT_BUSY'});expect(new ApiError('code','message',undefined,undefined,false,'bad reason').reason).toBeUndefined()}finally{vi.unstubAllGlobals()}
})

it('同一读取的订阅者独立取消，最后一个离开才取消网络请求',async()=>{
  let finish!:(value:Response)=>void
  const pending=new Promise<Response>(resolve=>{finish=resolve})
  const fetch=vi.fn().mockReturnValue(pending)
  vi.stubGlobal('fetch',fetch)
  const first=new AbortController(),second=new AbortController()
  const a=request('/api/shared-abort',{signal:first.signal}),b=request('/api/shared-abort',{signal:second.signal})
  const rejection=expect(a).rejects.toHaveProperty('name','AbortError')
  first.abort()
  await rejection
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(false)
  finish(response('retained reader'))
  expect(await b).toBe('retained reader')
})

it('同时读取同一资源只发送一次，结束后重新读取真实状态',async()=>{
  let resolve!:(value:Response)=>void
  const first=new Promise<Response>(done=>{resolve=done})
  const fetch=vi.fn().mockReturnValueOnce(first).mockResolvedValueOnce(response('new'))
  vi.stubGlobal('fetch',fetch)
  const a=request('/api/same-resource'),b=request('/api/same-resource')
  expect(fetch).toHaveBeenCalledTimes(1)
  resolve(response('first'))
  expect(await Promise.all([a,b])).toEqual(['first','first'])
  expect(await request('/api/same-resource')).toBe('new')
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('写入后的读取不会合并到写入前的在途请求',async()=>{
  let resolve!:(value:Response)=>void
  const pending=new Promise<Response>(done=>{resolve=done})
  const fetch=vi.fn().mockReturnValueOnce(pending).mockResolvedValueOnce(response('saved')).mockResolvedValueOnce(response('new'))
  vi.stubGlobal('fetch',fetch)
  const stale=request('/api/item')
  await request('/api/item',{method:'POST',body:'{}'})
  expect(await request('/api/item')).toBe('new')
  resolve(response('old'));await stale
  expect(fetch).toHaveBeenCalledTimes(3)
})

it('拒绝未知消息版本，不把错误结构当作成功数据',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({schema_version:'99',data:'invalid'}))))
  await expect(request('/api/version')).rejects.toMatchObject({code:'API_VERSION_UNSUPPORTED'})
})

it('写入结果未知不会自动重发',async()=>{
  const fetch=vi.fn().mockRejectedValue(new TypeError('connection interrupted: private transport detail'))
  vi.stubGlobal('fetch',fetch)
  await expect(request('/api/command',{method:'POST'})).rejects.toMatchObject({code:'CONTROL_CONNECTION_FAILED',requestOutcome:'UNKNOWN',message:'与界鉴服务的连接已中断。请检查本机服务；已提交的操作先查询原回执。'})
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('保留错误编号与明确的执行事实，任意细节不进入页面错误对象',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({schema_version:'1',error:{code:'NOT_READY',message:'尚未就绪',details:{execution_started:false,unrelated:'private detail'}},trace_id:'trace-test'}),{status:409})))
  try{await request('/api/failure');throw new Error('expected rejection')}catch(error){
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({code:'NOT_READY',traceId:'trace-test',executionStarted:false})
    expect(error).not.toHaveProperty('details')
  }
})
