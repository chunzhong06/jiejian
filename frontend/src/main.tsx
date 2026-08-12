import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import ControlShell from './app/ControlShell'

createRoot(document.getElementById('root')!).render(<StrictMode><ConfigProvider theme={{ token: { colorPrimary: '#4f46e5', colorInfo: '#0891b2', colorSuccess: '#15803d', colorWarning: '#b45309', colorError: '#b91c1c', colorBgLayout: '#f6f7fb', colorText: '#172033', borderRadius: 10 } }}><ControlShell /></ConfigProvider></StrictMode>)
