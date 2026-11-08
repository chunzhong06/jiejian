import {createContext,useContext} from 'react'
import type {Route} from './navigation'

export type WorkflowNavigation={open:(destination:string)=>void;finish:()=>void;label:string;route?:Route;reviewed?:boolean;finishLabel?:string;origin?:string;resume?:(destination:string)=>string;references?:Record<string,string>}
// 组合层只拥有当前工作位置，领域状态、草稿和未知回执仍由原工作面维护。
export const WorkflowContext=createContext<WorkflowNavigation|null>(null)
export const useWorkflow=()=>useContext(WorkflowContext)
