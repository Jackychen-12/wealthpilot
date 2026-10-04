// 演示模式下各功能页的预填参数。必须与 backend/scripts/record_demo.py 里录制用的入参一致。
// 单独成文件、不引用快照，正式构建带上它也只是几个常量。
export const DEMO_DEFAULTS = {
  fund: '110011',
  stock: '600519',
  overlap: { a: '110011', b: '161725' },
  rebalance: { fund_code: '161725', mode: 'target_pct' as const, value: '15' },
}
