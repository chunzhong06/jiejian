// Promise 驱动在每条语句前重新绑定请求；连接串、SQL 和参数不进入记录。
import crypto from 'node:crypto'

function connectionState(engine,raw,scope,query=raw.query.bind(raw)) {
  const original=query
  let tail=Promise.resolve(),transaction=null,owner=null,autocommit=true,uncertain=false
  const invalidate=current=>{if(current)current.auditIncomplete=true;if(owner)owner.auditIncomplete=true}
  function finishTransaction() {if(owner)owner.pending-=1;owner=null;transaction=null}
  function beginTransaction(current) {if(!transaction){transaction=crypto.randomBytes(16).toString('hex');owner=current;if(owner)owner.pending+=1}}
  async function perform(method,args) {
    const current=scope(),input=args[0]
    if(args.some(item=>typeof item==='function')) {invalidate(current);throw Error('DATABASE_CAPTURE_REQUIRES_PROMISE_QUERY')}
    const sql=typeof input==='string'?input:input?.text??input?.sql
    if(typeof sql!=='string'){invalidate(current);throw Error('DATABASE_CAPTURE_QUERY_UNSUPPORTED')}
    const command=sql.trim().replace(/;\s*$/,'').replace(/\s+/g,' ').toUpperCase()
    // 不解析任意 SQL 以猜测事务闭合；未知事务/DDL/多语句保持缺口。
    const known=/^(SELECT|INSERT|UPDATE|DELETE)\b/.test(command)||/^(BEGIN(?: WORK| TRANSACTION)?|START TRANSACTION|COMMIT(?: WORK)?|ROLLBACK(?: WORK)?|ROLLBACK TO(?: SAVEPOINT)? [A-Z_][A-Z0-9_]*|SAVEPOINT [A-Z_][A-Z0-9_]*|RELEASE SAVEPOINT [A-Z_][A-Z0-9_]*|SET (?:SESSION )?AUTOCOMMIT\s*=\s*[01])$/.test(command)
    if(!known||command.includes(';')){uncertain=true;invalidate(current)}
    if(uncertain)invalidate(current)
    if(transaction&&owner!==current)invalidate(current)
    const rollback=/^ROLLBACK\b/.test(command),ending=/^(COMMIT|ROLLBACK(?: WORK)?)$/.test(command)
    if(engine==='MYSQL'&&!autocommit&&!transaction&&!ending)beginTransaction(current)
    const nonce=current?(current.ending?'late:':'')+current.nonce:null
    if(current?.ending)invalidate(current)
    if(engine==='POSTGRESQL') {
      // 失败事务中的 ROLLBACK 必须能执行；保存点恢复后的下一条语句再次设定上下文。
      if(!rollback&&!ending)await original("SELECT set_config('jiejian.nonce',$1,false)",[nonce??''])
    } else {
      if(!transaction)transaction=crypto.randomBytes(16).toString('hex')
      await original('SET @jiejian_nonce=?, @jiejian_transaction=?',[nonce,transaction])
    }
    let result
    try {result=await (method==='execute'?raw.__jiejianExecute:original)(...args)}
    catch(error){if(!transaction)invalidate(current);throw error}
    if(/^(BEGIN|START TRANSACTION)\b/.test(command)) {
      // MySQL 上 BEGIN 隐式结束旧事务；跨请求所有权依然不能补认。
      if(owner)finishTransaction()
      transaction=null;beginTransaction(current)
    } else if(ending||/^SET (?:SESSION )?AUTOCOMMIT\s*=\s*1$/.test(command)){finishTransaction();uncertain=false}
    if(engine==='MYSQL') {
      if(/^SET (?:SESSION )?AUTOCOMMIT\s*=\s*0$/.test(command)){autocommit=false;transaction=null}
      if(/^SET (?:SESSION )?AUTOCOMMIT\s*=\s*1$/.test(command))autocommit=true
      if(autocommit&&!owner)transaction=null
    }
    return result
  }
  return {
    invoke(method,args) {
      const current=scope()
      if(current)current.pending+=1
      const result=tail.then(()=>perform(method,args))
      tail=result.catch(()=>{})
      return result.finally(()=>{if(current)current.pending-=1})
    },
    release() {
      if(transaction&&owner)invalidate(scope())
      // 驱动归还连接是同步操作，不能异步清理后再归还；脏连接销毁并保留未闭合事实。
      return Boolean(owner)||!autocommit||uncertain
    },
    detach(release) {
      return tail.then(async()=>{
        if(engine==='POSTGRESQL')await original("SELECT set_config('jiejian.nonce','',false)")
        else await original('SET @jiejian_nonce=NULL,@jiejian_transaction=NULL')
      }).then(()=>release(false),()=>release(true))
    },
    closed(){if(owner){invalidate(owner);finishTransaction()}},
  }
}

function matches(spec,engine,config) {
  return spec.engine===engine&&(config.host==='127.0.0.1'||config.host==='localhost')
    && Number(config.port??(engine==='POSTGRESQL'?5432:3306))===spec.port
    && config.database===spec.database&&config.user===spec.username
}

export function instrumentPgClient(Client,{databases,scope}) {
  return class CapturedClient extends Client {
    constructor(...args) {
      super(...args)
      this.__jiejianDeclared=databases.some(spec=>matches(spec,'POSTGRESQL',this.connectionParameters))
      this.__jiejianState=connectionState('POSTGRESQL',this,scope,super.query.bind(this))
    }
    query(...args) {
      if(!this.__jiejianDeclared){if(scope())scope().auditIncomplete=true;return super.query(...args)}
      return this.__jiejianState.invoke('query',args)
    }
    end(...args){this.__jiejianState.closed();return super.end(...args)}
  }
}

export function instrumentPgPool(Pool) {
  return class CapturedPool extends Pool {
    async connect(...args) {
      if(args.length)throw Error('DATABASE_CAPTURE_REQUIRES_PROMISE_QUERY')
      const client=await super.connect(),release=client.release
      client.release=error=>{
        const dirty=client.__jiejianState?.release()
        if(dirty)client.__jiejianState.closed()
        if(error||dirty)return release(error||dirty)
        return client.__jiejianState?client.__jiejianState.detach(release):release()
      }
      return client
    }
    async query(...args) {
      if(args.some(value=>typeof value==='function'))throw Error('DATABASE_CAPTURE_REQUIRES_PROMISE_QUERY')
      const client=await this.connect()
      try{return await client.query(...args)}finally{await client.release()}
    }
  }
}

export function instrumentMysqlPromise(namespace,{databases,scope}) {
  const cache=new WeakMap()
  const wrap=raw=>{
    if(cache.has(raw))return cache.get(raw)
    const config=raw.connection?.config??raw.pool?.config?.connectionConfig
    const declared=config&&databases.some(spec=>matches(spec,'MYSQL',config))
    if(!declared){if(scope())scope().auditIncomplete=true;return raw}
    const originalExecute=raw.execute?.bind(raw)
    if(originalExecute)raw.__jiejianExecute=originalExecute
    const state=connectionState('MYSQL',raw,scope)
    const proxy=new Proxy(raw,{get(target,key) {
      if(['query','execute'].includes(key))return (...args)=>state.invoke(key,args)
      if(key==='beginTransaction')return ()=>state.invoke('query',['BEGIN'])
      if(key==='commit')return ()=>state.invoke('query',['COMMIT'])
      if(key==='rollback')return ()=>state.invoke('query',['ROLLBACK'])
      if(key==='release')return ()=>{if(state.release()){state.closed();target.destroy()}else return state.detach(dirty=>dirty?target.destroy():target.release())}
      if(['end','destroy'].includes(key))return (...args)=>{state.closed();return target[key](...args)}
      if(['connection','pool'].includes(key)&&scope())scope().auditIncomplete=true
      const value=Reflect.get(target,key,target)
      return typeof value==='function'?value.bind(target):value
    }})
    cache.set(raw,proxy);return proxy
  }
  const pool=raw=>new Proxy(raw,{get(target,key) {
    if(key==='getConnection')return async()=>wrap(await target.getConnection())
    if(key==='releaseConnection')return connection=>connection.release()
    if(['query','execute'].includes(key))return async(...args)=>{const client=wrap(await target.getConnection());try{return await client[key](...args)}finally{await client.release()}}
    const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value
  }})
  return {...namespace,createConnection:async(...args)=>wrap(await namespace.createConnection(...args)),createPool:(...args)=>pool(namespace.createPool(...args))}
}
