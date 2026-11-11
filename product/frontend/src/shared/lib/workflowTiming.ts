/** 显式本地诊断会话；只收集固定阶段和时长，不记录URL、读取键或表单。 */
type Phase='http.read'|'http.command'|'view.read'
type Outcome='COMPLETE'|'FAILED'|'ABORTED'
type RecordItem={sequence:number;phase:Phase;duration_ms:number|null;outcome:Outcome}
const records:RecordItem[]=[]
let sequence=0,dropped=0
const environment=globalThis as typeof globalThis&{__JIEJIAN_WORKFLOW_TIMING__?:boolean;__JIEJIAN_TIMINGS__?:()=>unknown}
const noop=(_outcome?:Outcome)=>{}
if(environment.__JIEJIAN_WORKFLOW_TIMING__===true)environment.__JIEJIAN_TIMINGS__=()=>({schema_version:'1',clock:'browser_monotonic',stages:[...records],dropped})
function readClock(){try{const value=performance.now();return Number.isFinite(value)&&value>=0?value:null}catch{return null}}
// User Timing 是可选诊断：浏览器禁用、容量或时钟异常都不能影响原读取和提交。
function userTiming(action:()=>void){try{action()}catch{}}

export function beginWorkflowTiming(phase:Phase):(outcome?:Outcome)=>void{
 if(environment.__JIEJIAN_WORKFLOW_TIMING__!==true)return noop
 if(sequence>=2048){dropped++;return noop}
 const id=++sequence,name='jiejian:'+phase+':'+id,started=readClock()
 userTiming(()=>performance.mark(name+':start'))
 let finished=false
 return(outcome='COMPLETE')=>{
  if(finished)return
  finished=true
  const ended=readClock()
  userTiming(()=>{performance.mark(name+':end');performance.measure(name,name+':start',name+':end')})
  records.push({sequence:id,phase,duration_ms:started!==null&&ended!==null&&ended>=started?ended-started:null,outcome})
  userTiming(()=>{performance.clearMarks(name+':start');performance.clearMarks(name+':end');performance.clearMeasures(name)})
 }
}
