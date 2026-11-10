import {renderHook} from '@testing-library/react'
import {expect,it} from 'vitest'
import {editorDraft,rememberEditorDraft,editorDraftGeneration,clearSubmittedDraft,discardProjectEditorDrafts,useDraftProtection} from './handoff'

it('迟到保存保留较新草稿，清理只影响所属应用',()=>{
  rememberEditorDraft('rule-a',{reason:'first'},'a')
  const submitted=editorDraftGeneration('rule-a','a')
  rememberEditorDraft('rule-a',{reason:'continued'},'a')
  rememberEditorDraft('rule-b',{reason:'other'},'b')
  clearSubmittedDraft('rule-a','a',submitted)
  expect(editorDraft<{reason:string}>('rule-a','a')?.reason).toBe('continued')
  expect(editorDraft('rule-a','b')).toBeUndefined()
  discardProjectEditorDrafts('a')
  expect(editorDraft('rule-a','a')).toBeUndefined()
  expect(editorDraft('rule-b','b')).toEqual({reason:'other'})
})

it('只在未保存编辑时保护刷新，普通页内卸载不触发离开确认',()=>{
  const view=renderHook(({dirty})=>useDraftProtection(dirty),{initialProps:{dirty:false}})
  const clean=new Event('beforeunload',{cancelable:true});window.dispatchEvent(clean)
  expect(clean.defaultPrevented).toBe(false)
  view.rerender({dirty:true})
  const dirty=new Event('beforeunload',{cancelable:true});window.dispatchEvent(dirty)
  expect(dirty.defaultPrevented).toBe(true)
  view.unmount()
  const left=new Event('beforeunload',{cancelable:true});window.dispatchEvent(left)
  expect(left.defaultPrevented).toBe(false)
})
