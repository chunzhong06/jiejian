# 官方材料配方分步观察各自受监督的登录进程；取消与未知回执不重新提交目标动作。
from copy import deepcopy
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.examples.gallery_materials import gallery_identities, prepare_gallery_content


def advance_gallery_preparation(service, project, progress, *, cancel=False):
    """返回可持久化的有限进度；每次只提交或观察，不同步等待登录进程。"""
    value=deepcopy(progress)
    identities=list(value.get('identities',[]))
    if not identities:
        if cancel:return dict(value,phase='CANCELLED')
        identities=[dict(identity_id=item.identity_id,account=account,preparation_id=None,state='WAITING')
                    for item,account in zip(gallery_identities(service,project),('curator','judge'),strict=True)]
        return dict(value,identities=identities,phase='LOGIN',started_at_us=service.clock())
    state=None if cancel else service.runtime.state(project)
    origin=None if cancel else f"http://127.0.0.1:{state['configuration']['port']}"
    pending=False
    for item in identities:
        if item['state'] in ('PREPARED','CANCELLED'):continue
        preparation=item.get('preparation_id')
        if preparation is None:
            if cancel:item['state']='CANCELLED';continue
            # 两个身份分别提交，不等待第一个完成后才提交第二个。
            view=service.identity_preparations.start_official(item['identity_id'],account=item['account'],origin=origin)
            if view is None:item['state']='PREPARED';continue
            item['preparation_id']=view.preparation_id
        else:
            view=service.identity_preparations.status(preparation)
        item['state']=view.status.value
        if item['state'] not in ('PREPARED','CANCELLED','FAILED'):
            timed_out=service.clock()-value['started_at_us']>40_000_000
            if (cancel or timed_out) and not item.get('cancel_sent'):
                service.identity_preparations.cancel(item['preparation_id'])
                item['cancel_sent']=True
            pending=True
        elif item['state']=='FAILED' and not cancel:
            value['failed']=True
    value.update(identities=identities,phase='LOGIN')
    if pending:return value
    if cancel:return dict(value,phase='CANCELLED')
    if value.get('failed') or any(item['state']!='PREPARED' for item in identities):
        raise JiejianError(ErrorCode.IDENTITY_PREPARATION_FAILED,'示例账号未准备完成，请核对账号后继续')
    if progress.get('phase')!='CONTENT':return dict(value,phase='CONTENT')
    prepare_gallery_content(service,project,[service.identities.get(item['identity_id']) for item in identities])
    return dict(value,phase='COMPLETED',finished_at_us=service.clock())
