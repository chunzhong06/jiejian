// 受控 ESM 执行器：只链接冻结模块及固定内建模块；不生成运行对应或权限结论。
// VM 仅限定支持的加载方式，不是对抗恶意应用的安全沙箱；进程和端口由外部监督者核对。
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import vm from 'node:vm'
import http from 'node:http'
import { AsyncLocalStorage } from 'node:async_hooks'
import { fileURLToPath, pathToFileURL } from 'node:url'

const fail = () => { throw new Error('NODE_RUNTIME_INPUT_INVALID') }
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex')
const samePath = (a, b) => process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b
const allowedBuiltins = new Set(['node:assert','node:assert/strict','node:buffer','node:crypto','node:events',
  'node:fs','node:fs/promises','node:http','node:https','node:path','node:querystring','node:stream',
  'node:stream/promises','node:string_decoder','node:timers','node:timers/promises','node:url','node:util','node:zlib','node:sqlite'])

function bytes(file, limit) {
  if (fs.lstatSync(file).isSymbolicLink() || !samePath(fs.realpathSync(file), path.resolve(file))) fail()
  const fd = fs.openSync(file, 'r')
  try {
    if (!fs.fstatSync(fd).isFile() || fs.fstatSync(fd).size > limit) fail()
    const buffer = Buffer.alloc(limit + 1)
    let count = 0
    while (count < buffer.length) {
      const read = fs.readSync(fd, buffer, count, buffer.length - count, null)
      if (!read) break
      count += read
    }
    if (count > limit) fail()
    return buffer.subarray(0, count)
  } finally { fs.closeSync(fd) }
}

async function main() {
  if (process.argv.length !== 5 || !process.execArgv.includes('--permission') || !process.permission?.has('fs.read', process.argv[2])) fail()
  const [manifestFile, expectedRawHash, dataRoot] = process.argv.slice(2)
  const raw = bytes(manifestFile, 262144)
  if (sha(raw) !== expectedRawHash) fail()
  const manifest = JSON.parse(raw.toString('utf8'))
  const keys = ['schema_version','mode','instance_id','project_id','entry','port','files',
    'source_fingerprint','interpreter_fingerprint','executor_fingerprint']
  if (Object.keys(manifest).sort().join() !== keys.sort().join() || manifest.schema_version !== '1'
      || manifest.mode !== 'CONTROLLED_NODE_ESM' || !Number.isInteger(manifest.port)
      || manifest.port < 1024 || manifest.port > 65535 || !Array.isArray(manifest.files)
      || !manifest.files.length || manifest.files.length > 512) fail()
  if (sha(bytes(fileURLToPath(import.meta.url), 262144)) !== manifest.executor_fingerprint) fail()
  // 解释器摘要由外层 Worker 启动前核对；执行器不能用自己的声明替代内核所有权。
  const root = path.join(path.dirname(manifestFile), 'source')
  const records = new Map()
  let total = 0
  const sourceHash = crypto.createHash('sha256')
  for (const item of manifest.files) {
    if (Object.keys(item).sort().join() !== ['relative_path','sha256','size'].sort().join()
        || typeof item.relative_path !== 'string' || !Number.isInteger(item.size) || item.size < 0
        || !/^[a-f0-9]{64}$/.test(item.sha256) || records.has(item.relative_path.toLowerCase())) fail()
    const parts = item.relative_path.split('/')
    if (!/\.(mjs|json|html|css|svg)$/.test(item.relative_path)) fail()
    if (parts.some(part => !part || part === '.' || part === '..' || /[\\:<>{}"|?*\x00-\x1f]/.test(part)
        || part.trim() !== part || part.endsWith('.'))) fail()
    total += item.size
    if (total > 33554432) fail()
    const file = path.join(root, ...parts)
    const content = bytes(file, item.size)
    if (content.length !== item.size || sha(content) !== item.sha256) fail()
    records.set(item.relative_path.toLowerCase(), {file, content, relative: item.relative_path})
    sourceHash.update(item.relative_path); sourceHash.update('\0'); sourceHash.update(Buffer.from(item.sha256,'hex'))
  }
  if (sourceHash.digest('hex') !== manifest.source_fingerprint || !records.has(manifest.entry.toLowerCase())) fail()
  const gate = path.join(path.dirname(manifestFile), 'start.gate')
  const deadline = Date.now() + 10000
  while (!fs.existsSync(gate)) {
    if (Date.now() >= deadline) fail()
    await new Promise(resolve => setTimeout(resolve, 10))
  }
  if (bytes(gate, 64).toString('ascii') !== expectedRawHash) fail()
  if (!fs.statSync(dataRoot).isDirectory() || !samePath(fs.realpathSync(dataRoot), path.resolve(dataRoot))) fail()
  const context = vm.createContext({Buffer, URL, URLSearchParams, TextEncoder, TextDecoder, structuredClone,
    setTimeout, clearTimeout, setInterval, clearInterval, setImmediate, clearImmediate, queueMicrotask,
    console, process: Object.freeze({env:Object.freeze({PORT:String(manifest.port),JIEJIAN_DATA_DIR:dataRoot}),
      pid:process.pid, cwd:()=>dataRoot, argv:Object.freeze(['node', manifest.entry])})},
    {codeGeneration:{strings:false,wasm:false}})
  const cache = new Map()
  const builtinCache = new Map()
  let recordModule
  // 业务客户端只能提交有限同步事务；记录服务在 Worker 内，能力令牌不暴露给应用模块。
  const recordOrigin = process.env.JIEJIAN_RECORD_ORIGIN
  const recordCapability = process.env.JIEJIAN_RECORD_CAPABILITY
  const recordControl = process.env.JIEJIAN_RECORD_CONTROL
  const requestScopes = new AsyncLocalStorage()
  const adapterNames = new Set(['node:http'])
  const methodName = method => ['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS','CONNECT','TRACE'].includes(method) ? method : 'OTHER'
  const nowUs = () => Math.trunc(performance.timeOrigin * 1000 + performance.now() * 1000)
  function sourcePosition() {
    const stack = new Error().stack?.split('\n') ?? []
    for (const line of stack) {
      const match = line.match(/(?:\(|at )([^()]+\.mjs):(\d+):\d+\)?$/)
      if (match && records.get(match[1].toLowerCase())?.relative === match[1]) return match[1]+':'+match[2]
    }
    return null
  }
  function startCall(scope, kind, operation, extra = {}) {
    const capture = scope?.capture
    if (!capture || scope.ending) return null
    if (capture.events.length >= 128) { capture.dropped_count += 1; return null }
    const event = {event_id:'call_'+crypto.randomBytes(16).toString('hex'),
      parent_event_id:capture.events[0]?.event_id ?? null, kind, operation, started_at_us:nowUs(),
      duration_us:0, outcome:'INCOMPLETE', source_location:sourcePosition(), http_method:null, http_status:null, ...extra}
    capture.events.push(event)
    return event
  }
  function finishCall(event, outcome = 'OK', extra = {}) {
    if (event) Object.assign(event,{outcome,duration_us:Math.max(0,nowUs()-event.started_at_us)},extra)
  }
  function captureSync(kind, operation, invoke) {
    const event = startCall(requestScopes.getStore(),kind,operation)
    try { const result = invoke(); finishCall(event); return result }
    catch (error) { finishCall(event,'ERROR'); throw error }
  }
  function activitySnapshot(scope, closed) {
    // 单次请求有界缓冲，随闭合回执一次保存；崩溃时只留下预先持久化的未闭合入口。
    if (!scope.capture) return undefined
    return {...scope.capture, adapters:[...adapterNames].sort(), complete:closed && !scope.capture.dropped_count
      && scope.capture.events.every(event=>event.outcome!=='INCOMPLETE'),
      events:scope.capture.events.map(event=>({...event,duration_us:event.outcome==='INCOMPLETE'
        ? Math.max(0,nowUs()-event.started_at_us) : event.duration_us}))}
  }
  function instrumentSqlite(namespace) {
    class CapturedDatabase extends namespace.DatabaseSync {
      exec(...args) { return captureSync('SQLITE','EXEC',()=>super.exec(...args)) }
      prepare(...args) {
        let statement
        try { statement = super.prepare(...args) }
        catch (error) { const event=startCall(requestScopes.getStore(),'SQLITE','PREPARE'); finishCall(event,'ERROR'); throw error }
        const methods = new Map()
        return new Proxy(statement,{get(target,key) {
          const value = Reflect.get(target,key,target)
          if (typeof value !== 'function') return value
          if (!methods.has(key)) methods.set(key, (...values) => {
            if (['run','get','all'].includes(key)) return captureSync('SQLITE',key.toUpperCase(),()=>Reflect.apply(value,target,values))
            if (key !== 'iterate') return Reflect.apply(value,target,values)
            const event = startCall(requestScopes.getStore(),'SQLITE','ITERATE')
            let iterator
            try { iterator = Reflect.apply(value,target,values) }
            catch (error) { finishCall(event,'ERROR'); throw error }
            return {
              [Symbol.iterator]() { return this },
              next(...input) {
                try { const result=iterator.next(...input); if (result.done) finishCall(event); return result }
                catch (error) { finishCall(event,'ERROR'); throw error }
              },
              return(...input) { try { return iterator.return ? iterator.return(...input) : {done:true} } finally { finishCall(event) } },
            }
          })
          return methods.get(key)
        }})
      }
    }
    return {...namespace, DatabaseSync:CapturedDatabase}
  }
  function instrumentFiles(namespace, promises = false) {
    const wrapped = {...namespace}
    for (const [base,operation] of [['readFile','READ'],['writeFile','WRITE'],['appendFile','APPEND']]) {
      if (!promises) wrapped[base+'Sync'] = (...args) => captureSync('FILESYSTEM',operation,()=>namespace[base+'Sync'](...args))
      wrapped[base] = (...args) => {
        const event = startCall(requestScopes.getStore(),'FILESYSTEM',operation)
        if (promises) {
          try { return namespace[base](...args).then(value=>{finishCall(event);return value},error=>{finishCall(event,'ERROR');throw error}) }
          catch (error) { finishCall(event,'ERROR'); throw error }
        }
        const callback = args.at(-1)
        if (typeof callback === 'function') args[args.length-1]=function(error,...values) { finishCall(event,error?'ERROR':'OK'); return Reflect.apply(callback,this,[error,...values]) }
        try { return namespace[base](...args) } catch (error) { finishCall(event,'ERROR'); throw error }
      }
    }
    if (!promises) wrapped.promises=instrumentFiles(namespace.promises,true)
    return wrapped
  }
  function instrumentClient(namespace) {
    function request(...args) {
      const event = startCall(requestScopes.getStore(),'HTTP_CLIENT','REQUEST')
      let outgoing
      try { outgoing=namespace.request(...args) }
      catch (error) { finishCall(event,'ERROR'); throw error }
      if (event) event.http_method=methodName(outgoing.method)
      outgoing.once('response',incoming=>finishCall(event,'OK',{http_status:incoming.statusCode}))
      outgoing.once('error',()=>finishCall(event,'ERROR'))
      return outgoing
    }
    return {...namespace,request,get:(...args)=>{const outgoing=request(...args);outgoing.end();return outgoing}}
  }
  async function recordRequest(endpoint, payload, control = false) {
    if (!/^http:\/\/127\.0\.0\.1:[0-9]+$/.test(recordOrigin ?? '') || !recordCapability) throw new Error('RECORD_PROVIDER_UNAVAILABLE')
    const body = JSON.stringify(payload)
    if (Buffer.byteLength(body) > 98304) throw new Error('RECORD_INPUT_LIMIT')
    const response = await fetch(recordOrigin + endpoint, {method:'POST',body,
      headers:{'Content-Type':'application/json',Authorization:'Bearer ' + (control ? recordControl : recordCapability)},signal:AbortSignal.timeout(5000)})
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : 'RECORD_PROVIDER_UNAVAILABLE')
    return data.data
  }
  function recordScope(scope) {
    scope.opening ??= recordRequest('/scope/open',{request_nonce:scope.nonce,request_digest:scope.digest,
      activity:activitySnapshot(scope,false)},true).then(record=>scope.id=record.scope_id)
    return scope.opening
  }
  function openCollection(collection) {
    if (typeof collection !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(collection)) throw new Error('RECORD_COLLECTION_INVALID')
    return Object.freeze({
      seed: async (resource_id, owner_id, data) => {
        const scope = requestScopes.getStore()
        if (!scope) return recordRequest('/resource/seed', {schema_version:'1',collection,resource_id,owner_id,data})
        if (scope.ending) throw new Error('RECORD_SCOPE_CLOSED')
        scope.pending += 1
        try {
          return await recordRequest('/resource/seed', {schema_version:'2',collection,resource_id,owner_id,data,scope_id:await recordScope(scope)})
        } finally { scope.pending -= 1 }
      },
      read: resource_id => recordRequest('/resource/read', {collection,resource_id}),
      remove: async (resource_id, expected_version) => {
        const scope = requestScopes.getStore()
        if (!scope || scope.ending) throw new Error('RECORD_SCOPE_CLOSED')
        scope.pending += 1
        try {
          return await recordRequest('/resource/remove', {schema_version:'1',collection,resource_id,expected_version,scope_id:await recordScope(scope)})
        } finally { scope.pending -= 1 }
      },
      trace: async (resource_id, event) => {
        const scope = requestScopes.getStore()
        if (!scope || scope.ending) throw new Error('RECORD_SCOPE_CLOSED')
        scope.pending += 1
        try {
          // scope 由宿主绑定，应用只提交显式父事件与有限公开标识。
          const receipt = await recordRequest('/trace/append', {schema_version:'1',collection,resource_id,event,scope_id:await recordScope(scope)})
          if (receipt.schema_version !== '1' || typeof receipt.event?.event_id !== 'string') throw new Error('TRACE_RECEIPT_INVALID')
          return receipt.event
        } finally { scope.pending -= 1 }
      },
      transact: async input => {
        const scope = requestScopes.getStore()
        if (!scope || scope.ending) throw new Error('RECORD_SCOPE_CLOSED')
        scope.pending += 1
        try {
          // 操作关联由宿主注入，业务模块不能回放旧事务或借用另一请求的完成记录。
          return await recordRequest('/resource/transact', {...input,schema_version:'2',collection,
            scope_id:await recordScope(scope),request_key:crypto.randomBytes(32).toString('hex')})
        } finally { scope.pending -= 1 }
      },
    })
  }
  class ScopedServer extends http.Server {
    emit(event, ...args) {
      if (event !== 'request') return super.emit(event,...args)
      const [request,response] = args
      const supplied = request.headers['x-jiejian-request-nonce']
      const nonce = typeof supplied === 'string' && /^[a-f0-9]{64}$/.test(supplied) ? supplied : crypto.randomBytes(32).toString('hex')
      const digest = sha(Buffer.from(request.method.toUpperCase()+'\n'+request.url))
      const scope = {nonce,digest,pending:0,ending:false,capture:typeof supplied==='string' && /^[a-f0-9]{64}$/.test(supplied)
        ? {request_nonce:nonce,request_digest:digest,collector:'CONTROLLED_NODE',dropped_count:0,events:[]} : null}
      startCall(scope,'HTTP_SERVER','REQUEST',{http_method:methodName(request.method)})
      const end = response.end.bind(response)
      response.end = (...endArgs) => {
        if (scope.ending) return response
        finishCall(scope.capture?.events[0],'OK',{http_status:response.statusCode})
        scope.ending = true
        // 检查请求及真实业务写入仍先确认持久闭合；普通只读请求不创建记录日志。
        if (!scope.opening) return end(...endArgs)
        const complete=scope.pending===0
        scope.opening.then(id=>recordRequest('/scope/close',{scope_id:id,complete,
          activity:activitySnapshot(scope,complete)},true)).then(()=>end(...endArgs),()=>response.destroy())
        return response
      }
      response.once('close',()=>{
        if (!scope.ending) {
          scope.ending=true
          scope.opening?.then(id=>recordRequest('/scope/close',{scope_id:id,complete:false,
            activity:activitySnapshot(scope,false)},true)).catch(()=>{})
        }
      })
      const invoke=()=>{if(!response.destroyed)requestScopes.run(scope,()=>super.emit(event,...args))}
      if(scope.capture) recordScope(scope).then(invoke,()=>response.destroy())
      else invoke()
      return true
    }
  }
  const scopedHttp = Object.freeze({...instrumentClient(http),Server:ScopedServer,createServer:(...args)=>new ScopedServer(...args)})
  function moduleFor(relative) {
    const record = records.get(relative.toLowerCase())
    if (!record || record.relative !== relative || !relative.endsWith('.mjs')) fail()
    if (!cache.has(relative)) cache.set(relative, new vm.SourceTextModule(new TextDecoder('utf-8',{fatal:true}).decode(record.content), {
      context, identifier:relative,
      initializeImportMeta(meta) {meta.url = pathToFileURL(record.file).href},
      importModuleDynamically() {throw new Error('NODE_DYNAMIC_IMPORT_UNSUPPORTED')},
    }))
    return cache.get(relative)
  }
  const entry = moduleFor(manifest.entry)
  await entry.link(async (specifier, parent, extra) => {
    if (Object.keys(extra.attributes ?? {}).length) fail()
    if (specifier === 'jiejian:records') {
      recordModule ??= new vm.SyntheticModule(['openCollection'], function() {this.setExport('openCollection',openCollection)}, {context,identifier:specifier})
      return recordModule
    }
    if (allowedBuiltins.has(specifier)) {
      if (!builtinCache.has(specifier)) builtinCache.set(specifier, import(specifier).then(namespace => {
        if (['node:http','node:https','node:sqlite','node:fs','node:fs/promises'].includes(specifier)) adapterNames.add(specifier)
        const captured = specifier==='node:http' ? scopedHttp : specifier==='node:https' ? instrumentClient(namespace.default)
          : specifier==='node:sqlite' ? instrumentSqlite(namespace) : specifier==='node:fs' ? instrumentFiles(namespace.default)
          : specifier==='node:fs/promises' ? instrumentFiles(namespace.default,true) : namespace
        const names = Object.keys(namespace)
        return new vm.SyntheticModule(names, function() {
          for (const name of names) this.setExport(name,name==='default' && captured!==namespace ? captured : captured[name] ?? namespace[name])
        }, {context,identifier:specifier})
      }))
      return builtinCache.get(specifier)
    }
    if (!specifier.startsWith('./') && !specifier.startsWith('../')) fail()
    if (/[\\%?#:]/.test(specifier)) fail()
    const relative = path.posix.normalize(path.posix.join(path.posix.dirname(parent.identifier), specifier))
    if (relative.startsWith('../') || path.posix.isAbsolute(relative)) fail()
    return moduleFor(relative)
  })
  await entry.evaluate({timeout:5000})
}

// 失败立即关闭本进程；不能因应用已监听而在模块加载失败后仍留下可被误认的端口。
// 不输出源码、响应或异常正文；外层监督者根据退出与内核事实发布有限错误。
process.on('uncaughtException', () => process.exit(1))
process.on('unhandledRejection', () => process.exit(1))
main().catch(() => process.exit(1))
