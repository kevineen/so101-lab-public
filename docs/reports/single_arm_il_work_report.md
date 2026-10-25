# 片腕 IL 作業レポート（データセット → 学習）

| 項目 | 値 |
|------|-----|
| 版 | **v0.2** |
| 最終更新 | 2026-10-18 |
| 対象 | `~/robot/so101-lab`。環境確認時は `53b518f`（クリーン）、`vendor/lerobot` @ `943fae88`。学習と推論の git SHA はこの版では再取得していない |
| 手順 | [17_act_record_train_infer.md](../17_act_record_train_infer.md) · [15_dataset_pipeline.md](../15_dataset_pipeline.md) · [14_single_arm_il.md](../14_single_arm_il.md) |
| 提出用途 | ラボの片腕 ACT 進捗。数値の正本は各セッションの成果物パス |
| 関連 | [TODO T-P1-05](TODO.md) · [design_notes](design_notes.md) · [references](references.md) |

### 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v0.2 | 2026-10-18 | S-20261018-02: コーヒー 5 本の ACT 学習と Thor 推論。ポッド未到達 |
| v0.1 | 2026-10-18 | 雛形と環境確認（S-20261018-01）。録画・編集・学習・推論は未実施 |

手順のコマンドは [15](../15_dataset_pipeline.md) に置き、本ファイルは **実施した事実** だけを積む。予定は [TODO.md](TODO.md) の T-P1-05。

---

## 1. いま言えること

2026-10-18、コーヒーポッドのスモークは 5 本まで録画し、4090 の WSL で 5,000 step 学習し、Thor で約 40 秒動かした。腕は目標に向かって動いた。ポッドには届いていない。40〜50 本への追加と、その学習のやり直しはまだです。

| 段階 | 状態 |
|------|------|
| 環境確認 | 実施（S-20261018-01） |
| データセット作成 | コーヒー 5 本（S-20261018-02）。ペンの 5 本は別データセット（F-20261018-02） |
| 閲覧 | `info` は確認済み。映像の採用判断は未記録 |
| 編集 | 未実施 |
| ACT 学習 | スモーク 5,000 step まで。次は別 `output_dir` |
| 実機推論 | Thor で 1 試行。ポッド到達 0 |

---

## 2. セッションログ

新しい実施は表に 1 行足し、必要なら節を増やす。書かないものは「未記録」とし、空欄のまま成功扱いにしない。

| ID | 日付 | 段階 | 成果物 | メモ |
|----|------|------|--------|------|
| S-20261018-01 | 2026-10-18 | 環境確認 | カメラ静止画（下） | この時点ではデータセット 0 本 |
| S-20261018-02 | 2026-10-18 | 学習・推論 | コーヒー ACT の重み | 5 本。Thor で動作、ポッド未到達 |

### S-20261018-01 — 録画前の環境確認

| 欄 | 内容 |
|----|------|
| いつ | 2026-10-18 |
| どこ | Raspberry Pi（hostname `ubuntu`、aarch64）。作業ディレクトリ `~/robot/so101-lab` |
| git | so101-lab `53b518f`（確認時クリーン）。vendor/lerobot `943fae88` |
| 独占 | `web_remote` / `lelab` / `lerobot-*` プロセスは無し |
| シリアル | follower / leader とも 1a86 USB Serial（by-id 末尾で判別。`ttyACM` 番号は挿し直しで変わる） |
| キャリブ | `~/.cache/huggingface/lerobot/calibration/robots/so_follower/my_follower.json`（2026-10-18 03:16）。teleop `…/teleoperators/so_leader/my_leader.json`（2026-10-18 03:20）。`my_leader_drive.json` は別ファイルとして存在する |
| カメラ | `lerobot-find-cameras realsense` で D435 `${SO101_REALSENSE_SERIAL}`、USB 3.2、既定 640×480 @ 30。OpenCV では follower 先端 `/dev/video7`（by-path `…1.2.4.1:1.0-video-index0`）と leader 先端 `/dev/video17` がフレームを保存 |
| データセット | `~/.cache/huggingface/lerobot/` に `meta/info.json` は無い（calibration と outputs のみ） |
| Hub | `hf` コマンド無し。push はしていない |
| 閲覧ツール | venv に `lerobot-edit-dataset` と `lerobot-dataset-viz` はある。`rerun` は未導入 |
| 学習 | 未実施 |

確認時に残した静止画（上書きされうる。データセットではない）:

- `$HOME/outputs/captured_images/realsense_${SO101_REALSENSE_SERIAL}.png`
- `$HOME/outputs/captured_images/opencv__dev_video7.png`

### S-20261018-02 — コーヒー 5 本の ACT と Thor 推論

| 欄 | 内容 |
|----|------|
| いつ | 2026-10-18 |
| どこ | 録画とクライアントは Pi。学習は 4090 の WSL（`${SO101_GPU_SSH}`、`../lerobot`）。推論計算は Thor（`${SO101_THOR_TAILSCALE_IP}`） |
| git | このセッションでは SHA を再取得していない |
| 段階 | 作成 / 学習 / 推論 |
| 成果物 | 下記 §3〜§6 |
| 数字 | 5 episodes、1332 frames。推論 1 試行、ポッド到達 0 |
| タスク文 | `Pick up the coffee pot, pour it into a clear container, and put the coffee pod back where it was.` |
| 捨てたもの | なし（編集は未実施） |
| 次 | 映像を見て残す本を決め、デモを足してから別ディレクトリで学習し直す。[17](../17_act_record_train_infer.md) |

---

## 3. データセット

| 欄 | 内容 |
|----|------|
| repo_id（スタンプ付き） | `local/so101_single_coffee_smoke_20261018_085324` |
| root | `${SO101_GPU_SSH}:$HOME/.cache/huggingface/lerobot/local/so101_single_coffee_smoke_20261018_085324` |
| single_task | 上のタスク文 |
| episodes / frames | 5 / 1332（`info`、30 fps） |
| カメラキー | `front`（RealSense `${SO101_REALSENSE_SERIAL}`）、`wrist`（OpenCV by-path `…1.2.4.1:1.0-video-index0`）。どちらも 640×480 @ 30 |
| push | ローカルのみ |
| 採用 | このディレクトリをそのまま 5,000 step に渡した。編集後の採用ディレクトリはまだ無い |

---

## 4. 編集

未実施。

---

## 5. 学習

| 欄 | 内容 |
|----|------|
| ホスト | 4090 の WSL。作業ディレクトリ `../lerobot`。venv の Python は `/root` 以下 |
| コマンド時点の lerobot SHA | 未記録 |
| dataset root | 上の root |
| policy | `act`。batch 8、seed 1000、`push_to_hub=false` |
| output_dir | `../lerobot/outputs/train/act_so101_coffee_smoke_20261018` |
| device | cuda |
| ステップ数 / 損失 | 5,000 step（保存は `checkpoints/last` → `005000/pretrained_model`）。損失は学習側の報告で step 200 が 6.47、終了時 0.32。この版では MLflow を再読していない |
| Hub | ローカルのみ。学習後、ディレクトリは `a+rX` にした |

---

## 6. 推論

| 欄 | 内容 |
|----|------|
| 計算 | Thor `policy_server` `0.0.0.0:8080`。重み `$HOME/act_so101_coffee_smoke_20261018`。`policy_device=cuda`、`actions_per_chunk=100` |
| 腕 | Pi の `robot_client`。follower のみ、`max_relative_target=5`、切断時トルクオフは false |
| 試行 | 1。制御ループはおおよそ 40 秒（10:06:31–10:07:09 UTC）。クライアントは SIGINT で停止 |
| 結果 | 肩と肘が持ち上がる方向へ動いた。ポッドには届いていない。到達 0 / 試行 1 |
| 落ちた経路 | Pi の `lerobot-rollout` は行動前に Illegal instruction。Thor は draccus のパッチ前、設定読込で落ちた。どちらも [F-20261018-03](design_notes.md) |
| 停止後 | `go_so101_home.sh --arm follower`。shoulder_lift の最後の目標は -78.32°（nest -79.03°）。トルクは入ったまま |

---

## 7. セッションの追記型

```markdown
### S-YYYYMMDD-NN — 短い題

| 欄 | 内容 |
|----|------|
| いつ | YYYY-MM-DD |
| どこ | |
| git | so101-lab `<sha>`（dirty なら明記）。vendor/lerobot `<sha>` |
| 段階 | 作成 / 閲覧 / 編集 / 学習 / 推論 |
| 成果物 | パス |
| 数字 | episodes、frames、成功/試行。単位と n |
| タスク文 | |
| 捨てたもの | episode index と理由。無ければ「なし」 |
| 次 | |
```

追記したら先頭の版と改訂履歴を 1 行上げる。外部名を増やしたら [references.md](references.md)、判断や失敗は [design_notes.md](design_notes.md)。

**本番評価セッション（[17 §5](../17_act_record_train_infer.md) の 10 試行プロトコル）用の追記型**:

```markdown
### S-YYYYMMDD-NN — <モデル名> 本番評価（10 試行）

| 欄 | 内容 |
|----|------|
| いつ | YYYY-MM-DD |
| どこ | 推論計算 Thor / 腕 Pi |
| git | so101-lab `<sha>`。vendor/lerobot `<sha>` |
| 段階 | 推論（評価） |
| 対象重み | output_dir と checkpoint パス |
| データセット | repo_id と本数（学習に使ったもの） |
| 試行 | 10（nest から・物体同一位置） |
| 成功 | __ / 10（成功 = ポッドを持ち上げ注ぎ切る） |
| 止まった場所 | 試行ごとに 1 行（例: 3 試行目: 把持失敗で nest 前で停止） |
| 判断 | [17 §5](../17_act_record_train_infer.md) の判断表のどれを踏んだか |
| 次 | デモ追加 / steps 調整 / SmolVLA・Diffusion 比較へ |
```

ACT・SmolVLA・Diffusion で同じ形式の行を並べると、そのままモデル比較の表になります。
