import {expect,it} from 'vitest'
import {actual} from './checks'

const effect=(state:'CONFIRMED'|'ABSENT'|'UNKNOWN',judgement:string)=>({effect_id:'effect',business_label:'内部完整包已被接收',resource_concept:'内部资料',observed_state:state,judgement,evidence_refs:[]})

it('未闭合的未观察到结果不能写成没有发生',()=>{
  expect(actual(effect('ABSENT','尚未完成观察'))).toContain('尚未确认')
})

it('已闭合的缺席判断与确认发生分别使用准确业务表述',()=>{
  expect(actual(effect('ABSENT','在已闭合的观察范围内未发生这项业务结果'))).toBe('未完整收到内部包')
  expect(actual(effect('CONFIRMED','已确认'))).toBe('完整收到内部包')
})
