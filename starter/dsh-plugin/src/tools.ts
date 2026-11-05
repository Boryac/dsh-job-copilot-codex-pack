// 工具聚合出口（包自检 scripts/verify.sh 依赖本文件存在）。
// 具体实现按 08 第 2 节拆到 src/tools/*.ts，这里只做 re-export，不放业务逻辑。
export { resumeStructurerTool, type ResumeStructurerInput } from "./tools/resume-structurer";
export { companyReconTool, isDeepEstimate, type CompanyReconInput, type CompanyReconOutput } from "./tools/company-recon";
export { jdDecoderTool, type JdDecoderInput } from "./tools/jd-decoder";
export { TIMEOUTS } from "./timeouts";
