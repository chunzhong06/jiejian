# 为每次 pytest 运行保存不含异常正文或参数值的结构化回执。
import hashlib
import json
import os
import time
from pathlib import Path

state={}
destination=None

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
    global destination,state
    value=os.environ.get('JIEJIAN_TEST_REPORT')
    destination=Path(value) if value else None
    state={'schema_version':'1','engine':'pytest','status':'RUNNING','started_at':time.time(),'cases':[],'collection_errors':[]}
    save()

def pytest_collectreport(report):
    if report.failed:state['collection_errors'].append(public_node(report.nodeid));save()

def pytest_runtest_logreport(report):
    state['cases'].append({'node':public_node(report.nodeid),'phase':report.when,'outcome':report.outcome,'seconds':round(report.duration,4)})
    save()

def pytest_sessionfinish(session,exitstatus):
    state.update(status='PASSED' if exitstatus==0 else 'EMPTY' if exitstatus==5 else 'FAILED',exit_code=int(exitstatus),collected=session.testscollected,seconds=round(time.time()-state['started_at'],3))
    save()
