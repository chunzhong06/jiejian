// Web 产品入口：挂载根组件和全局样式，不在此处创建业务状态。

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import ControlShell from './app/ControlShell'
import { productTheme } from './app/theme'

createRoot(document.getElementById('root')!).render(<StrictMode><ConfigProvider locale={zhCN} theme={productTheme}><ControlShell /></ConfigProvider></StrictMode>)
