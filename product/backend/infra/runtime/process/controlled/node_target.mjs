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
  function openCollection(collection) {
    if (typeof collection !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(collection)) throw new Error('RECORD_COLLECTION_INVALID')
    return Object.freeze({
      seed: (resource_id, owner_id, data) => recordRequest('/resource/seed', {schema_version:'1',collection,resource_id,owner_id,data}),
      read: resource_id => recordRequest('/resource/read', {collection,resource_id}),
      transact: async input => {
        const scope = requestScopes.getStore()
        if (!scope || scope.ending) throw new Error('RECORD_SCOPE_CLOSED')
        scope.pending += 1
        try {
          // 操作关联由宿主注入，业务模块不能回放旧事务或借用另一请求的完成记录。
          return await recordRequest('/resource/transact', {...input,schema_version:'1',collection,
            scope_id:scope.id,request_key:crypto.randomBytes(32).toString('hex')})
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
      recordRequest('/scope/open',{request_nonce:nonce,request_digest:digest},true).then(record => {
        const scope = {id:record.scope_id,pending:0,ending:false}
        const end = response.end.bind(response)
        response.end = (...endArgs) => {
          if (scope.ending) return response
          scope.ending = true
          // 先冻结完成边界再结束响应；未等待的业务写入不能得到完整的“没有发生”证明。
          recordRequest('/scope/close',{scope_id:scope.id,complete:scope.pending===0},true)
            .then(()=>end(...endArgs),()=>response.destroy())
          return response
        }
        response.once('close',()=>{
          if (!scope.ending) {
            scope.ending=true
            recordRequest('/scope/close',{scope_id:scope.id,complete:false},true).catch(()=>{})
          }
        })
        requestScopes.run(scope,()=>super.emit(event,...args))
      }).catch(()=>response.destroy())
      return true
    }
  }
  const scopedHttp = Object.freeze({...http,Server:ScopedServer,createServer:(...args)=>new ScopedServer(...args)})
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
        const names = Object.keys(namespace)
        return new vm.SyntheticModule(names, function() {
          for (const name of names) this.setExport(name,specifier==='node:http'
            ? (name==='default' ? scopedHttp : scopedHttp[name] ?? namespace[name]) : namespace[name])
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
