import type {FlowStep} from '../api/operationFlows'

export type InputLocation='PATH'|'QUERY'|'HEADER'|'JSON_BODY'
export type InputSource='LITERAL'|'CASE_RESOURCE_ID'|'CASE_SUBJECT_ID'|'PRIOR_STEP_JSON_PATH'|'PRIOR_STEP_HEADER'|'PRIOR_STEP_COOKIE'|'PRIOR_STEP_LOCATION'
// 字段名称可以修改；动态槽使用独立身份，路径槽仍对应实际占位名称。
export type FlowParameter={slotId:string;name:string;value:string;source:InputSource;producer:string;path:string;location:InputLocation;json:boolean;secret:boolean;slot?:Record<string,unknown>}
export type EditableStep={id:string;method:string;path:string;parameters:FlowParameter[];bodyKind?:'JSON'|'EMPTY';base?:FlowStep}

export const sensitiveParameter=(name:string)=>/(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key|csrf)/i.test(name)
export const newParameter=(location:InputLocation):FlowParameter=>({slotId:'v_'+crypto.randomUUID().replaceAll('-',''),name:'',value:'',source:'LITERAL',producer:'',path:'$.id',location,json:false,secret:false})

function readParameter(name:string,value:unknown,location:InputLocation,slot?:Record<string,unknown>):FlowParameter{
  const fixed=slot?.source==='FIXED_LITERAL'
  const literal=fixed?slot.literal:value
  const draft=newParameter(location)
  return {...draft,name,value:slot&&!fixed?'':typeof literal==='string'?literal:JSON.stringify(literal)??'',
    json:literal!==undefined&&typeof literal!=='string',source:slot&&!fixed?slot.source as InputSource:'LITERAL',
    slotId:slot?.slot_id as string??draft.slotId,producer:slot?.producer_step_id as string??'',
    path:slot?.source_path as string??'$.id',secret:Boolean(slot?.secret),slot}
}

export function decodeSteps(items:FlowStep[]):EditableStep[]{
  return items.map(item=>{
    const template=item.request_template,body=template.body
    if(!['JSON','EMPTY'].includes(body.kind)||body.kind==='JSON'&&(body.value===null||typeof body.value!=='object'||Array.isArray(body.value)))
      throw new Error('此编辑器支持 JSON 对象正文。其他正文格式请继续通过原录制采用，已有流程保持不变。')
    const slots=template.input_slots??[],find=(id:unknown)=>slots.find(slot=>slot.slot_id===id)
    const parameters=[...Object.entries((body.value??{}) as Record<string,unknown>).map(([name,value])=>
      readParameter(name,value,'JSON_BODY',find((value as {$slot?:string}|null)?.$slot))),
      ...(template.query??[]).map(field=>readParameter(field.name as string,field.literal,'QUERY',find(field.slot_id))),
      ...(template.headers??[]).map(field=>readParameter(field.name as string,field.literal,'HEADER',find(field.slot_id))),
      ...slots.filter(slot=>slot.consumer==='PATH').map(slot=>readParameter(slot.slot_id as string,undefined,'PATH',slot))]
    return {id:item.id,method:template.method,path:template.path,parameters,bodyKind:body.kind,base:item}
  })
}

function jsonSlotIds(value:unknown):string[]{
  if(!value||typeof value!=='object')return []
  if('$slot' in value)return [(value as {$slot:string}).$slot]
  return Object.values(value).flatMap(jsonSlotIds)
}

function checkLiteral(value:unknown,name=''){
  const onlySlots=(value:unknown):boolean=>Boolean(value&&typeof value==='object'&&('$slot' in value||Object.values(value).every(onlySlots)))
  if(sensitiveParameter(name)&&!onlySlots(value))throw new Error('敏感参数请从前序请求提取，账号凭据在测试账号中准备。')
  if(value&&typeof value==='object')for(const [key,child] of Object.entries(value))checkLiteral(child,key)
}

export function compileSteps(items:EditableStep[],targetId:string,createdPath:string):FlowStep[]{
  const extractions=new Map<string,Map<string,Record<string,unknown>>>()
  const output=items.map((item,index)=>{
    const slots=new Map<string,Record<string,unknown>>(),query:Record<string,unknown>[]=[],headers:Record<string,unknown>[]=[],body:Record<string,unknown>={}
    const addSlot=(slot:Record<string,unknown>)=>{
      const id=slot.slot_id as string,previous=slots.get(id)
      if(previous&&JSON.stringify(previous)!==JSON.stringify(slot))throw new Error('同一请求的动态取值引用冲突，请分别设置来源。')
      slots.set(id,slot)
    }
    for(const parameter of item.parameters){
      const {name,location,source}=parameter
      if(!name.trim())throw new Error('请填写参数名称或移除空参数。')
      let value:unknown=source==='LITERAL'?(parameter.json?JSON.parse(parameter.value):parameter.value):undefined
      const dynamic=source!=='LITERAL',id=location==='PATH'?name:parameter.slotId
      if(dynamic&&sensitiveParameter(name)&&!parameter.secret)throw new Error('敏感参数必须标记为仅在执行内存中传递。')
      if(!dynamic){checkLiteral(value,name);if(location!=='JSON_BODY'&&typeof value!=='string')value=String(value)}
      if(dynamic||location==='PATH'){
        const {producer_step:_,consumer_step:__,...base}=parameter.slot??{}
        const prior=source.startsWith('PRIOR_STEP_')
        const slot={...base,slot_id:id,source:dynamic?source:'FIXED_LITERAL',consumer:location,
          consumer_step_id:item.id,secret:dynamic&&parameter.secret,literal:dynamic?null:value,secret_ref:null,
          producer_step_id:prior?parameter.producer:null,source_path:prior?parameter.path:null}
        addSlot(slot)
        if(prior){
          const producer=items.findIndex(step=>step.id===parameter.producer)
          if(producer<0||producer>=index)throw new Error('动态参数必须来自当前步骤之前的请求。')
          const kinds:Partial<Record<InputSource,string>>={PRIOR_STEP_JSON_PATH:'JSON_PATH',PRIOR_STEP_HEADER:'HEADER',PRIOR_STEP_COOKIE:'COOKIE',PRIOR_STEP_LOCATION:'LOCATION'}
          const kind=kinds[source]!,selectors:Record<string,string>={JSON_PATH:'json_path',HEADER:'header_name',COOKIE:'cookie_name'}
          const selector=selectors[kind]
          const extractor={extractor_id:id,kind,secret:parameter.secret,...(selector?{[selector]:parameter.path}:{}),...(base.max_length?{max_length:base.max_length}:{})}
          const group=extractions.get(parameter.producer)??new Map(),previous=group.get(id)
          if(previous&&JSON.stringify(previous)!==JSON.stringify(extractor))throw new Error('同一前序请求的取值名称冲突，请使用独立参数。')
          group.set(id,extractor);extractions.set(parameter.producer,group)
        }
        value={$slot:id}
      }
      const fields=location==='QUERY'?query:headers
      if(location==='JSON_BODY'){
        if(Object.hasOwn(body,name))throw new Error('JSON 正文中的参数名称重复。')
        body[name]=value
      }else if(location!=='PATH')fields.push({name,...(dynamic?{slot_id:id}:{literal:value})})
    }
    // 嵌套 JSON 中的原有槽仍由原声明拥有；修改普通字段不能悄悄丢弃这些依赖。
    for(const id of jsonSlotIds(body))if(!slots.has(id)){
      const slot=item.base?.request_template.input_slots?.find(value=>value.slot_id===id&&value.consumer==='JSON_BODY')
      if(slot)addSlot(slot)
    }
    if(item.path.includes('{case_resource_id}')&&!slots.has('case_resource_id'))addSlot({slot_id:'case_resource_id',source:'CASE_RESOURCE_ID',consumer:'PATH',consumer_step_id:item.id})
    const hasBody=Object.keys(body).length>0||item.bodyKind==='JSON'
    return {id:item.id,failure_policy:item.base?.failure_policy??'INCONCLUSIVE',purpose:item.id===targetId?'TARGET':'SETUP',identity_id:'CASE_SUBJECT',
      request_template:{...item.base?.request_template,method:item.method,path:item.path,query,headers,body:hasBody?{kind:'JSON',value:body}:{kind:'EMPTY'},input_slots:[...slots.values()],response_extractors:[...(item.base?.request_template.response_extractors??[])]},
      classifier:item.base?.classifier??{accepted:[{kind:'STATUS_IN',statuses:[200,201,204]}],denied:[{kind:'STATUS_IN',statuses:[401,403]}]},
      depends_on_step_ids:[...new Set([...(index?[items[index-1].id]:[]),...[...slots.values()].map(slot=>slot.producer_step_id).filter((id):id is string=>typeof id==='string')])]} as FlowStep
  })
  for(const step of output){
    const extractors=step.request_template.response_extractors??[]
    const replacements=extractions.get(step.id)??new Map()
    step.request_template.response_extractors=[...extractors.filter(item=>!replacements.has(item.extractor_id as string)&&!(step.id===targetId&&item.extractor_id==='created_resource_id')),...replacements.values(),
      ...(step.id===targetId&&createdPath?[{extractor_id:'created_resource_id',kind:'JSON_PATH',json_path:createdPath}]:[])]
  }
  return output
}
