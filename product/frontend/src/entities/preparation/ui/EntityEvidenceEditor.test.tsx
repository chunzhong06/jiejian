import {useState} from 'react'
import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it} from 'vitest'
import {EntityEvidenceEditor} from './EntityEvidenceEditor'
import type {EntityEvidence} from '../api/operationFlows'

it('连续输入多个公开状态时保留分隔符，同时清除状态配置会清除其枚举',()=>{
  let current:EntityEvidence[]=[]
  function Harness(){
    const [value,setValue]=useState<EntityEvidence[]>([{effect_id:'effect',query:{request:{},resource_path:'$.id',owner_path:'$.owner',data_path:'$',condition_state_path:'$.status',condition_state_values:[]}}])
    current=value
    return <EntityEvidenceEditor effects={[{effect_id:'effect',label:'内部安排',kind:'DATA_DISCLOSURE',protected_projection:['internal_note']}]} value={value} onChange={setValue}/>
  }
  render(<Harness/>);
  const input=screen.getByLabelText('允许采集的公开状态')
  fireEvent.change(input,{target:{value:'DRAFT, '}})
  expect(input).toHaveValue('DRAFT, ')
  fireEvent.change(input,{target:{value:'DRAFT, APPROVED'}})
  expect(current[0].query.condition_state_values).toEqual(['DRAFT','APPROVED'])
  fireEvent.change(screen.getByLabelText('资源状态字段（可选）'),{target:{value:''}})
  expect(current[0].query.condition_state_values).toEqual([])
  expect(current[0].query.condition_state_path).toBeNull()
})
