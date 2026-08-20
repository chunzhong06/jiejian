/* PermissionContract 浏览入口：组合纯投影后的矩阵与只读关系图。 */

import { useMemo } from 'react'
import { Tabs } from 'antd'
import type { PermissionContractDto } from '../../../api/contracts'
import { PermissionGraph } from './PermissionGraph'
import { PermissionMatrix } from './PermissionMatrix'
import { buildPermissionMatrix } from './projection'
import '../permissions.css'

export function PermissionExplorer({ contract }: { contract: PermissionContractDto }) {
  const matrix = useMemo(() => buildPermissionMatrix(contract), [contract])
  return <Tabs items={[
    { key: 'matrix', label: '权限矩阵', children: <PermissionMatrix model={matrix} /> },
    { key: 'graph', label: '关系图', children: <PermissionGraph contract={contract} /> },
  ]} />
}
