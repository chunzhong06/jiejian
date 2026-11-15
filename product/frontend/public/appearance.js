// 在应用模块和样式加载前采用已保存主题，避免暗色重开时先绘制白色画布。
try {
  document.documentElement.dataset.studioTheme = localStorage.getItem('jiejian.studio.theme') === 'dark' ? 'dark' : 'light';
} catch {
  document.documentElement.dataset.studioTheme = 'light';
}
