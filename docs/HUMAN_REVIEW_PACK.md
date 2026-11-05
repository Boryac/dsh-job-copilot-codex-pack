# 真人复核包（索引）

> **这不是一份已完成的评审记录。** AI 没有、也不能代替真人完成评审：只负责把材料摊开并留出填写位；
> 判定必须由真人按 `09_TESTING_ACCEPTANCE.md` 第 3 节 rubic 亲自完成。
> 在真人回填之前，`docs/REVIEW_T3.4.md` 的结论只能算 AI 自评，不能算人工评审。

## 包内文件

| 用例 | 档位 | 题数 | 文件 |
|---|---|---|---|
| `golden_06_bd_strong` | strong | 8 | [docs\review-pack\golden_06_bd_strong.md](golden_06_bd_strong.md) |
| `golden_07_gap` | gap | 9 | [docs\review-pack\golden_07_gap.md](golden_07_gap.md) |

## 复核怎么做（给真人，约 40 分钟）

1. 先读第 2 节四维表：判断档位是否与你的直觉一致，不一致先记下来；
2. 逐题读第 3 节：题面 → evidence_ref → 证据原文，问自己三个问题：
   - **相关性**：这道题是不是这个岗位真会问的？
   - **证据真实性**：题面里的数字/动作，能不能在证据原文里找到？
   - **可追问性**：如果你继续追问一层，候选人有没有可能露馅？
3. 在第 5 节表格里逐题打勾并写问题描述（只写总分不算评审完成）；
4. 填汇总：通过率（要求 ≥70%）、是否发现证据造假、是否认可档位；
5. 回填后把本文件与两份复核表一起更新到 `PROGRESS.md` 的已知缺口 1。

## 复核人建议来源

- 做过校园招聘/社招初筛的 HR（看题面自然度）；
- 用人部门面试官（看考察点是否对准岗位）；
- 至少 1 人，2 人以上更好（记录分歧点）。

## 生成命令

```bash
python3 scripts/export_review_pack.py --case golden_06_bd_strong --case golden_07_gap
# 想额外复核常见档位（discussable）时：
python3 scripts/export_review_pack.py --case golden_01_bd
```
