// 只把已发布观察译成完整句；不从响应码、资源名称或别项结论推断安全结果。
import type { ResultStory } from '../../../api/checks/currentChecks'

type ObservedState = 'CONFIRMED' | 'ABSENT' | 'UNKNOWN'
const topics: Record<string, string> = {
  '内部包曾向操作账号开放': '内部包访问权',
  '内部完整包已被接收': '内部完整包接收情况',
  '公开展示版已被接收': '公开展示版接收情况',
  '公开作品说明可见': '公开作品说明读取情况',
}
export function effectTopic(label: string) {
  // 标题只命名核对对象，不能把结果名称里的“已接收”呈现成另一条结论。
  return topics[label] ?? `核对“${label}”`
}
const sentences: Record<string, [string, string, string]> = {
  '内部包曾向操作账号开放': ['内部包曾向本次操作账号开放', '未发现内部包向本次操作账号开放', '尚不能确认内部包是否曾向本次操作账号开放'],
  '内部完整包已被接收': ['已完整收到内部完整包', '未发现内部完整包被完整接收', '尚不能确认是否完整收到内部完整包'],
  '公开展示版已被接收': ['已完整收到公开展示版', '未发现公开展示版被完整接收', '尚不能确认是否完整收到公开展示版'],
  '公开作品说明可见': ['已读取到公开作品说明', '未发现公开作品说明被读取', '尚不能确认是否读取到公开作品说明'],
}
export function effectSentence(label: string, state: ObservedState) {
  const known = sentences[label]
  if (known) return known[state === 'CONFIRMED' ? 0 : state === 'ABSENT' ? 1 : 2]
  // 自定义业务名称没有通用的否定语法，保留原文，避免替用户重写权限含义。
  return state === 'CONFIRMED' ? `已确认：${label}` : state === 'ABSENT' ? `本次未发现“${label}”` : `证据不足，尚不能确认“${label}”`
}
export function effectScope(state: ObservedState) {
  return state === 'ABSENT' ? '本次观察已完成；结论仅限已核对的请求与资源。' : state === 'UNKNOWN' ? '查看缺少的证据或核对条件，不能据此认定结果没有发生。' : '对应记录可在本项依据中核对。'
}
export function runHeading(story: ResultStory) {
  return story.verdict === 'PASS' ? `本轮${story.actions.length}项检查均符合权限要求` : story.verdict === 'BLOCK' ? '本轮发现违反权限要求的结果' : '本轮检查尚不能得出完整结论'
}
