// Web V1 主题：集中维护产品语义色和基础控件尺度，不承载页面业务状态。

import type { ThemeConfig } from 'antd'

export const productTheme: ThemeConfig = {
  token: {
    colorPrimary: '#3659D9',
    colorInfo: '#3659D9',
    colorSuccess: '#188765',
    colorWarning: '#B87512',
    colorError: '#C83C3C',
    colorText: '#172033',
    colorTextSecondary: '#667085',
    colorBgBase: '#FFFFFF',
    colorBgLayout: '#F6F8FB',
    colorBorder: '#E4E7EC',
    colorLink: '#3659D9',
    borderRadius: 10,
    fontSize: 14,
    controlHeight: 40,
  },
  components: {
    Button: { primaryShadow: 'none' },
    Card: { headerBg: '#FFFFFF' },
    Layout: { bodyBg: '#F6F8FB', headerBg: '#FFFFFF', siderBg: '#FFFFFF' },
    Menu: { itemBg: '#FFFFFF', itemSelectedBg: '#EEF2FF', itemSelectedColor: '#3659D9' },
  },
}
