# 为每次 pytest 运行保存不含异常正文或参数值的结构化回执。
import hashlib
import json
import os
import time
from pathlib import Path
from scripts.quality.identity import input_identity

state={}
destination=None
events=None

def save():
    if destination is None:return
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    for attempt in range(3):
        try:
            temporary.replace(destination)
            break
        except PermissionError:
            if attempt==2:raise
            time.sleep(.02*(2**attempt))

def public_node(value):
    name,separator,parameters=value.partition('[')
    return name+'['+hashlib.sha256(parameters.encode()).hexdigest()[:12]+']' if separator else name

def pytest_sessionstart(session):
    global destination,state,events
    value=os.environ.get('JIEJIAN_TEST_REPORT')
    destination=Path(value) if value else None
    state={'schema_version':'1','engine':'pytest','status':'RUNNING','started_at':time.time(),'cases':[],'collection_errors':[]}
    if destination is not None:
        state['inputs']=input_identity(Path(__file__).resolve().parents[2])
        destination.parent.mkdir(parents=True,exist_ok=True)
        event_path=destination.with_suffix('.events.jsonl')
        events=event_path.open('w',encoding='utf-8',buffering=1)
        state['events']=event_path.name
        events.write(json.dumps({'event':'started',**state},ensure_ascii=False)+'\n')
    save()

def pytest_collection(session):
    state['collection_started_at']=time.time()

def pytest_collection_finish(session):
    state['collection_seconds']=round(time.time()-state.pop('collection_started_at'),4)

def pytest_collectreport(report):
    if report.failed:
        node=public_node(report.nodeid)
        state['collection_errors'].append(node)
        if events:events.write(json.dumps({'event':'collection_error','node':node})+'\n')

def pytest_runtest_logreport(report):
    state['cases'].append({'node':public_node(report.nodeid),'phase':report.when,'outcome':report.outcome,'seconds':round(report.duration,4)})
    if events:events.write(json.dumps({'event':'case',**state['cases'][-1]})+'\n')
    # 倍增快照的累计序列化量为线性；两次快照间的中断结果从追加事件读取。
    count=len(state['cases'])
    if count & (count-1)==0:save()

def pytest_sessionfinish(session,exitstatus):
    state.update(status='PASSED' if exitstatus==0 else 'EMPTY' if exitstatus==5 else 'FAILED',exit_code=int(exitstatus),collected=session.testscollected,seconds=round(time.time()-state['started_at'],3))
    save()
    if events:
        events.write(json.dumps({'event':'finished',**{key:value for key,value in state.items() if key!='cases'}})+'\n')
        events.close()
