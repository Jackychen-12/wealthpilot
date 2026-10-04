// 演示模式下可回放的问题清单。单独成文件：正式构建只会带上这个空数组，不会把快照打进包里。
import { DEMO } from '../api'

const questions: string[] = DEMO
  ? (await import('./fixtures.json')).default.chats
    ? Object.keys((await import('./fixtures.json')).default.chats)
    : []
  : []

export default questions
