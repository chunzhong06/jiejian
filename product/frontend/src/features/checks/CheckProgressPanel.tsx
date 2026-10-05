// 检查过程只投影服务端阶段与计数；动效衔接真实更新，不用计时器推算进度或安全结论。
import type {ReactNode} from 'react'
import type {CheckStatus} from '../../api/checks/currentChecks'
import './check-progress.css'

export function CheckProgressPanel({status, paused, children}:{status:CheckStatus;paused:boolean;children?:ReactNode}) {
  const progress=status.progress, queued=status.run.lifecycle==='QUEUED'
  const active=['QUEUED','RUNNING'].includes(status.run.lifecycle)
  const phase=queued ? 0 : progress ? {PREPARING:1,EXECUTING:2,FINALIZING:3}[progress.phase] : 1
  const hasCounts=Boolean(progress && progress.planned_cases>0 && progress.completed_cases>=0 && progress.completed_cases<=progress.planned_cases)
  const current=progress?.current_case
  const title=paused ? '暂时无法读取最新进度' : status.job?.cancel_requested ? '正在停止检查' : !active ? '本轮执行已停止' : queued ? '等待执行器领取' : !progress ? '正在读取执行进度' : {PREPARING:'正在准备本轮检查',EXECUTING:'正在执行并观察业务结果',FINALIZING:'正在核验并发布结果'}[progress.phase]
  return <section className="check-run-process" aria-label="本轮权限验证过程" data-active={active && !paused && !status.job?.cancel_requested}>
    <ol className="check-run-stages">{['等待','准备','执行','发布'].map((label,index)=><li key={label} aria-current={index===phase ? 'step' : undefined} data-complete={index<phase}><span>{index+1}</span>{label}</li>)}</ol>
    <div className="check-run-focus"><h2 className="check-run-title">{title}</h2>
      <div className="check-run-reading"><span className="check-run-count" role="status">{hasCounts ? `已处理 ${progress!.completed_cases} / ${progress!.planned_cases} 项验证` : '尚未取得检查项进度'}</span><span>结果在证据发布后给出</span></div>
      {hasCounts && <div className="check-progress-bar" role="progressbar" aria-label="已处理检查项" aria-valuemin={0} aria-valuemax={progress!.planned_cases} aria-valuenow={progress!.completed_cases}><span style={{width:`${progress!.completed_cases/progress!.planned_cases*100}%`}}/></div>}
      {progress?.phase==='EXECUTING' && <section className="check-current-case" aria-label="当前处理的权限考题">
        <p className="editorial-eyebrow">{paused || !active ? '上次读取的计划题目' : '当前处理的计划题目'}</p>
        {current ? <><h3>{current.expectation==='ALLOW' ? '正常对照' : '拒绝验证'} · {current.action_label}</h3><p>计划操作账号：{current.planned_subject_label}；资源所有者：{current.planned_resource_owner_label}。</p><p>本题将观察：{current.effect_labels.join('、') || '本题冻结的业务结果'}。</p><details><summary>核对本题资源引用</summary><code>{current.resource_id}</code></details></> : <p>当前考题说明暂不可用，执行进度仍以服务端为准。</p>}
      </section>}
      {children && <div className="check-run-actions">{children}</div>}
    </div>
  </section>
}
