# 独立普通工单应用：启动时没有业务资料，账号登录和合成工单只能经真实业务请求建立。
import json


def write_workbench(root):
    root.mkdir(parents=True)
    (root/'workbench.mjs').write_text(APP,encoding='utf-8')
    (root/'policy.mjs').write_text(POLICY,encoding='utf-8')
    (root/'page.mjs').write_text('export const page='+json.dumps(PAGE,ensure_ascii=False)+';',encoding='utf-8')
    paths={path:{method:{'summary':label,'responses':{'200':{'description':'完成'}},
        'parameters':[] if '{ticket}' not in path else [{'name':'ticket','in':'path','required':True,'schema':{'type':'string'}}]}}
        for path,method,label in [('/session/current','get','当前工单账号'),('/service/tickets','post','新建工单'),
            ('/service/tickets/{ticket}','get','查看工单'),('/service/tickets/{ticket}/complete','post','完成工单'),
            ('/service/tickets/{ticket}/reopen','post','重新打开工单')]}
    (root/'openapi.json').write_text(json.dumps(dict(openapi='3.0.3',info={'title':'工单工作台','version':'1'},paths=paths),ensure_ascii=False),encoding='utf-8')


POLICY="export function mayComplete(actor, owner) { return actor.role === 'supervisor' && actor.id === owner; }"
APP=r"""
import http from 'node:http';
import crypto from 'node:crypto';
import {openCollection} from 'jiejian:records';
import {mayComplete} from './policy.mjs';
import {page} from './page.mjs';
const roles=['supervisor','contributor'];
const accounts={lead:{id:'lead',role:roles[0]},guest:{id:'guest',role:roles[1]}};
const records=openCollection('tickets'),sessions=new Map();
http.createServer(async(req,res)=>{
  const reply=(status,data)=>{const b=Buffer.from(JSON.stringify(data));res.writeHead(status,{'Content-Type':'application/json','Content-Length':b.length});res.end(b);};
  try {
    if(req.url==='/'){res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Content-Length':Buffer.byteLength(page)});return res.end(page);}
    if(req.url==='/session/login'&&req.method==='POST'){
      let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>512)return reply(413,{error:'size'});}
      const actor=accounts[JSON.parse(raw).account];if(!actor)return reply(403,{error:'account'});
      const key=crypto.randomBytes(24).toString('hex');sessions.set(key,actor);
      res.setHeader('Set-Cookie','workbench_session='+key+'; HttpOnly; SameSite=Strict; Path=/');return reply(200,actor);
    }
    const key=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('workbench_session='))?.slice(18);
    const actor=sessions.get(key);if(!actor)return reply(401,{error:'identity'});
    if(req.url==='/session/current')return reply(200,actor);
    if(req.url==='/service/tickets'&&req.method==='POST'){
      if(actor.role!=='supervisor')return reply(403,{error:'permission'});
      await records.seed('sample','lead',{phase:'queued',title:'合成测试工单',summary:'只含虚构内容'});
      return reply(201,{message:'合成工单已创建'});
    }
    const match=/^\/service\/tickets\/([a-z]+)(?:\/(complete|reopen))?$/.exec(req.url);
    if(!match)return reply(404,{error:'route'});
    const [,resource_id,action]=match,item=await records.read(resource_id);
    if(!item)return reply(404,{error:'尚无工单'});
    if(!action)return reply(200,{resource_id,owner_id:item.owner_id,data:item.data});
    const allowed=action==='reopen'?actor.id===item.owner_id:mayComplete(actor,item.owner_id);
    await records.transact({resource_id,subject_id:actor.id,expected_version:item.version,
      changes:allowed?[{path:['phase'],value:action==='complete'?'ready':'queued'}]:[]});
    return reply(allowed?200:403,{message:allowed?(action==='complete'?'工单已完成':'工单已重新打开'):'无权操作'});
  }catch(error){if(error?.message==='RECORD_RESOURCE_MISSING')return reply(404,{error:'尚无工单'});return reply(409,{error:'操作未完成'});}
}).listen(Number(process.env.PORT),'127.0.0.1');
"""
PAGE="""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>普通工单工作台</title>
<main><h1>普通工单工作台</h1><p id="identity">尚未登录</p><button onclick="login('lead')">主管登录</button>
<button onclick="login('guest')">协作者登录</button><button onclick="call('/service/tickets','POST')">创建合成工单</button>
<button onclick="call('/service/tickets/sample')">查看工单</button><button onclick="call('/service/tickets/sample/complete','POST')">完成工单</button>
<button onclick="call('/service/tickets/sample/reopen','POST')">重新打开工单</button><p id="output" aria-live="polite"></p></main>
<script>async function call(path,method='GET',body){const r=await fetch(path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});const d=await r.json();document.querySelector('#output').textContent=d.message||d.error||'工单内容已读取';return d;}
async function login(account){const d=await call('/session/login','POST',{account});document.querySelector('#identity').textContent=d.id||'未登录';}
fetch('/session/current').then(r=>r.json()).then(d=>{document.querySelector('#identity').textContent=d.id||'尚未登录';});</script></html>"""
