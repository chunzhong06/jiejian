// Web 产品入口：挂载根组件和全局样式，不在此处创建业务状态。

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import ControlShell from './app/ControlShell'
import { ProductThemeProvider } from './app/ThemeContext'

createRoot(document.getElementById('root')!).render(<StrictMode><ProductThemeProvider><ControlShell /></ProductThemeProvider></StrictMode>)
