// 原题逐项对照只渲染已发布的前后事实；行结果不能替代服务端的修复总判断。
import type {RepairComparisonRow} from '../../api/repairs'
const roleLabels = {DENY:'必须消除的原问题',SELECTED_ALLOW:'必须保留的正常对照',REGRESSION:'必须保留的原安全回归'}
const caseLabels = {SAFE:'符合这条权限规则',VULNERABLE:'发现不应发生的业务后果',INCONCLUSIVE:'证据不足，尚不能判断'}
export function RepairComparison({rows}: {rows: RepairComparisonRow[]}) {
  if (!rows.length) return <p className="editorial-muted">当前未取得可展示的逐项原题对照，请刷新已发布事实。</p>
  return <div className="repair-comparison" aria-label="原题修复前后对照">{rows.map((row,index)=><section key={`${row.role}:${row.source_case_id}:${index}`}>
    <p className="editorial-eyebrow">{roleLabels[row.role]}</p><h3>{row.subject_label ?? '原操作账号'} · {row.action_label}</h3>
    <p>资源属于：{row.resource_owner_label ?? '原资源所有者'}；业务结果：{row.effect_labels.join('、') || '原题已冻结的业务结果'}。</p>
    <div className="repair-comparison-columns"><div><span className="editorial-eyebrow">原问题记录</span><p>{caseLabels[row.before_verdict]}</p></div><div><span className="editorial-eyebrow">新的检查</span><p>{row.match_status === 'MATCHED' && row.after_verdict ? caseLabels[row.after_verdict] : row.match_status === 'AMBIGUOUS' ? '存在多项可能对应的操作，尚不能逐项关联' : row.match_status === 'NOT_FOUND' ? '尚未找到同一原题的检查结果' : '尚无可关联的已发布结果'}</p></div></div>
  </section>)}<p className="editorial-muted">这里逐项展示检查事实；是否沿原权限和证据标准完成修复，以服务端原题复验判断为准。</p></div>
}
