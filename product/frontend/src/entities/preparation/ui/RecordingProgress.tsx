import type {ReactNode} from 'react'
import type {RecordingViewDto} from '../api/recordings'
import {recordingEnded} from '../model/recordingState'
import {Badge,ErrorNote} from '../../../shared/ui/feedback'
import {Button} from '../../../shared/ui/actions'
import {ObjectHeading,SectionHeading,TaskActions,TaskStage} from '../../../shared/ui/layout'
import {ActivityDots} from '../../../shared/ui/ActivityDots'
import './recording-progress.css'

const reasonText:Record<string,string>={
 SESSION_REFERENCE_EXPIRED:'这次录制使用的登录已失效，请先核对原账号并重新登录。',
 AUTHENTICATION_FAILED:'应用没有接受这次登录，请先核对原账号。',
 AUTHENTICATION_REQUIRED:'应用要求重新登录，请先核对原账号。',
 TARGET_SCOPE_VIOLATION:'页面请求超出了本次确认的应用范围，录制已停止。',
 UNSUPPORTED_RESPONSE:'应用返回了本次录制不能安全采集的响应。',
 STREAMING_UNSUPPORTED:'应用响应采用了本次录制不支持的流式传输，请核对接口返回方式后再录制。',
 CONTENT_LENGTH_REQUIRED:'应用响应没有声明完整长度，请核对接口返回方式后再录制。',
 BROWSER_START_FAILED:'独立浏览器未能打开。',
 BROWSER_INTERACTION_FAILED:'浏览器操作没有完整结束。',
 EVENT_BUDGET_EXCEEDED:'本次采集已达到允许的事件或请求上限。',
 PROCESSING_FAILED:'已有操作未能整理成可审阅流程。',
 CLEANUP_FAILED:'本次浏览器资源的清理仍需核对。',
}

/** 解释当前录制事实；开始、停止、取消及审阅写入仍由原材料用例持有。 */
export function RecordingProgress({view,action,accounts,busy,uncertain,error,onStart,onStop,onCancel,onRefresh,onBack,children}:{
 view:RecordingViewDto;action:string;accounts:Array<{test_identity_id:string;label:string}>;busy:boolean;uncertain:boolean;error?:unknown;
 onStart:()=>void;onStop:()=>void;onCancel:()=>void;onRefresh:()=>void;onBack:()=>void;children?:ReactNode
}){
 const recording=view.recording!,phase=view.capture_phase??recording.capture_phase
 const stopped=recording.state==='SAFETY_STOPPED',failed=recording.state==='FAILED'||stopped,cancelled=recording.state==='CANCELLED',saved=recording.state==='COMPLETED'
 const review=recording.state==='PENDING_REVIEW',ended=recordingEnded(recording.state)
 const ready=!ended&&!review&&phase==='AWAITING_CAPTURE',capturing=!ended&&!review&&phase==='CAPTURING'
 const status=failed?'需要处理':cancelled?'已取消':saved?'已保存':review?'待审阅':ready?'等待开始':capturing?'正在采集':phase==='STOPPING'?'正在结束采集':phase==='CAPTURE_STARTING'?'正在开始采集':recording.state==='PROCESSING'?'正在整理':'正在准备'
 const title=stopped?'这次录制已停止':failed?'这次录制未完成':cancelled?'这次录制已取消':saved?'这次操作已保存':review?'核对这次录制':ready?'浏览器已就绪':capturing?'在独立浏览器中完成操作':'本次操作录制'
 const purpose=recording.purpose==='RECOVERY'?'恢复方式':recording.purpose==='OBSERVATION'?'业务结果观察':'业务操作'
 const label=(id?:string)=>accounts.find(item=>item.test_identity_id===id)?.label??(view.test_identity&&view.test_identity.test_identity_id===id?view.test_identity.label:'原账号（请返回核对）')
 const specificResponse=(recording.reason_codes??[]).some(code=>['STREAMING_UNSUPPORTED','CONTENT_LENGTH_REQUIRED'].includes(code))
 const reasons=[...new Set((recording.reason_codes??[]).filter(code=>reasonText[code]&&!(specificResponse&&code==='UNSUPPORTED_RESPONSE')).map(code=>reasonText[code]))]
 const job=view.job??recording.job,activeJob=job&&!['SUCCEEDED','FAILED','CANCELLED'].includes(job.state)
 const description=failed?'已有材料继续保留。处理下面的原因后，返回原准备任务继续。':cancelled?'本次没有保存新的流程；已经发生的业务变化仍需核对。':saved?'录制候选已经保存。回到材料核对影响并确认后，才会用于检查。':review?'按实际顺序核对步骤和业务对象。保存后形成候选，随后再确认是否用于检查。':ready?'先在独立窗口核对登录与测试数据。准备好后在这里开始记录。':capturing?`在独立浏览器中演示“${action}”及必要的前序步骤，完成后回到这里结束采集。`:'正在处理原录制任务，离开页面后仍可回到这里查看。'
 const controls=!children&&<TaskActions>{ended?<Button kind="primary" disabled={busy} onClick={onBack}>返回准备并核对现场</Button>:<>
  {activeJob&&<Button kind="quiet" disabled={busy||Boolean(error)} onClick={onCancel}>取消本次录制</Button>}
  {ready&&<Button kind="primary" busy={busy} disabled={uncertain||Boolean(error)} onClick={onStart}>开始记录这个操作</Button>}
  {capturing&&<Button kind="primary" busy={busy} disabled={uncertain||Boolean(error)} onClick={onStop}>结束采集并核对</Button>}
 </>}</TaskActions>
 const context=<section className="jj-recording-reading"><SectionHeading title="本次录制对象" appearance="group"/>
  <dl className="jj-facts"><div><dt>业务操作</dt><dd>{action}</dd></div><div><dt>录制用途</dt><dd>{purpose}</dd></div><div><dt>操作账号</dt><dd>{label(recording.subject_test_identity_id)}</dd></div><div><dt>资源所有者</dt><dd>{label(recording.resource_owner_test_identity_id)}</dd></div></dl>
 </section>
 const guidance=<>
  <ObjectHeading title={title} status={<Badge tone={failed?'caution':saved?'positive':ended?'neutral':'accent'}>{!ended&&!review&&!ready&&<ActivityDots/>}{status}</Badge>}/>
  <p>{description}</p>
  {reasons.length>0&&<div className="jj-recording-reasons" role="status">{reasons.map(reason=><p key={reason}>{reason}</p>)}</div>}
  {ready&&<p className="jj-small jj-muted">准备期间不采集业务步骤。</p>}
  {(failed||cancelled)&&<p className="jj-small jj-muted">重录前先核对测试数据，必要时按原安排恢复。取消或失败不会撤回应用中已发生的操作。</p>}
 </>
 return <section className="jj-recording-progress" aria-label="本次操作录制">
  {Boolean(error)&&<ErrorNote error={error} actions={<Button onClick={onRefresh}>重新读取原录制</Button>}/>}
  {children?<><div className="jj-recording-review-context">{guidance}</div>{context}</>:<TaskStage context={context}>{guidance}{controls}</TaskStage>}
  {children}
 </section>
}
