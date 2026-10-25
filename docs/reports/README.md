# 作業レポート（更新管理）

提出・共有用の作業レポートと、**実行可能な残リスト**、**工夫／失敗ログ**、**参考文献・ライセンス**をこのディレクトリに置く。  
正本は Markdown。数値・再現情報は可能な限り **元リポジトリの成果物パス** を指す（再計算可能な一次情報をここに複製しない）。

## ファイル一覧

| ファイル | 内容 | 誰が更新するか |
|----------|------|----------------|
| [TODO.md](TODO.md) | **残リスト正本**（実行→成果物→レポート追記まで） | 着手/完了のたび |
| [AGENT.md](AGENT.md) | **Agent 指示メモ**（ワークフロー・引用必須・プロンプト例） | 運用が変わったとき |
| [design_notes.md](design_notes.md) | **工夫した点 / 試してダメだった点** | 判断・実験のたび |
| [references.md](references.md) | **参考リンク + ライセンス正本**（ID 参照） | 外部依存を触るたび **必須** |
| [sim2rl_work_report.md](sim2rl_work_report.md) | sim2RL 提出用本文（v0.1） | TODO 完了時に要約追記 |
| [single_arm_il_work_report.md](single_arm_il_work_report.md) | 片腕 IL（データセット→学習）の実施ログ（v0.1） | セッションのたび。手順は [15](../15_dataset_pipeline.md) |
| [run_registry.md](run_registry.md) · [run_registry.csv](run_registry.csv) | **学習・推論ラン台帳**（`R-…` / ハイパラ / 推論 / 動画） | 学習完了・推論のたび。`dataset_id` でデータ台帳と結合 |
| [dataset_registry.md](dataset_registry.md) · [dataset_registry.csv](dataset_registry.csv) | **データセット台帳**（`D-…` / タスク文 / カメラ / 派生元 / 使用ラン） | 録画・編集・派生のたび |
| [model_eval_results.md](model_eval_results.md) | 実機 10 試行の選別表 | 評価キャンペーン時。[24](../24_model_eval_campaign.md) |
| `../../.cursor/rules/reports-todo.mdc` | Cursor 常設ルール | AGENT 変更時に要約だけ同期 |
| 本 README | 索引・共通ルール | レポート追加時 |

リポジトリ直下の [`../../reports/`](../../reports/) は過去の実験メモ置き場。新規は **本ディレクトリ** を使う。

## 必須ポリシー（短い版）

1. **参考にしたらリンクを書く** — 本文に名前を出したら [references.md](references.md) に `url` 付き ID を追加する。  
2. **使ったらライセンスを書く** — コード・メッシュ・データ・SDK は `license` 欄必須。不明は提出前に解消。  
3. **失敗も残す** — うまくいかなかった試行は [design_notes.md](design_notes.md) の `F-` に残し、成功話だけにしない。  
4. 詳細手順・禁止事項は **[AGENT.md](AGENT.md) §9** が正。

## どう回すか（最短）

1. [TODO.md](TODO.md) の **P0 / `open`** を見る  
2. Agent に進めてもらうときは [AGENT.md](AGENT.md) §6 のプロンプトを貼る  
3. 完了後: evidence → レポート版上げ → **references / design_notes** → TODO を `done`  
4. 提出時: レポート §8 + references 末尾チェック + スライド（`sim2rl` の `make slides`）

## レポート本文の更新ルール

1. **版を上げる** — ファイル先頭の `版` と「改訂履歴」に 1 行追加（日付・要約・TODO ID または根拠パス）。
2. **事実と計画を分ける** — 「実施済み」は git SHA / `benchmarks/` / `docs/` の実測表に紐づける。「予定」は [TODO.md](TODO.md) だけに置く。
3. **数値は一次情報を優先** — 表を直すときは `sim2rl/benchmarks/<run>/` または `sim2rl/docs/*.md` を更新し、レポートは要約だけ合わせる。
4. **引用は ID で** — 論文・ツール名の羅列ではなく `R-…` / `D-…` / `F-…` を本文に埋め、一覧は references / design_notes に任せる。
5. **提出物セット** — スライドは `sim2rl/slides/sim2rl_overview.md`（`make slides`）、run 一式は `sim2rl/docs/presentation.md`。
6. **索引を同期** — レポートを追加したら本 README の表と [../README.md](../README.md) を更新する。

## 改訂テンプレ（各レポート先頭）

```markdown
| 項目 | 値 |
|------|-----|
| 版 | v0.x |
| 最終更新 | YYYY-MM-DD |
| 対象リポ | ~/robot/sim2rl @ <short-sha> |
| 提出用途 | 研究室ミーティング / 進捗報告 / アペンディクス |
```

## 関連

- sim2rl 発表ガイド: [`../../../sim2rl/docs/presentation.md`](../../../sim2rl/docs/presentation.md)
- メイク Stage ゲート: [`../../../sim2rl/docs/makeup_roadmap.md`](../../../sim2rl/docs/makeup_roadmap.md)
- so101-lab ロードマップ: [../roadmap.md](../roadmap.md)
