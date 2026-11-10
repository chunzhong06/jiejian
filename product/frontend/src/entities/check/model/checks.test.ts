import {expect,it} from 'vitest'
import {actual,resultTitle} from './checks'
import type {ResultStory} from '../api/currentChecks'

const effect=(state:'CONFIRMED'|'ABSENT'|'UNKNOWN',judgement:string,assessment_state?:'CONFIRMED'|'ABSENT'|'UNKNOWN')=>({effect_id:'effect',business_label:'内部完整包已被接收',resource_concept:'内部资料',observed_state:state,assessment_state,judgement,evidence_refs:[]})

it('未闭合的未观察到结果不能写成没有发生',()=>{
  expect(actual(effect('ABSENT','尚未完成观察'))).toContain('尚未确认')
})

it('已闭合的缺席判断与确认发生分别使用准确业务表述',()=>{
  expect(actual(effect('ABSENT','措辞不参与分类','ABSENT'))).toBe('未完整收到内部包')
  expect(actual(effect('CONFIRMED','任何解释','CONFIRMED'))).toBe('完整收到内部包')
})

it('多目标修复保留部分通过，不用第一项成功代表整批验收',()=>{
  const value:ResultStory={run_id:'r1',project_id:'p1',verdict:'PASS',judgement:'本轮范围符合规则',policy_epoch:1,actions:[],claim_boundary:[],technical_references:[]};
  const reference={source_run_id:'original',source_case_id:'case',repair_fingerprint:'fingerprint'};
  value.repair_reviews=['VERIFIED','INCONCLUSIVE'].map(status=>({reference,verification:{repair_reference:'fingerprint',source_run_id:'original',run_id:'r1',status:status as 'VERIFIED'|'INCONCLUSIVE',reason_codes:[]},comparison:[]}));
  expect(resultTitle(value)).toBe('2 项原问题中，1 项修复已验证');
  value.repair_reviews[1].verification.status='VERIFIED';value.verdict='INCONCLUSIVE';
  expect(resultTitle(value)).toBe('2 项原问题已修复，其他结果尚未确认');
});
