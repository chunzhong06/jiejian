# 通过真实控制面推进独立官方示例，封装重复请求而不替测试决定结论。
from dataclasses import dataclass
import time
from uuid import uuid4


def until(read,accept,*,seconds=90,clock=time.monotonic,sleep=time.sleep):
    deadline=clock()+seconds
    while clock()<deadline:
        value=read()
        if accept(value):return value
        sleep(.15)
    raise AssertionError('独立场景未在预算内形成完成回执')


@dataclass(frozen=True)
class Checkpoint:
    run_id: str
    status: dict
    story: dict
    preview: dict


class OfficialScenario:
    def __init__(self,client):
        self.client=client
        self.project_id=None
        self.operations=[]
        self.stages=[]

    def request(self,method,path,body=None):
        response=self.client.request(method,path,**({'json':body} if body is not None else {}))
        assert response.status_code in (200,201,202),f'{method} {path}: HTTP {response.status_code}'
        envelope=response.json()
        assert envelope.get('schema_version')=='1' and 'data' in envelope
        if method!='GET':self.operations.append({'method':method,'path':path,'status':response.status_code})
        return envelope['data']

    def start(self):
        self.request('POST','/api/experience/official-sample/start',{'schema_version':'1','consent':True,'operation_id':uuid4().hex})
        sample=until(lambda:self.request('GET','/api/experience/official-sample?lightweight=true'),lambda value:value['operation_state'] in {'SUCCEEDED','FAILED'})
        assert sample['active'] and sample['operation_state']=='SUCCEEDED'
        self.project_id=sample['project_id']
        proposal=self.request('POST','/api/experience/official-sample/boundary-proposal',{'exhibition_download':True})['proposal']
        self.request('POST',f'/api/projects/{self.project_id}/business-boundaries/proposals/{proposal["proposal_id"]}/approve',{'schema_version':'1','expected_fingerprint':proposal['proposal_fingerprint'],'reason':'独立官方场景核对访问要求'})

    def check(self,version,change_id=None):
        project=self.project_id
        plan=self.request('POST',f'/api/projects/{project}/proof-preparation/batches/preview?mode=OFFICIAL')
        operation=uuid4().hex
        self.request('POST',f'/api/projects/{project}/proof-preparation/batches',{'operation_id':operation,'plan':plan,'confirmed':True})
        batch=until(lambda:self.request('GET',f'/api/projects/{project}/proof-preparation/batches/{operation}'),lambda value:value['state'] not in {'RUNNING','CANCELLING'})
        assert batch['state']=='SUCCEEDED',f'准备批次终止于 {batch["state"]}'
        assert self.request('GET',f'/api/projects/{project}/preparation')['preparation_complete']
        suffix='?change_id='+change_id if change_id else ''
        preview=self.request('GET',f'/api/projects/{project}/check-preview'+suffix)
        assert preview['can_execute']
        command={'schema_version':'2','expected_plan_fingerprint':preview['plan_fingerprint'],'idempotency_key':uuid4().hex}
        if change_id:command['change_id']=change_id
        submitted=self.request('POST',f'/api/projects/{project}/runs',command)
        run_id=submitted['run']['run_id']
        status=until(lambda:self.request('GET',f'/api/runs/{run_id}'),lambda value:value['run']['lifecycle'] not in {'QUEUED','RUNNING'},seconds=120)
        story=self.request('GET',f'/api/runs/{run_id}/result-story')
        self.stages.append({'version':version,'run_id':run_id,'lifecycle':status['run']['lifecycle'],'verdict':status['run']['verdict']})
        return Checkpoint(run_id,status,story,preview)

    def load(self,version,*,repair=None):
        command={'schema_version':'1','version':version}
        if repair is not None:
            contracts=self.request('GET',f'/api/runs/{repair.run_id}/repair-contracts')
            assert len(contracts)==1
            command['repair_reference']={key:contracts[0][key] for key in ('source_run_id','source_case_id','repair_fingerprint')}
        return self.request('POST','/api/experience/official-sample/version',command)['current_change_id']
