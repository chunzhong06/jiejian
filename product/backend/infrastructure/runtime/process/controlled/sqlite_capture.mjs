import path from 'node:path'
import crypto from 'node:crypto'

const quote=value=>'"'+value.replaceAll('"','""')+'"'
const normalize=value=>process.platform==='win32'?value.toLowerCase():value

export function instrumentDatabase(Database,{root,dataRoot,databases,scope,capture}) {
  return new Proxy(Database,{construct(Constructor,args,newTarget) {
    const filename=typeof args[0]==='string'?path.resolve(args[0]):null
    const selected=databases.find(item=>normalize(path.resolve(root,item.relative_path))===normalize(filename??''))
    if(!selected){if(scope())scope().auditIncomplete=true;return Reflect.construct(Constructor,args,Constructor)}
    const index=databases.indexOf(selected)
    const actual=path.join(dataRoot,'sqlite',String(index)+'.sqlite')
    const database=Reflect.construct(Constructor,[actual,...args.slice(1)],Constructor)
    const originalPrepare=database.prepare.bind(database),originalExec=database.exec.bind(database)
    let transaction=crypto.randomBytes(16).toString('hex')
    const originalTransaction=database.transaction.bind(database)
    // 驱动的 transaction() 不经过公开 exec()；外层事务必须另取提交标识，嵌套 savepoint 沿用它。
    database.transaction=function(callback) {
      const variants=new Map()
      const wrap=fn=>{
        if(!variants.has(fn)){
          const wrapped=function(...values){if(!database.inTransaction)transaction=crypto.randomBytes(16).toString('hex');return Reflect.apply(fn,this,values)}
          variants.set(fn,wrapped)
          for(const key of ['deferred','immediate','exclusive','default'])if(typeof fn[key]==='function')Object.defineProperty(wrapped,key,{value:wrap(fn[key])})
        }
        return variants.get(fn)
      }
      return wrap(originalTransaction(callback))
    }
    database.function('_jj_nonce',()=>{const current=scope(); if(current?.ending){current.auditIncomplete=true;return 'late:'+current.nonce}return current?.nonce??null})
    database.function('_jj_transaction',()=>transaction)
    for(const selectedTable of selected.tables) {
      const table=quote(selectedTable.table)
      const columns=originalPrepare('SELECT name FROM pragma_table_info(?)').all(selectedTable.table).map(row=>row.name)
      const fields=[selectedTable.resource_column,selectedTable.owner_column,...selectedTable.fields]
      if(fields.some(field=>!columns.includes(field)))throw Error('SQLITE_CAPTURE_MAPPING_MISSING')
      const projection=side=>'json_object('+selectedTable.fields.flatMap(field=>["'"+field+"'",`CASE WHEN typeof(${side}.${quote(field)})='blob' THEN NULL ELSE ${side}.${quote(field)} END`]).join(',')+')'
      const identifier=(side,column)=>`CASE WHEN typeof(${side}.${quote(column)}) IN ('null','blob') THEN '__jiejian_unsupported__' ELSE CAST(${side}.${quote(column)} AS TEXT) END`
      const key=side=>identifier(side,selectedTable.resource_column)
      const owner=side=>identifier(side,selectedTable.owner_column)
      for(const [kind,before,after] of [['INSERT',false,true],['UPDATE',true,true],['DELETE',true,false]]) {
        const name=quote('_jj_'+index+'_'+selectedTable.table+'_'+kind.toLowerCase())
        const resource=key(after?'new':'old')
        const unsupported=(side)=>[...selectedTable.fields.map(field=>`typeof(${side}.${quote(field)})='blob'`),...[selectedTable.resource_column,selectedTable.owner_column].map(field=>`typeof(${side}.${quote(field)}) IN ('null','blob')`)].join(' OR ')
        // 观察不能使原本合法的 BLOB 写入失败；标记未知，由独立 reader 拒绝据此判断缺少结果。
        const invalid=[...(before?[unsupported('old')]:[]),...(after?[unsupported('new')]:[])].join(' OR ')
        const statement=`CREATE TRIGGER IF NOT EXISTS ${name} AFTER ${kind} ON ${table} BEGIN
          INSERT INTO _jj_rows(table_name,resource_id,owner_id,kind,request_nonce,transaction_id,before_data,after_data,identity_changed)
          VALUES('${selectedTable.table}',${resource},${owner(after?'new':'old')},'${kind}',_jj_nonce(),_jj_transaction(),${before?projection('old'):'NULL'},${after?projection('new'):'NULL'},CASE WHEN ${invalid} THEN 2 ELSE ${kind==='UPDATE'?`(${key('old')} IS NOT ${key('new')} OR ${owner('old')} IS NOT ${owner('new')})`:'0'} END); END;`
        originalExec(statement)
      }
    }
    const invoke=(operation,fn,values)=>{
      if(!database.inTransaction)transaction=crypto.randomBytes(16).toString('hex')
      try{return capture('SQLITE',operation,()=>Reflect.apply(fn,database,values))}
      catch(error){if(scope()&&String(error?.code??'').startsWith('SQLITE_')&&String(error?.message??'').includes('_jj_'))scope().auditIncomplete=true;throw error}
    }
    database.exec=function(...values) {
      if(scope()&&values[0]?.trim().replace(/;\s*$/,'').includes(';'))scope().auditIncomplete=true
      return invoke('EXEC',originalExec,values)
    }
    database.prepare=function(...values) {
      const statement=originalPrepare(...values),wrappers=new Map()
      return new Proxy(statement,{get(target,key) {
        const value=Reflect.get(target,key,target)
        if(typeof value!=='function')return value
        if(!wrappers.has(key))wrappers.set(key,function(...input) {
          if(['run','get','all'].includes(key))return invoke(key.toUpperCase(),(...args)=>Reflect.apply(value,target,args),input)
          if(key==='iterate') {
            const iterator=Reflect.apply(value,target,input)
            const current=scope()
            if(current)current.pending+=1
            let closed=false
            const close=()=>{if(!closed){closed=true;if(current)current.pending-=1}}
            return {[Symbol.iterator](){return this},next(...args){try{const result=iterator.next(...args);if(result.done)close();return result}catch(error){close();throw error}},return(...args){try{return iterator.return?.(...args)??{done:true}}finally{close()}}}
          }
          const result=Reflect.apply(value,target,input)
          return result===target?this:result
        })
        return wrappers.get(key)
      }})
    }
    return database
  }})
}
