// 只记录验证状态、文件和耗时，参数与异常正文留在本地控制台。
import {mkdirSync,writeFileSync,renameSync} from 'node:fs'
import {dirname,relative} from 'node:path'

export default class QualityReporter{
  onInit(context){this.context=context;this.started=Date.now();this.write({status:'RUNNING'})}
  write(value){
    const destination=process.env.JIEJIAN_TEST_REPORT
    if(!destination)return
    mkdirSync(dirname(destination),{recursive:true})
    writeFileSync(destination+'.tmp',JSON.stringify({schema_version:'1',engine:'vitest',...value},null,2))
    renameSync(destination+'.tmp',destination)
  }
  onFinished(files=[],errors=[]){
    let collected=0,failed=errors.length,skipped=0
    const visit=task=>{
      if(task.type==='test'){collected++;if(task.result?.state==='fail')failed++;if(['skip','todo'].includes(task.mode))skipped++}
      for(const child of task.tasks??[])visit(child)
    }
    files.forEach(visit)
    if(files.some(file=>file.result?.state==='fail')&&!failed)failed++
    this.write({status:failed?'FAILED':!collected?'EMPTY':skipped?'INCOMPLETE':'PASSED',collected,failures:failed,skipped,seconds:(Date.now()-this.started)/1000,files:files.map(file=>({path:relative(this.context.config.root,file.filepath).replaceAll('\\','/'),outcome:file.result?.state??'unknown'}))})
  }
}
