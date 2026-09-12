// 只把服务端已选定的任务定位字段带入正式页面，不决定下一任务或触发写入。
import type { PrimaryTaskDto } from '../api/workspace'
const preparationKinds = new Set(['SELECT_ALLOW_CONTROL','REVIEW_RECORDING','PREPARE_TEST_IDENTITY','DEMONSTRATE_ACTION','PREPARE_ACTION_RESOURCE','COMPLETE_EFFECT_EVIDENCE','COMPLETE_RECOVERY'])
export function taskDestination(task: PrimaryTaskDto) {
  const query = new URLSearchParams()
  if (task.run_id) query.set('run_id', task.run_id)
  else if (task.change_id && task.route === '/tests') query.set('change_id', task.change_id)
  if (task.route === '/tests' && preparationKinds.has(task.task_kind)) query.set('task_id', task.task_id)
  return task.route + (query.size ? `?${query}` : '')
}
