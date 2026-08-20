// Web 产品入口：挂载根组件和全局样式，不在此处创建业务状态。

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import ControlShell from './app/ControlShell'

createRoot(document.getElementById('root')!).render(<StrictMode><ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#4f46e5', colorInfo: '#0891b2', colorSuccess: '#15803d', colorWarning: '#b45309', colorError: '#b91c1c', colorBgLayout: '#f6f7fb', colorText: '#172033', borderRadius: 10 } }}><ControlShell /></ConfigProvider></StrictMode>)
