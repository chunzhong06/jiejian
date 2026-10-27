import type { FlowDraftDto, FlowDraftVariableSourceDto } from '../../../entities/preparation/api/recordings'

export function requiredVariables(draft?:FlowDraftDto|null){
  if(!draft?.target_step_id)return []
  const included=new Set<string>(),pending=[draft.target_step_id]
  while(pending.length){const id=pending.pop()!;if(included.has(id))continue;included.add(id);pending.push(...(draft.steps.find(step=>step.id===id)?.depends_on_step_ids??[]))}
  return (draft.variables??[]).filter(item=>!item.consumer_step_ids||item.consumer_step_ids.some(id=>included.has(id)))
}
export async function sourceChoice(source:FlowDraftVariableSourceDto){
  const bytes=new TextEncoder().encode(`${source.source_step_id}\0${source.source_event_sequence}\0${source.json_path}`)
  const hash=await crypto.subtle.digest('SHA-256',bytes)
  return 'choice-'+[...new Uint8Array(hash)].map(item=>item.toString(16).padStart(2,'0')).join('').slice(0,16)
}
