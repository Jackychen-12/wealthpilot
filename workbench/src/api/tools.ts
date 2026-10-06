import { runTool, useApi } from './index'

/**
 * 调一个只读工具。工具返回字符串表示"没取到"（原样当作空状态的说明），返回对象才是数据。
 * 这些工具就是 Agent 用的那一批，页面上的数和 AI 引用的证据对得上。
 */
export function useTool<T>(name: string, code: string, extra: Record<string, unknown> = {}) {
  const res = useApi(() => runTool<T | string>(name, { code, ...extra }), [name, code])
  const missing = typeof res.data?.data === 'string' ? res.data.data : ''
  return { ...res, value: res.data && !missing ? (res.data.data as T) : null, missing }
}
