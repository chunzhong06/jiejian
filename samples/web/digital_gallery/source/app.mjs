// 数字展馆的普通Web业务；登录、创建资料、预览、交付和撤回都经过真实请求。
import http from 'node:http';
import crypto from 'node:crypto';
import {page} from './page.mjs';
import {openCollection} from 'jiejian:records';
import {mayReceive,beforeDecision,afterDenied} from './delivery.mjs';
import {publicView} from './preview.mjs';
import {createAssets,readAsset} from './assets.mjs';
const roles=['owner','reviewer'];
const accounts={curator:{id:'curator',role:roles[0]},judge:{id:'judge',role:roles[1]}};
const sessions=new Map(),records=openCollection('galleries');
http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  let audit;
  const reply=async(status,data)=>{if(audit)await audit('MESSAGE','response_prepared',{source_location:'app.mjs/reply'});const body=Buffer.from(JSON.stringify(data));res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Content-Length':body.length});res.end(body);};
  const send=async(name,type)=>{const bytes=readAsset(name);if(audit)await audit('MESSAGE','response_prepared',{source_location:'app.mjs/send'});res.writeHead(200,{'Content-Type':type,'Content-Length':bytes.length,'Content-Disposition':`attachment; filename="${name}"`});res.end(bytes);};
  try {
    if(req.method==='GET'&&url.pathname==='/health')return reply(200,{ready:true});
    if(req.method==='GET'&&url.pathname==='/'){res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Content-Length':Buffer.byteLength(page)});return res.end(page);}
    if(req.method==='POST'&&url.pathname==='/api/login'){
      let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>512)return reply(413,{error:'请求太大'});}
      const actor=accounts[JSON.parse(raw).account];if(!actor)return reply(403,{error:'请选择演示账号'});
      const key=crypto.randomBytes(24).toString('hex');sessions.set(key,actor);res.setHeader('Set-Cookie',`gallery_session=${key}; HttpOnly; SameSite=Strict; Path=/`);return reply(200,actor);
    }
    const key=(req.headers.cookie||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('gallery_session='))?.slice(16);
    const actor=sessions.get(key);if(!actor)return reply(401,{error:'请先登录'});
    if(req.method==='GET'&&url.pathname==='/api/me')return reply(200,actor);
    if(req.method==='POST'&&url.pathname==='/api/galleries'){
      if(actor.role!=='owner')return reply(403,{error:'只有负责人可以创建项目'});
      await records.seed('campus','curator',{visibility:'internal',access_for:'',title:'校园数字展馆',summary:'展馆公开说明与展示内容'});
      createAssets();return reply(201,{resource_id:'campus',owner_id:'curator',message:'虚构展馆资料和文件已创建'});
    }
    const match=/^\/api\/galleries\/([a-z]+)(?:\/(preview|exhibition|internal|withdraw|internal-file))?$/.exec(url.pathname);
    if(!match)return reply(404,{error:'页面不存在'});
    const [,resource_id,action]=match,item=await records.read(resource_id);
    if(!item)return reply(404,{error:'请由负责人先创建展馆资料'});
    if(!action&&req.method==='GET')return reply(200,{resource_id,owner_id:item.owner_id});
    // 记录实际经过的调用和明确父引用；缺少诊断通道时业务仍按原权限继续。
    let parent=null;
    audit=async(kind,semantic_key,fields={})=>{
      if(typeof records.trace!=='function')return;
      try {
        const event=await records.trace(resource_id,{kind,semantic_key,parent_event_id:parent,
          subject_id:actor.id,source_component:'digital_gallery',source_location:'app.mjs/route',...fields});
        parent=event.event_id;
      } catch { /* 诊断失败不改变业务返回；界鉴将保留不完整路径。 */ }
    };
    await audit('ENTRY','request_received');
    await audit('IDENTITY','session_identity',{source_location:'app.mjs/session'});
    const authorize=allowed=>audit('AUTHORIZATION','permission_checked',{authorization_decision:allowed?'ALLOW':'DENY',source_location:'app.mjs/permission'});
    let stage='beforeDecision';
    const observedRecords={...records,transact:async command=>{
      const committed=await records.transact(command);
      await audit(stage==='afterDenied'?'RECOVERY':'PERSISTENT_EFFECT','business_committed',
        {operation_id:committed.operation_id,source_location:'delivery.mjs/'+stage});
      return committed;
    }};
    if(action==='preview'&&req.method==='GET'){await authorize(true);return reply(200,{resource_id,owner_id:item.owner_id,data:publicView(item)});}
    if(action==='exhibition'&&req.method==='GET'){await authorize(true);return send('exhibition.pdf','application/pdf');}
    if(action==='internal'&&req.method==='POST'){
      const allowed=mayReceive(actor,item.owner_id);
      await authorize(allowed);
      await beforeDecision(observedRecords,item,actor);
      if(!allowed){stage='afterDenied';await afterDenied(observedRecords,await records.read(resource_id),actor);return reply(403,{error:'无权取得内部完整包'});}
      return send('internal.zip','application/zip');
    }
    if(action==='internal-file'&&req.method==='GET'){
      const allowed=actor.id===item.owner_id||(item.data.visibility==='recipient'&&item.data.access_for===actor.id);await authorize(allowed);
      if(!allowed)return reply(403,{error:'内部文件尚未对你开放'});
      return send('internal.zip','application/zip');
    }
    if(action==='withdraw'&&req.method==='POST'){
      await authorize(actor.id===item.owner_id);
      if(actor.id!==item.owner_id)return reply(403,{error:'无权撤回'});
      await records.transact({resource_id,subject_id:actor.id,expected_version:item.version,changes:[{path:['access_for'],value:''},{path:['visibility'],value:'internal'}]});return reply(200,{ok:true});
    }
    return reply(405,{error:'操作不支持'});
  }catch(error){
    // 尚未创建的资源与执行冲突分别返回，页面才能准确引导首次准备。
    if(error?.message==='RECORD_RESOURCE_MISSING')return reply(404,{error:'请由负责人先创建展馆资料'});
    return reply(409,{error:'操作未完成，请核对资料是否已创建'});
  }
}).listen(Number(process.env.PORT),'127.0.0.1');
