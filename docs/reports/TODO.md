# 提出可能タスク残リスト（TODO）

実行して **数値・成果物・レポート追記** まで運べる残件の正本。  
エージェント／人間とも、着手前に本ファイルを読み、完了時にステータスと改訂履歴を更新する。

| 項目 | 値 |
|------|-----|
| 版 | **v0.8** |
| 最終更新 | 2026-10-18 |
| 対象 | `~/robot/sim2rl` 中心（実機経路は so101-lab 連携） |
| 運用 | [AGENT.md](AGENT.md) · [README.md](README.md) · [design_notes.md](design_notes.md) · [references.md](references.md) · [sim2rl_work_report.md](sim2rl_work_report.md) |

### 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v0.8 | 2026-10-18 | T-P1-05 notes に本番ゲート・10 試行評価プロトコル整備済みを追記。T-P1-07（SmolVLA FT 比較）・T-P1-08（MolmoAct2 片腕スモーク）を新設 |

| v0.7 | 2026-10-18 | T-P1-05 notes: 5 本スモークは学習と Thor 推論まで。手順は docs/17。status は open。T-P0-01 の版上げ先を v0.3 に変更 |
| v0.6 | 2026-10-18 | T-P1-05 notes: スマホにエピソード数、記録時間、ライブ映像、一時停止（D-20261018-09） |
| v0.5 | 2026-10-18 | T-P1-05 notes: スマホの録画は Start/Stop のあと残すと決めてから転送（D-20261018-08） |
| v0.4 | 2026-10-18 | T-P1-05 notes: 学習ログはローカル MLflow（docs/16） |
| v0.3 | 2026-10-18 | T-P1-06 完了（データセット手順と作業レポート雛形）。P2 サマリを status 別に修正 |
| v0.2 | 2026-10-17 | T-P1-05 追加（片腕 ACT/SmolVLA）。手順書は docs/14 |
| v0.1 | 2026-10-16 | 初版。レポート未了・ベンチ・メイク Stage・実機経路から抽出 |

---

## ステータス凡例

| 記号 | 意味 |
|------|------|
| `open` | 未着手。コマンド／手順が書ける |
| `in_progress` | 誰か（人 or agent）が作業中。`owner` を記入 |
| `blocked` | 依存・機材待ち。理由を `notes` に |
| `done` | 完了。`evidence` とレポート追記まで済 |
| `deferred` | 意図的に後回し（理由必須） |

**優先度**: `P0` = 提出の説得力に直結 · `P1` = レポート強化 · `P2` = 次ステージ／研究枠

**完了の定義（DoD）**:

1. 成果物パス（evidence）が存在する  
2. [sim2rl_work_report.md](sim2rl_work_report.md)（または新規レポート）に要約が載る  
3. 新規の外部依存があれば [references.md](references.md) に **url + license** 付き ID がある  
4. 工夫・失敗があれば [design_notes.md](design_notes.md) に D-/F-（`refs` 空禁止）  
5. 本リストの行が `done` になっていること  

詳細は [AGENT.md](AGENT.md) §9。

---

## サマリ（更新時に数を合わせる）

| 優先度 | open | in_progress | blocked | done | deferred |
|--------|------|-------------|---------|------|----------|
| P0 | 3 | 0 | 0 | 0 | 0 |
| P1 | 7 | 0 | 0 | 1 | 0 |
| P2 | 3 | 0 | 1 | 0 | 1 |

---

## P0 — 提出の主結果を足す

### T-P0-01 — 長時間 MuJoCo/Genesis reach ベンチ（主結果用）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 半日〜1日（GPU） |
| where | `~/robot/sim2rl` |
| why | 現行 `20261012-100431_bench` は 20k steps で未収束。提出の「学習できた」根拠にならない |
| do | `uv run python -m sim2rl.benchmark.run --algos ppo,a2c --seeds 1,2,3 --timesteps 200000`（または presentation 推奨の長時間）。必要なら `sim=genesis` 学習→評価は常に MuJoCo |
| evidence | `benchmarks/<ts>_*/benchmark.{md,csv,png}` · 各 `runs/*/eval_report.json` |
| report | `sim2rl_work_report.md` §5.2 を主結果に差し替え、20k 表は付録扱い。版を v0.3 へ（v0.2 は片腕 ACT の事実修正で使用済み） |
| notes | GPU 必須。コミットは csv/md/protocol のみ（png は gitignore 想定） |

### T-P0-02 — Stage-1 trace ゲート通過の run パスをレポートに固定

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 1–2h（既に EVA-ACT 実測ありならパス特定のみ） |
| where | `~/robot/sim2rl` |
| why | `docs/il_eva.md` に数値はあるが、提出用に `runs/<dir>/eval_report.json` へのポインタが無い |
| do | `runs/` から該当 EVA-ACT / IK 評価を特定。無ければ `python -m sim2rl.il.train ...` → `eval` を再実行 |
| evidence | `runs/<dir>/eval_report.json`（`task_metrics_mean.trace_rms_lateral_onpath` 等） |
| report | §5.3 に `run_dir` / git SHA を追記 |
| notes | ゲート: on-path RMS &lt; 2mm（`makeup_roadmap.md` Stage 1） |

### T-P0-03 — 提出物パッケージを一式生成

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 30–60min |
| where | `sim2rl` + 本ディレクトリ |
| why | ミーティング／提出で「何を渡せばよいか」が毎回曖昧になる |
| do | `cd ~/robot/sim2rl && make slides`（または `uv run slides/report_md.py slides/sim2rl_overview.md out.pptx`）。レポート版番号確認。代表 run を zip |
| evidence | `*.pptx` / `*.pdf` · `reports/sim2rl_work_report.md` · run zip |
| report | §8 チェックリストを `[x]` に。成果物パスを §4 表に追記 |
| notes | バイナリは git に入れず、パスまたは共有場所をレポートに書く |

---

## P1 — レポートを厚くする

### T-P1-01 — SGS 検証のシード拡大（傾向→主張）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 半日〜（GPU） |
| where | `~/robot/sim2rl` |
| why | `docs/sgs.md` §8 は 1–2 seed。「傾向」止まりで提出では弱い |
| do | reach/grasp で seed を追加（例 3+）。同一プロトコルで uniform vs SGS |
| evidence | `runs/*_sgs_*` · `sgs_history.csv` · `docs/sgs.md` 表更新 |
| report | 新節または §5.4 を拡張 |
| notes | 評価 ep=10 の分散に注意。可能なら ep を 20 に |

### T-P1-02 — パリティ再計測（現行 SHA・クリーンツリー）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 1–2h |
| where | `~/robot/sim2rl` |
| why | `full5` は dirty SHA。提出用はクリーンコミット上の数字が望ましい |
| do | `git status` クリーン確認 → `uv run python -m sim2rl.benchmark.parity --sims mujoco,mjwarp,genesis,newton,physx --tag full5-clean` |
| evidence | `benchmarks/<ts>_full5-clean/` |
| report | §5.1 を差し替えまたは併記 |
| notes | PhysX は extras / EULA 要。無ければ sims から外し notes に明記 |

### T-P1-03 — Quest テレオペ（so101-lab Phase D）作業レポート新設

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 2–4h（文書化中心。実機確認済みなら短く） |
| where | `~/robot/so101-lab` |
| why | sim2rl レポートの主対象外だがラボ提出では別軸の実績になる |
| do | [roadmap.md](../roadmap.md) Phase B–D と [11_quest_teleop_runbook.md](../11_quest_teleop_runbook.md) から実績を抽出し `quest_teleop_work_report.md` を作成 |
| evidence | `data/quest_teleop/*.jsonl` · bridges デモログ · runbook チェック結果 |
| report | 本 README 表に追加。sim2rl レポート §7 からリンク |
| notes | 実機が無い日は「契約 JSON / dry-run」までを提出可能範囲とする |

### T-P1-04 — 再現手順のワンページ（第三者向け）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 1h |
| where | 本ディレクトリ or `sim2rl/docs/` |
| why | 「他人が同じ数字を出せる」が売りなので、提出付録に短い再現手順が欲しい |
| do | 代表 1 ベンチ + 1 IL eval の 3 ステップ（checkout → uv sync --frozen → 再評価）を `repro_snippet.md` に |
| evidence | 当該ファイル |
| report | §10 参照に追加 |
| notes | `docs/reproducibility.md` / `docs/benchmarks.md` の要約で可。重複を避けリンク多めに |

### T-P1-05 — 片腕 ACT（実機デモ→学習→推論スモーク）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 半日〜1日（録画）+ GPU 数時間 |
| where | `~/robot/so101-lab` · GPU ホストの `vendor/lerobot` |
| why | 第2駆動腕はトルク不足のため OFF。片腕で ACT→（任意）SmolVLA を通し、ラボの学習経路を実証する |
| do | [17_act_record_train_infer.md](../17_act_record_train_infer.md) に従い、残したデモへ本数を足してから新しい `output_dir` で ACT を学習し、Thor で推論する。長時間学習・トルク ON は確認後。各セッションを作業レポートへ追記 |
| evidence | データセットディレクトリ（`meta/info.json`）· ACT checkpoint · 推論メモ（ポッド到達 / 試行） |
| report | [single_arm_il_work_report.md](single_arm_il_work_report.md) にセッション追記。sim2rl レポート §7 からリンク |
| notes | 通し手順は [17](../17_act_record_train_infer.md)（D-20261018-10、F-20261018-03）。2026-10-18 のコーヒースモークは 5 本・1332 フレーム、5,000 step。Thor で約 40 秒動き、ポッドには未到達。40〜50 本の再学習は未了なので status は open。Pi では ACT を計算しない。**2026-10-18: 着手ゲート・10 試行評価プロトコル・train_mlflow.sh 完全版を [17 §5](../17_act_record_train_infer.md) と[チェックリスト Step 4b/5b](../checklists/single_arm_il.checklist.md) に整備（準備完了。実施残）** |

### T-P1-07 — SmolVLA FT（ACT と同じデータでの比較）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | GPU 数時間（T-P1-05 のデータをそのまま使う） |
| where | `~/robot/so101-lab` · GPU ホストの `vendor/lerobot` |
| why | 学習カリキュラム第3章のゴール（「ACT の上に SmolVLA FT を載せる」）が未達。ACT との同一データ比較は提出の比較表になる |
| do | T-P1-05 の本番データセット（40〜50 本）で `--policy.path=lerobot/smolvla_base` の FT を [14 Step 4b](../14_single_arm_il.md) · [learn 03](../learn/03_smolvla/01_finetune.md) の手順で実行 → [17 §5](../17_act_record_train_infer.md) の 10 試行プロトコルで評価 |
| evidence | SmolVLA checkpoint · 評価セッション（作業レポート S- 行） |
| report | [single_arm_il_work_report.md](single_arm_il_work_report.md) に ACT と同じ形式の評価行を並べる |
| notes | タスク文は学習・推論で一致させる（learn 第3章のゴール②）。ACT が 5/10 未満なら先に T-P1-05 を回しきる |

### T-P1-08 — MolmoAct2 片腕スモーク（VLA サーバの練習）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 2〜3h（Thor・Pi 両方の fork 編集を含む） |
| where | `~/robot/so101-lab` · vendor/lerobot（両ホスト） |
| why | 学習第4章が「VLA サーバを一度立てる練習」として提案している未実施項目。双腕換装前の Thor 推論経路の実証になる |
| do | [10](../10_molmoact2_thor.md) の手順で Pi/Thor 両方の `SUPPORTED_POLICIES` に `molmoact2` を追加 → 公開 `lerobot/MolmoAct2-SO100_101-LeRobot`（片腕・cam0/cam1）で policy server と robot client の通信確認 |
| evidence | Thor サーバログ（`Policy type: molmoact2`）· クライアント接続ログ |
| report | 本ファイルと design_notes（詰まったら F- 候補） |
| notes | カメラキーを checkpoint の `observation.images.*` に合わせる必要あり（[10](../10_molmoact2_thor.md) チェックポイント節）。関節次元が片腕 6 の重みなので本格評価はしない（通信確認がゴール） |

---

## P2 — 次ステージ（実装が必要だが提出ストーリーになる）

### T-P2-01 — メイク Stage-2 `press`（接触力）の最小実装＋ゲート計測

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 数日 |
| where | `~/robot/sim2rl` |
| why | ロードマップ上の次ゲート。実装＋1 表でレポート章が増える |
| do | `makeup_roadmap.md` Stage 2 設計に沿い `task=press` を実装 → eval 指標を記録 |
| evidence | `src/sim2rl/tasks/` · `eval_report.json` · roadmap 更新 |
| report | 新節「Stage-2」または別レポート |
| notes | **2026-10-24: タスク本体は実装済み**（`task=press` + `robot=so101_touch` + 力帯メトリクス、単体テスト・スモークrun済み。DRと特権Teacher-Student蒸留の仕組みも同時実装。手順は sim2rl learn/07 L4-L5）。残作業は学習イテレーションでゲート（帯内>90%・3N超過0%・RMS<0.3N）を通すこと |

### T-P2-06 — 力覚観測ILスモーク（Present_Load → ACT A/B）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 半日（録画）+ GPU 数時間 |
| where | Pi（録画）· GPU ホスト（学習）· `~/robot/lerobot` |
| why | VFA（Vision-Force-Action）方式の実機側入門。力覚proxyを観測へ混ぜたACTが既存モデル比で掴み安定に効くかを1枚の表にする |
| do | [learn 06](../learn/06_force_obs/01_present_load.md) の手順: `read_present_load=true` で20〜40本録画 → `scripts/train_mlflow.sh` でACT学習 → [docs/24](../24_model_eval_campaign.md) の10試行プロトコルで既存4モデルとA/B |
| evidence | データセット（`meta/info.json` の state 12次元）· ACT checkpoint + MLflow run · 評価セッション |
| report | [single_arm_il_work_report.md](single_arm_il_work_report.md) に比較行を追加 |
| notes | **2026-10-24: コード側は実装済み**（lerobotフォーク `so_follower` の `read_present_load`。スカラー観測は`observation.state`へ統合されるためポリシー変更不要）。残るは人間による実機録画・学習実行。`observation.state`が12次元になるため既存6次元checkpointとの混用は不可（データセット側で区分） |

### T-P2-02 — 実機 `real_eval.csv` プロトコル実施（reach 最低限）

| 欄 | 内容 |
|----|------|
| status | `blocked` |
| effort | 半日（実機＋安全確認） |
| where | Pi + sim2rl / so101-lab |
| why | Sim2Real の提出根拠 |
| do | `docs/benchmarks.md` の real_eval 形式で 10 ep。安全チェックリスト（learn/07）必須 |
| evidence | `runs/<sim_run>/real_eval.csv` |
| report | §5 に実機表 |
| notes | **blocked**: 実機占有・LeLab/WebRemote 非同時起動。準備できたら `open` に戻す。**2026-10-18: 実施ツールを実装済み** — sim2rl `export_onnx`（best.zip→policy.onnx）＋ 本repo `apps/real_eval`（Pi 完結・ONNX 推論・安全策・CSV 出力。[docs/18](../18_real_eval.md)）。単体テストあり（モック実機）。残るは人間による実機実行のみ |

### T-P2-03 — Bi-ACT 実測表（論文対応の最低限 ablation）

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 1–2日 |
| where | `~/robot/sim2rl` |
| why | `algo=bi_act` は実装済みだが提出用の自前数値が薄い |
| do | 三つ組観測 ON/OFF または prior 切替で同一デモ比較 |
| evidence | `docs/il_biact.md` に実測節追加 · runs |
| report | IL 節に Bi-ACT 行を追加 |
| notes | 力フィードバック無しデモでも τ ストリーム比較は可 |

### T-P2-04 — 双腕シーン / 干渉ゲート（MuJoCo sim）

| 欄 | 内容 |
|----|------|
| status | `deferred` |
| effort | 数日 |
| where | so101-lab `scripts/sim_check.py` / sim2rl assets |
| why | 双腕テレオペの安全側。提出より運用優先になりやすい |
| do | [12_mujoco_sim.md](../12_mujoco_sim.md) 「今後の拡張」 |
| evidence | 双腕 MJCF · CI ゲート |
| report | quest / sim レポートへ |
| notes | deferred: P0/P1 完了後 |

### T-P2-05 — Colab ノートで第三者再現スモーク

| 欄 | 内容 |
|----|------|
| status | `open` |
| effort | 1–2h |
| where | `notebooks/sim2rl_benchmark_colab.ipynb` |
| why | 再現性アピールの実演 |
| do | COMMIT を固定してスモーク→表出力→zip |
| evidence | Colab 出力 or ローカル再実行ログ |
| report | §5 または再現付録に「Colab 確認日」 |
| notes | クラウド課金に注意（`docs/cloud_gpu.md`） |

---

## 完了済み（アーカイブ）

完了したら行をここに移し、`evidence` とレポート版を残す。

### T-P1-06 — データセット一連の手順と作業レポート雛形

| 欄 | 内容 |
|----|------|
| status | `done` |
| done | 2026-10-18 |
| where | `~/robot/so101-lab` |
| why | 作成・閲覧・編集・学習引き渡しを、実施のたびに提出用へ写せる形にする |
| evidence | `docs/15_dataset_pipeline.md` · `docs/reports/single_arm_il_work_report.md`（v0.1、環境確認のみ） |
| report | single_arm_il_work_report v0.1。design_notes `D-20261018-01`。references `R-DOC-LEROBOT-DATASET-TOOLS` · `R-DOC-SO101-DATASET-PIPELINE` |
| notes | 録画・学習は T-P1-05 のまま open。本項は文書化のみ |

---

## アイテム追加テンプレ（コピー用）

```markdown
### T-<Px>-<NN> — <短いタイトル>

| 欄 | 内容 |
|----|------|
| status | `open` |
| owner | （着手時に記入） |
| effort | |
| where | `~/robot/sim2rl` or `~/robot/so101-lab` |
| why | 提出・レポートにどう効くか |
| do | 具体コマンド / 手順（コピペ可能に） |
| evidence | 期待する成果物パス |
| report | どのファイルのどの節を更新するか |
| notes | 依存・機材・注意 |
```
