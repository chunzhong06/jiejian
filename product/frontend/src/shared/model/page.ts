import {ApiError} from '../api/http'
import type {Route} from '../lib/navigation'

export function assertProject(actual:string,expected:string){if(actual!==expected)throw new ApiError('STATE_PRECONDITION','读取的内容属于其他应用。')}
export type PageProps={projectId:string;name:string;official:boolean;refresh:()=>void;onError:(error:unknown)=>void;route:Route}
