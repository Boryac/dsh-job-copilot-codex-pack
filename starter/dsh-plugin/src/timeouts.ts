/** 超时预算单一事实来源（02 第 4 节）。改这里就等于改全部工具，不要在工具里另写数字。 */
export const TIMEOUTS = {
  resumeStructurerMs: 30_000,
  companyReconMs: 30_000,
  jdDecoderMs: 20_000,
  analysisMs: 120_000,
} as const;
