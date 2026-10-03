// 页面保留容器向消费者提供可见性；隐藏页暂停读取和编辑阻塞，不另存业务状态。
import { createContext } from 'react'

export const WorkPageVisible = createContext(true)
