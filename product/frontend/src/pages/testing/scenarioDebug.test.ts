import {expect,it} from 'vitest'
import {scenarioDebugSnapshot} from './scenarioDebug'
import type {BusinessScenario} from '../../entities/preparation/api/businessScenarios'

const item={id:'resource',permission:{intent_id:'rule',revision:1,intent_hash:'a'.repeat(64)},subject_identity_id:'owner',resource_id:'template'}
const document:BusinessScenario={document_type:'jiejian.business-scenario',schema_version:'1',id:'original',project_id:'app',revision:4,label:'创建并发布',description:'',experiments:[
  {id:'normal',label:'正常',kind:'NORMAL',control_experiment_id:null,invocations:[{id:'create',label:'创建',items:[item],depends_on:[],batch:null},{id:'publish',label:'发布',items:[{...item,resource_from:'create'}],depends_on:['create'],batch:null}]},
  {id:'member',label:'换主体',kind:'CHANGE_SUBJECT',control_experiment_id:'normal',invocations:[{id:'create',label:'创建',items:[item],depends_on:[],batch:null},{id:'publish',label:'发布',items:[{...item,subject_identity_id:'member',resource_from:'create'}],depends_on:['create'],batch:null}]}]}

it('正常流程前缀保留依赖，独立快照不覆盖原草稿',()=>{
  const snapshot=scenarioDebugSnapshot(document,document.experiments[0],'debug','create')
  expect(snapshot).toMatchObject({id:'debug',revision:1,experiments:[{id:'normal',invocations:[{id:'create'}]}]})
  expect(snapshot.experiments[0].invocations).toHaveLength(1)
  snapshot.experiments[0].invocations[0].items[0].resource_id='changed'
  expect(document.experiments[0].invocations[0].items[0].resource_id).toBe('template')
})

it('变体保留整个实验与完整正常对照，不将任意前缀冒充原变体',()=>{
  const snapshot=scenarioDebugSnapshot(document,document.experiments[1],'debug')
  expect(snapshot.experiments).toEqual(document.experiments)
  expect(()=>scenarioDebugSnapshot(document,document.experiments[1],'debug','publish')).toThrow('完整结构')
  expect(()=>scenarioDebugSnapshot(document,document.experiments[0],'debug','missing')).toThrow('步骤已变化')
})
