// 建议与原准备指导共用一次读取；精确修订不被最新列表替换，隐藏页和旧项目响应不能回写。
import { useEffect, useRef, useState } from 'react'
import { proofSourcesApi } from '../../../api/preparation/proofSources'
import { preparationSuggestionsApi, type PreparationSuggestionContext, type PreparationSuggestionView } from '../../../api/preparation/preparationSuggestions'
import type { PreparationGuidance } from '../../../api/preparation/preparationGuidance'
import { useLiveRead } from '../../../shared/runtime/useLiveRead'
import { ApiError } from '../../../api/http'

type Snapshot = { key: string; context?: PreparationSuggestionContext; view?: PreparationSuggestionView | null; guidance?: PreparationGuidance; error?: string }

export function useMaterialSuggestions(projectId: string, enabled: boolean, refreshKey: string, id?: string | null, revision?: string | null) {
  const key = JSON.stringify([projectId, refreshKey, id, revision])
  const scope = useRef<string | undefined>(undefined)
  scope.current = enabled ? key : undefined
  const [snapshot, setSnapshot] = useState<Snapshot>()
  const [busyKey, setBusyKey] = useState<string>()
  const pending = useRef<{ key: string; promise: Promise<void> } | undefined>(undefined)
  useEffect(() => () => { scope.current = undefined }, [])

  const read = (): Promise<void> => {
    if (pending.current?.key === key) return pending.current.promise
    setBusyKey(key)
    const request = (async () => {
      const value = await proofSourcesApi.context(projectId)
      if (value.project_id !== projectId || (value.suggestion_context && value.suggestion_context.project_id !== projectId)) throw new Error('project mismatch')
      let context = value.suggestion_context
      let view: PreparationSuggestionView | null | undefined = context?.latest
      let error: string | undefined
      // 指定修订读取失败时保留明确错误，不能换成另一份建议让用户误认来源。
      if (id != null) {
        try { view = await preparationSuggestionsApi.show(projectId, id, revision) }
        catch { view = undefined; error = '无法读取指定的材料建议。请核对原链接，或返回当前材料。' }
      }
      if (view && view.suggestion.project_id !== projectId) throw new Error('suggestion project mismatch')
      const changed = view && context?.basis_id && view.current_basis_id !== context.basis_id
      if (changed) context = { ...context!, state: 'NEEDS_REFRESH', note: '读取期间准备依据已经变化，请重新读取建议。' }
      if (view && context?.state !== 'CURRENT') view = { ...view, items: view.items.map(item => ({ ...item, current: false, source_locations: [] })) }
      if (scope.current === key) setSnapshot({ key, context, view, error,
        guidance: !changed && value.guidance?.project_id === projectId ? value.guidance : undefined })
    })().catch((failure: unknown) => {
      // 仅展示HTTP边界已脱敏的错误，原始异常与响应正文不进入界面；不据权限数量猜根因。
      const detail = failure instanceof ApiError ? `原因：${failure.message}（${failure.code}）${failure.traceId ? `，记录编号 ${failure.traceId}` : ''}。` : '尚未取得有效响应，请重新读取；持续失败时保留本次接口错误记录。'
      if (scope.current === key) setSnapshot({ key, error: `材料建议暂时无法读取。${detail}仍可查看下方实际材料；尚无正式权限时，请先到权限页核对候选并批准。` })
    }).finally(() => {
      if (pending.current?.promise === request) pending.current = undefined
      if (scope.current === key) setBusyKey(undefined)
    })
    pending.current = { key, promise: request }
    return request
  }
  useLiveRead(enabled ? key : undefined, read, 20_000)
  return { ...(snapshot?.key === key ? snapshot : {}), read, loading: busyKey === key,
    loaded: snapshot?.key === key }
}
