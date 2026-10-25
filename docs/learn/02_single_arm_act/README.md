# 第2章 — 片腕 ACT（最初の通し実習）

> 🎯 **章のゴール**
> ①テレオペ→録画→（GPU）学習→実機推論の流れを説明できる
> ②カメラが「テレオペ確認」と「学習データ」で必要性が違うことを言える
> ③チェックリストを1周できる（成功率が低くてもパイプライン完走がゴール）

**実習の正本（コマンド）**: [17_act_record_train_infer.md](../../17_act_record_train_infer.md)（学習と Thor 推論）· [14_single_arm_il.md](../../14_single_arm_il.md)  
**データセットの作成・閲覧・編集**: [15_dataset_pipeline.md](../../15_dataset_pipeline.md)  
**実施ログ**: [single_arm_il_work_report.md](../../reports/single_arm_il_work_report.md)  
**進捗用**: [checklists/single_arm_il.checklist.md](../../checklists/single_arm_il.checklist.md)

## レッスン一覧

| # | レッスン | 内容 | 時間目安 |
|---|---------|------|----------|
| 1 | [01_teleop_record.md](01_teleop_record.md) | キャリブ・テレオペ・録画 | 1〜3時間 |
| 2 | [02_train_eval.md](02_train_eval.md) | ACT 学習・推論 | GPU 数時間 + 実機30分 |

> ⚠️ 長時間学習・実機トルク ON はユーザー確認のうえ実施（[AGENT.md](../../reports/AGENT.md)）。

### sim2rl との接続

- 実機前の安全・Sim2Real 感覚: [sim2rl 07_sim2real](../../../../sim2rl/docs/learn/07_sim2real/README.md)
- 「観測ベクトル → ポリシー」の感覚: [sim2rl 03_pytorch](../../../../sim2rl/docs/learn/03_pytorch/README.md)

⏭️ [01_teleop_record.md](01_teleop_record.md)
