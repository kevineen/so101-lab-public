# 個人チェックリスト

手順の正本はドキュメント本体（例: [11_quest_teleop_runbook.md](../11_quest_teleop_runbook.md)）。  
ここにある `*.checklist.md` は **進捗記録用テンプレート**（リポジトリにコミットする）。

## 使い方

```bash
# リポジトリルートで — 自分用コピーを作る（gitignore 済み）
cp docs/checklists/quest_teleop.checklist.md docs/checklists/quest_teleop.local.md
cp docs/checklists/single_arm_il.checklist.md docs/checklists/single_arm_il.local.md
cp docs/checklists/model_eval.checklist.md docs/checklists/model_eval.local.md
```

| テンプレ | 正本 |
|----------|------|
| [quest_teleop.checklist.md](quest_teleop.checklist.md) | [11_quest_teleop_runbook.md](../11_quest_teleop_runbook.md) |
| [single_arm_il.checklist.md](single_arm_il.checklist.md) | [14_single_arm_il.md](../14_single_arm_il.md) · [15_dataset_pipeline.md](../15_dataset_pipeline.md) |
| [model_eval.checklist.md](model_eval.checklist.md) | [24_model_eval_campaign.md](../24_model_eval_campaign.md) |

あとは `*.local.md` の `- [ ]` を `- [x]` に変えながら進める。  
メモ欄に日付・ホスト名・気づきを書いてよい。**local ファイルは push しない**。

## なぜこの形か

| 案 | 判定 |
|----|------|
| 正本 runbook に直接チェック | みんなの進捗が衝突する → 不向き |
| `todo.txt` のみ（gitignore） | 軽いが、手順リンク・表が弱い |
| **テンプレ MD（コミット）+ `*.local.md`（gitignore）** | **推奨** — 手順は共有、進捗は手元 |

チーム共有したい発見は local ではなく runbook / Issue / PR に書く。
