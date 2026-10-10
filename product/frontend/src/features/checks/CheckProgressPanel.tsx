// 检查过程只投影服务端阶段与计数；阶段说明可回看，不按时间推算进度或安全结论。
import {useState, type ReactNode} from 'react'
import type {CheckStatus} from '../../api/checks/currentChecks'
import {formatTimestamp} from '../../shared/format/time'
import './check-progress.css'

export function CheckProgressPanel({status, paused, children}:{status:CheckStatus;paused:boolean;children?:ReactNode}) {
  const [selection,setSelection]=useState<{runId:string;phase:number}|null>(null)
  const progress=status.progress, queued=status.run.lifecycle==='QUEUED', published=status.result_integrity==='VALID'
  const active=['QUEUED','RUNNING'].includes(status.run.lifecycle)
  const phase=published ? 3 : queued ? 0 : progress ? {PREPARING:1,EXECUTING:2,FINALIZING:3}[progress.phase] : 1
  const selectedPhase=selection && selection.runId===status.run.run_id ? Math.min(selection.phase,phase) : phase
  const reviewing=selectedPhase!==phase
  const hasCounts=Boolean(progress && progress.planned_cases>0 && progress.completed_cases>=0 && progress.completed_cases<=progress.planned_cases)
  const current=progress?.current_case
  const titles=['检查请求已保存','本轮准备情况','本轮执行情况',published?'结果已发布并核验':'正在核验并发布结果']
  const title=reviewing ? titles[selectedPhase] : paused ? '暂时无法读取最新进度' : published ? titles[3] : status.job?.cancel_requested ? '正在停止检查' : !active ? '本轮执行已停止' : queued ? '等待执行器领取' : !progress ? '正在读取执行进度' : progress.phase==='PREPARING' ? '正在准备本轮检查' : phase===2?'正在执行并观察业务结果':titles[phase]
  const created=Number.isFinite(status.run.created_at_us)?formatTimestamp(status.run.created_at_us):null
  return <section className="check-run-process" aria-label="本轮权限验证过程" data-active={active && !paused && !status.job?.cancel_requested}>
    <ol className="check-run-stages">{['等待','准备','执行','发布'].map((label,index)=><li key={label} aria-current={index===phase ? 'step' : undefined} data-selected={index===selectedPhase} data-complete={published || index<phase}><button type="button" disabled={index>phase} aria-label={`查看${label}阶段`} aria-pressed={index===selectedPhase} onClick={()=>setSelection({runId:status.run.run_id,phase:index})}><span>{index+1}</span>{label}</button></li>)}</ol>
    <div className="check-run-focus"><h2 className="check-run-title">{title}</h2>
      {reviewing && <p className="check-stage-return"><button type="button" onClick={()=>setSelection(null)}>返回最新阶段</button></p>}
      {selectedPhase===0 && <section className="check-stage-facts" aria-label="等待阶段记录"><p>检查请求已保存，执行器领取后开始准备。</p><dl><div><dt>提交时间</dt><dd>{created??'时间暂不可用'}</dd></div><div><dt>领取情况</dt><dd>{status.job && status.job.attempt>0?'执行器已领取本轮任务':queued?'等待执行器领取':'领取记录暂不可用'}</dd></div><div><dt>本轮权限</dt><dd>权限版本 {status.run.policy_epoch}</dd></div></dl></section>}
      {selectedPhase===1 && <section className="check-stage-facts" aria-label="准备阶段记录"><p>{phase>1?'已进入执行阶段，本轮检查按冻结的计划运行。':active?'执行器正在读取本轮计划并核对运行条件。':'本轮已停止，未取得完整准备记录。'}</p><dl><div><dt>本轮范围</dt><dd>{hasCounts?`${progress!.planned_cases} 项验证`:'尚未取得计划项数'}</dd></div><div><dt>任务状态</dt><dd>{status.job && status.job.attempt>0?'已分配执行任务':'尚未取得任务记录'}</dd></div><div><dt>权限依据</dt><dd>权限版本 {status.run.policy_epoch}</dd></div></dl></section>}
      {selectedPhase>=2 && <><div className="check-run-reading"><span className="check-run-count" role="status">{hasCounts ? `已处理 ${progress!.completed_cases} / ${progress!.planned_cases} 项验证` : '正在读取检查项进度'}</span><span>{published?'结果以已发布证据为准':'结果在证据发布后给出'}</span></div>
      {hasCounts && <div className="check-progress-bar" role="progressbar" aria-label="已处理检查项" aria-valuemin={0} aria-valuemax={progress!.planned_cases} aria-valuenow={progress!.completed_cases}><span style={{width:`${progress!.completed_cases/progress!.planned_cases*100}%`}}/></div>}</>}
      {selectedPhase===2 && <section className="check-current-case" aria-label="当前处理的权限考题">
        <p className="editorial-eyebrow">{paused || !active || reviewing ? '本轮执行记录' : '当前处理的计划题目'}</p>
        {current ? <><h3>{current.expectation==='ALLOW' ? '正常对照' : '拒绝验证'} · {current.action_label}</h3><p>计划操作账号：{current.planned_subject_label}；资源所有者：{current.planned_resource_owner_label}。</p><p>本题将观察：{current.effect_labels.join('、') || '本题冻结的业务结果'}。</p><details><summary>核对本题资源引用</summary><code>{current.resource_id}</code></details></> : <p>{published?'执行已结束，逐项事实与证明可在本轮结果中查看。':'当前考题说明暂不可用，执行进度仍以服务端为准。'}</p>}
      </section>}
      {selectedPhase===3 && <section className="check-stage-facts" aria-label="发布阶段记录"><p>{published?'证据文件、发布记录和所属检查已通过读取核验。':status.result_integrity==='INVALID'?'已发布资料的完整性核验未通过，暂不展示安全结论。':'正在核验已取得的事实，发布完成后才展示判断。'}</p><dl><div><dt>发布状态</dt><dd>{published?'已发布':status.result_integrity==='INVALID'?'完整性核验失败':'等待发布完成'}</dd></div><div><dt>完成时间</dt><dd>{status.run.finished_at_us!=null?formatTimestamp(status.run.finished_at_us):'尚未完成'}</dd></div></dl></section>}
      {children && <div className="check-run-actions">{children}</div>}
    </div>
  </section>
}
