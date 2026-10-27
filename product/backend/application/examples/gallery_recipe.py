# 数字展馆的可审阅建议：人的展示版选择写入提案，代码现状不代替权限要求。
import json
from product.backend.application.business_boundaries.models import BoundaryProposalCommand

OWNER='pactr_1210000000000001'
REVIEWER='pactr_1210000000000002'
INTERNAL='pactn_1210000000000001'
PREVIEW='pactn_1210000000000002'
EXHIBITION='pactn_1210000000000003'
FILE='peff_1210000000000001'
ACCESS='peff_1210000000000002'
PUBLIC='peff_1210000000000003'
PDF='peff_1210000000000004'
ACTION_ROUTES={'取得内部完整包':'POST /api/galleries/{resource_id}/internal','查看公开预览':'GET /api/galleries/{resource_id}/preview','下载公开展示版':'GET /api/galleries/{resource_id}/exhibition'}

def gallery_recipe(exhibition_download: bool, understanding) -> BoundaryProposalCommand:
    if type(exhibition_download) is not bool:raise ValueError('展示版下载要求需要人的明确选择')
    roles={item.canonical_key.casefold():item.candidate_id for item in understanding.role_candidates if not item.stale}
    routes={item.canonical_key:item.candidate_id for item in understanding.action_candidates if not item.stale}
    actors=[dict(item_id=key,write_mode='CREATE',display_name=name,description=description,effective_state='ACTIVE',source_candidate_ids=[roles[role]] if role in roles else [])
        for key,name,description,role in [(OWNER,'项目负责人','管理展馆资料并保留完整导出','owner'),(REVIEWER,'评审','查看获准的公开展示内容','reviewer')]]
    effects={FILE:dict(business_label='内部完整包已被接收',effect_kind='FILE_CONTENT_DELIVERY',resource_concept='内部完整包',description='实际收到与已确认参照一致的完整文件'),
        ACCESS:dict(business_label='内部包曾向操作账号开放',effect_kind='STATE_MUTATION',resource_concept='展馆访问范围',expected_state='recipient',description='检查窗口内存在向本次操作账号开放的独立提交，即使随后撤回'),
        PUBLIC:dict(business_label='公开作品说明可见',effect_kind='DATA_DISCLOSURE',resource_concept='公开展示内容',protected_projection=['title','summary'],description='只读取公开标题与作品说明'),
        PDF:dict(business_label='公开展示版已被接收',effect_kind='FILE_CONTENT_DELIVERY',resource_concept='公开展示版PDF',description='实际收到已确认的公开展示文件')}
    actions=[dict(item_id=key,write_mode='CREATE',display_name=name,description=description,primary_resource_concept='展馆资料',operation_kind=operation,state_changing=changing,effective_state='ACTIVE',source_candidate_ids=[routes[ACTION_ROUTES[name]]] if ACTION_ROUTES[name] in routes else [],effect_catalog=[dict(item_id=effect,**effects[effect]) for effect in selected])
        for key,name,description,operation,changing,selected in [(INTERNAL,'取得内部完整包','请求取得团队内部完整资料','EXPORT',True,[FILE,ACCESS]),(PREVIEW,'查看公开预览','读取对外公开的作品说明','READ',False,[PUBLIC]),(EXHIBITION,'下载公开展示版','下载只含公开内容的PDF','EXPORT',False,[PDF])]]
    requirements=[(OWNER,INTERNAL,'OWNS','ALLOW',[FILE,ACCESS]),(REVIEWER,INTERNAL,'OTHER_ROLE','DENY',[FILE,ACCESS]),
        (REVIEWER,PREVIEW,'OTHER_ROLE','ALLOW',[PUBLIC]),(OWNER,EXHIBITION,'OWNS','ALLOW',[PDF]),
        (REVIEWER,EXHIBITION,'OTHER_ROLE','ALLOW' if exhibition_download else 'DENY',[PDF])]
    permissions=[dict(item_id='pperm_121'+str(index).zfill(13),write_mode='CREATE',effective_state='ACTIVE',subject_actor_item_id=subject,business_action_item_id=action,resource_owner_actor_item_id=OWNER,relation=relation,expectation=expectation,protected_effect_item_ids=protected)
        for index,(subject,action,relation,expectation,protected) in enumerate(requirements,1)]
    return BoundaryProposalCommand.model_validate_json(json.dumps(dict(proposed_actors=actors,proposed_actions=actions,proposed_permissions=permissions,
        provenance='数字展馆公开建议；展示版下载由本机用户明确选择：'+('允许' if exhibition_download else '禁止'))))

BASELINE="""// 交付前核对实际账号及资源所有者。
export function mayReceive(actor, ownerId) { return actor.id === ownerId && actor.role === 'owner'; }
export async function beforeDecision(records, item, actor) {
  if(mayReceive(actor,item.owner_id)) await records.transact({resource_id:item.resource_id,subject_id:actor.id,expected_version:item.version,changes:[{path:['access_for'],value:actor.id},{path:['visibility'],value:'recipient'}]});
}
export async function afterDenied(records, item, actor) {}
"""
VULNERABLE=BASELINE.replace("actor.id === ownerId && actor.role === 'owner'","true")
EXPOSE_REVOKE="""// 错误顺序：独立提交开放，再拒绝请求并独立撤回；外部读取会看到开放状态。
export function mayReceive(actor, ownerId) { return actor.id === ownerId && actor.role === 'owner'; }
export async function beforeDecision(records, item, actor) {
  await records.transact({resource_id:item.resource_id,subject_id:actor.id,expected_version:item.version,changes:[{path:['access_for'],value:actor.id},{path:['visibility'],value:'recipient'}]});
}
export async function afterDenied(records, item, actor) {
  await records.transact({resource_id:item.resource_id,subject_id:actor.id,expected_version:item.version,changes:[{path:['access_for'],value:''},{path:['visibility'],value:'internal'}]});
}
"""
PREVIEW_CHANGED="""// 后续维护只调整公开预览组织方式，保留原有字段。
export function publicView(item) { const {title,summary}=item.data; return {title,summary}; }
"""
