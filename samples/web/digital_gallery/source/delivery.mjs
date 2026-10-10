// 交付前核对实际账号及资源所有者。
export function mayReceive(actor, ownerId) { return actor.id === ownerId && actor.role === 'owner'; }
export async function beforeDecision(records, item, actor) {
  if(mayReceive(actor,item.owner_id)) await records.transact({resource_id:item.resource_id,subject_id:actor.id,expected_version:item.version,changes:[{path:['access_for'],value:actor.id},{path:['visibility'],value:'recipient'}]});
}
export async function afterDenied(records, item, actor) {}
