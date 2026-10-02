// 受控前端测试与构建入口，构建同时发布页面身份及可独立核对的资源清单。
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { createHash } from 'node:crypto'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

// 标识来自受控构建输入；同一标识同时写入脚本和独立清单，避免只比较产品版本号。
function frontendBuildId() {
  const hash = createHash('sha256')
  function collect(directory: string): string[] {
    return readdirSync(directory, {withFileTypes:true}).flatMap(entry => {
      const path = join(directory,entry.name)
      return entry.isDirectory() ? collect(path) : [path]
    })
  }
  for (const path of [...collect('src'), 'index.html', 'package.json', 'pnpm-lock.yaml', 'vite.config.ts'].sort()) {
    hash.update(path.replaceAll('\\','/')+'\0'); hash.update(readFileSync(path)); hash.update('\0')
  }
  return hash.digest('hex')
}
const buildId = frontendBuildId()

export default defineConfig({
  build: {
    emptyOutDir: true,
    outDir: process.env.JIEJIAN_FRONTEND_OUT_DIR || 'dist',
  },
  define: { __JIEJIAN_FRONTEND_BUILD_ID__: JSON.stringify(buildId) },
  plugins: [react(), {
    name: 'jiejian-frontend-identity', apply: 'build', enforce: 'post',
    generateBundle(_options,bundle) {
      const assets = Object.values(bundle).map(item => ({path:item.fileName,
        sha256:createHash('sha256').update(item.type === 'chunk' ? item.code : item.source).digest('hex')}))
      this.emitFile({type:'asset',fileName:'frontend-manifest.json',source:JSON.stringify({schema_version:'1',build_id:buildId,assets})})
    },
  }],
  cacheDir: process.env.JIEJIAN_FRONTEND_CACHE_DIR || '.vite',
  server: { port: 5173, strictPort: true },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts' },
})
