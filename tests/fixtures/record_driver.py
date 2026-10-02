# 最小协议驱动：只为通用来源整链测试生成临时 HTTP 处理器，无 UI、业务部署或产品专用配置。
import json


def write_record_driver(source, *, alternate=False):
    source.mkdir()
    (source/'app.mjs').write_text(DRIVER,encoding='utf8')
    (source/'policy.mjs').write_text("export function mayPublish(actor, ownerId) { return actor.role === 'owner' && actor.id === ownerId; }",encoding='utf8')
    (source/'response.mjs').write_text('export function publicationStatus(allowed) { return allowed ? 200 : 403; }',encoding='utf8')
    (source/'transition.mjs').write_text("export function publicationSteps() { return ['publish']; }",encoding='utf8')
    paths = {}
    for route,method in [('/api/me','get'),('/api/resources/{resource_id}','get'),
                         ('/api/resources/{resource_id}/publish','post'),('/api/resources/{resource_id}/withdraw','post')]:
        paths[route]={method:{'summary':'协议测试操作','responses':{'200':{'description':'ok'}},
            'parameters':([] if route=='/api/me' else [{'name':'resource_id','in':'path','required':True,'schema':{'type':'string'}}])}}
    (source/'openapi.json').write_text(json.dumps({'openapi':'3.0.3','info':{'title':'Protocol driver','version':'1'},'paths':paths}),encoding='utf8')
    if alternate:
        # 第二种接入更换入口、身份路径、资源集合与状态语义；产品不能依赖第一种约定。
        for path in source.iterdir():
            text=path.read_text(encoding='utf8').replace('/api/me','/session/current')
            text=text.replace("openCollection('units')","openCollection('tickets')")
            text=text.replace("{state:'draft'","{phase:'queued'").replace("path:['state']","path:['phase']")
            text=text.replace("?'published':'draft'","?'ready':'queued'")
            path.write_text(text,encoding='utf8')
        (source/'app.mjs').rename(source/'workbench.mjs')


DRIVER = r"""
import http from 'node:http';
import crypto from 'node:crypto';
import {openCollection} from 'jiejian:records';
import {mayPublish} from './policy.mjs';
import {publicationStatus} from './response.mjs';
import {publicationSteps} from './transition.mjs';
const roles=['owner','member'];
const accounts={alice:{id:'alice',role:roles[0]},bob:{id:'bob',role:roles[1]}};
const records=openCollection('units'), sessions=new Map();
await records.seed('alpha','alice',{state:'draft',title:'unit-a',summary:'value-a'});
await records.seed('beta','bob',{state:'draft',title:'unit-b',summary:'value-b'});
http.createServer(async(req,res)=>{
  const reply=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  try {
    if(req.url==='/api/login') {
      let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>512)return reply(413,{error:'size'});}
      const actor=accounts[JSON.parse(raw).account];if(!actor)return reply(403,{error:'account'});
      const key=crypto.randomBytes(24).toString('hex');sessions.set(key,actor);
      res.setHeader('Set-Cookie','test_session='+key+'; HttpOnly; SameSite=Strict; Path=/');return reply(200,{ok:true});
    }
    const key=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('test_session='))?.slice(13);
    const actor=sessions.get(key);if(!actor)return reply(401,{error:'identity'});
    if(req.url==='/api/me')return reply(200,actor);
    const match=/^\/api\/resources\/([a-z]+)(?:\/(publish|withdraw))?$/.exec(req.url);
    if(!match)return reply(404,{error:'route'});
    const [,resource_id,action]=match, item=await records.read(resource_id);
    if(!action)return reply(200,{resource_id,owner_id:item.owner_id,data:{title:item.data.title,summary:item.data.summary}});
    const allowed=action==='withdraw'?actor.id===item.owner_id:mayPublish(actor,item.owner_id);
    const steps=action==='withdraw'?['withdraw']:publicationSteps();
    await records.transact({resource_id,subject_id:actor.id,expected_version:item.version,
      changes:allowed?steps.map(step=>({path:['state'],value:step==='publish'?'published':'draft'})):[]});
    return reply(action==='withdraw'?(allowed?200:403):publicationStatus(allowed),{ok:allowed});
  }catch{return reply(500,{error:'operation'});}
}).listen(Number(process.env.PORT),'127.0.0.1');
"""
