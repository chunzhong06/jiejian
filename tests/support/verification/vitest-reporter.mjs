// Vitest 3 报告只输出文件、稳定编号、状态与耗时，测试名称和异常正文留在本地控制台。
import { mkdirSync, writeFileSync, renameSync } from 'node:fs'
import { dirname, relative } from 'node:path'

export default class VerificationReporter {
  onInit(ctx) { this.ctx = ctx; this.started = Date.now(); this.write({ status: 'RUNNING', files: [] }) }
  write(value) {
    const path = process.env.JIEJIAN_TEST_REPORT
    if (!path) return
    mkdirSync(dirname(path), { recursive: true })
    writeFileSync(`${path}.tmp`, JSON.stringify({ schema_version: '1', engine: 'vitest', ...value }, null, 2))
    renameSync(`${path}.tmp`, path)
  }
  onFinished(files = [], errors = []) {
    let collected = 0, failures = errors.length, skipped = 0
    const visit = (task) => {
      if (task.type === 'test') {
        collected++
        if (task.result?.state === 'fail') failures++
        if (['skip', 'todo'].includes(task.mode) || task.result?.state === 'skip') skipped++
      }
      for (const child of task.tasks || []) visit(child)
    }
    files.forEach(visit)
    if (files.some(f => f.result?.state === 'fail') && !failures) failures++
    this.write({ status: failures ? 'FAILED' : !collected ? 'EMPTY' : skipped ? 'INCOMPLETE' : 'PASSED',
      collected, failures, skipped, seconds: (Date.now() - this.started) / 1000,
      files: files.map(f => ({ path: relative(this.ctx.config.root, f.filepath).replaceAll('\\', '/'),
        outcome: f.result?.state || 'unknown', seconds: (f.result?.duration || 0) / 1000 })) })
  }
}
