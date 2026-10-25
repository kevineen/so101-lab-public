# 片腕 IL（ACT / SmolVLA）— 個人チェックリスト

正本手順: [17_act_record_train_infer.md](../17_act_record_train_infer.md) · [14_single_arm_il.md](../14_single_arm_il.md) · データセット: [15_dataset_pipeline.md](../15_dataset_pipeline.md) · 実施ログ: [作業レポート](../reports/single_arm_il_work_report.md)

```bash
cp docs/checklists/single_arm_il.checklist.md docs/checklists/single_arm_il.local.md
```

| 記録 | 値 |
|------|-----|
| 名前 / 日付 | |
| Pi IP | |
| GPU ホスト | |
| HF_USER | |
| タスク文 (`single_task`) | |
| dataset repo_id | |
| ACT / SmolVLA policy path | |
| 備考 | |

---

## Step 0 — 安全・独占

- [ ] LeLab 停止
- [ ] Web Remote 停止（または `--no-leader` / `leader_arm.enabled: false`）
- [ ] ESTOP 手の届く位置
- [ ] follower ホーム付近・干渉なし

メモ:

---

## Step 1 — キャリブ

- [ ] `my_follower` キャリブ JSON あり
- [ ] `my_leader`（**teleop**）キャリブ JSON あり（`my_leader_drive` ではない）
- [ ] by-id ポートが yaml / 環境変数と一致

メモ:

---

## Step 2 — テレオペ確認

- [ ] leader 手操作 → follower 追従
- [ ] `front` + `wrist` 映像 OK（キー名をメモ）
- [ ] Overload / 点滅なし

メモ:

---

## Step 3 — 録画

- [ ] `single_task` 文面を決めた
- [ ] leader と follower を同じ開始姿勢へ揃えた（nest: `~/.cache/so101-lab/home_poses.json`）
- [ ] スモーク 5 ep（録画 30 秒。スマホにエピソード数・記録時間・カメラ。記録開始のあと記録終了で止め、見てから残す→すぐ開始待ち。一時停止は時間とフレームだけ。早く終えるのは `n`）
- [ ] WSL（`../lerobot`、<user> 実行）で `lerobot-edit-dataset … info` をかけ、episodes / カメラキー / タスク文を確認した（[15 §2](../15_dataset_pipeline.md#dataset-review)）
- [ ] 失敗エピソードを除くときは、同じ WSL で別 `repo_id` と `--new_root` に保存し、元パスを残した
- [ ] 本番 ~50 ep（バリエーション含む）
- [ ] ローカルパス（と Hub に上げた場合はその URL）を作業レポートに書いた

メモ:

---

## Step 4 — 学習（GPU）

- [ ] ACT 学習完了（`policy.repo_id` / checkpoint パス）
- [ ] （任意）SmolVLA FT 完了
- [ ] ローカル MLflow（`./scripts/start_mlflow.sh` → http://127.0.0.1:5000）で損失曲線を一眼確認

メモ:

---

## Step 4b — 本番着手ゲート（[17 §5](../17_act_record_train_infer.md) と同じ）

- [ ] スモーク 5 本を仕分け、`*_kept` を作成した
- [ ] 合計 40〜50 本・位置のばらつきあり・`info.json` 確認済み
- [ ] `steps ≈ 5000 * (total_frames / 1332)` 計算済み
- [ ] 新しい `output_dir` を決めた（スモーク重みは比較用に残す）
- [ ] MLflow 起動（記録するとき）

メモ:

---

## Step 5 — 推論

- [ ] カメラキー・解像度が録画時と同じ
- [ ] Thor `policy_server` + Pi `robot_client` を実行した（[17](../17_act_record_train_infer.md)）
- [ ] ポッドまで到達した回数 / 試行回数: __ / __
- [ ] （任意）SmolVLA + 同じタスク文で推論
- [ ] 失敗時の原因メモ（カメラずれ・物体位置・速度など）

メモ:

---

## Step 5b — 本番評価と比較（10 試行プロトコル）

- [ ] 10 試行実施（nest から・物体は同じ位置）
- [ ] 成功 = ポッドを持ち上げ注ぎ切る、で集計: __ / 10
- [ ] どこで止まったかを試行ごとメモ（[17 §5](../17_act_record_train_infer.md) の判断表へ）
- [ ] S- セッションを作業レポートに追記した
- [ ] ACT が成立（目安 5/10 以上）したら **同じデータで** SmolVLA FT（[14 Step 4b](../14_single_arm_il.md)）と
      Diffusion Policy（[14 比較節](../14_single_arm_il.md)）を同じプロトコルで評価

メモ:

---

## やらないこと（このチェックリスト範囲）

- [ ] 物理 leader を Web Remote 第2駆動腕として使っていない
- [ ] leader に 12V を入れていない
- [ ] Pi 上で本格学習を強行していない
