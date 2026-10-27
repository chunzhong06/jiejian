import {expect,it,vi} from 'vitest'
import {request,ApiError} from './http'

const response=(data:unknown,status=200)=>new Response(JSON.stringify({schema_version:'1',data}),{status})

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
  const fetch=vi.fn().mockRejectedValue(new TypeError('connection interrupted'))
  vi.stubGlobal('fetch',fetch)
  await expect(request('/api/command',{method:'POST'})).rejects.toThrow('connection interrupted')
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
