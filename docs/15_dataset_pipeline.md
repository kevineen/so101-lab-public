# 15 — データセット作成・閲覧・編集、そのあと学習へ

片腕 follower のデモを **ローカルに録り、中身を見て、失敗を除き、GPU ホストで ACT に渡す**までの手順です。  
キャリブ・テレオペ・実機推論の正本は [14_single_arm_il.md](14_single_arm_il.md)。ここはデータセットのライフサイクルと、**実施事実の残し方**だけを担当します。

提出用の事実は [reports/single_arm_il_work_report.md](reports/single_arm_il_work_report.md) に追記します。  
**台帳**: データセットは [dataset_registry](reports/dataset_registry.md)（`D-…`）、学習ランは [run_registry](reports/run_registry.md)（`R-…` · `dataset_id` で結合）。  
チェックリスト（`docs/checklists/single_arm_il.local.md`）は手元の進捗用で、提出本文にはしません。

出典: [R-DOC-LEROBOT-DATASET-TOOLS](reports/references.md) · [R-DOC-LEROBOT-IL](reports/references.md) · [R-CODE-LEROBOT](reports/references.md) · [R-DOC-SO101-SINGLE-IL](reports/references.md)

---

## このラボでの決め（2026-10-18）

| 項目 | 決め |
|------|------|
| 駆動 | follower のみ（`my_follower`） |
| デモ | 物理 leader を手で動かす（`my_leader`）。`my_leader_drive` は使わない |
| 保存 | 録画中は Pi。スマホで残すと決めた本だけ、次の記録開始の前とセッションの最後に rsync。全部送れたら Pi 側は消す。第三者への配布は例外で [25 — HF Hub 配布](25_dataset_model_release.md) の手順でのみ行う |
| プレビュー | スマホの 8770 にエピソード数、記録時間、`front` / `wrist` のライブ画像。確認中は間引き画像。`rerun` は使わない（`--display_data=false`） |
| 学習 | この Pi（aarch64）では回さない。データセットディレクトリを GPU ホストへ渡す |
| 閲覧・選別 | **4090 の WSL** で行う。Pi ではやらない。残した本は WSL にあり、Pi 側は転送後に消えている。映像の確認と `delete_episodes`（動画の書き直し）は WSL の lerobot（`../lerobot`） |
| 独占 | 録画中は LeLab と Web Remote を起動しない。8770 のブラウザはシリアルを開かないので併用する |
| 初期位置 | `lerobot-record` は姿勢ファイルを持たない。開始は leader の現在角。録画前に両腕を nest へ揃える（下） |
| 本数 | スモーク **5**。学習用の目安 **40〜50**（場所を変えて繰り返す） |
| 時間 | 録画 **30 秒**（`n` / 記録終了で早く切る）。物戻しは確認のあと開始待ちで行い、揃ったら記録開始。fps は **30** |

`configs/so101_dual_cam.yaml` の `leader_arm.enabled` が `true` でも、Web Remote プロセスを上げなければ録画とシリアルは衝突しません。

シェル（録画のたびに）:

```bash
# so101-lab リポジトリ直下で実行
# venv の activate は不要。録画スクリプトが ~/robot/lerobot/.venv を自動で使う

export FOLLOWER_PORT=${SO101_FOLLOWER_PORT}
export LEADER_PORT=${SO101_LEADER_PORT}
export FOLLOWER_ID=my_follower
export LEADER_ID=my_leader
```

カメラキーは学習・推論と揃えます（[14](14_single_arm_il.md) と同じ）。

| キー | 実機（2026-10-18 確認） |
|------|-------------------------|
| `front` | RealSense D435 シリアル `${SO101_REALSENSE_SERIAL}`（USB 3.2、640×480 @ 30） |
| `wrist` | follower 先端。by-path `…usb-0:1.2.4.1:1.0-video-index0`（この日は `/dev/video7`） |

---

## 1. 作成（録画）

ESTOP を手元に置いてから実行します。follower にトルクが入ります。

### 初期位置 {#initial-pose}

録画に使う姿勢は四つあります。名前が似ていても、指している場所は別です。

| 名前 | どこにあるか | 録画での役割 |
|------|----------------|--------------|
| キャリブの 0° | 可動域の中点（half-turn homing）。`~/.cache/huggingface/lerobot/calibration/robots/so_follower/my_follower.json` | 角度の原点。開始姿勢としては使わない |
| 未保存の Web Remote ホーム | 全関節 0°、グリッパ 50（`H` / パッド Y の既定） | nest 未保存のときの戻り先 |
| 保存済み nest | `~/.cache/so101-lab/home_poses.json`。[03 — 初期位置](03_web_remote.md#nest) | 録画前に両腕を揃える安全姿勢 |
| エピソードの開始 | 録画ループが始まった瞬間の **leader の関節角** | follower が追従する初期位置。データに残る |

`lerobot-record` は nest を読みません。接続時に決まった座標へ戻る処理もなく、`connect()` は腕がすでに休止姿勢にある前提でトルクを入れます。次のエピソードの開始は、開始待ちのあいだに leader で戻した場所です（スマホ録画では vendor のリセット待ちは飛ばす）。開始待ち中のフレームは保存されません。

録画の前:

1. 机とケーブルに当たらない姿勢で、Web Remote から両腕の nest を保存する（保存済みなら省略）
2. Web Remote を止める
3. `./scripts/go_so101_home.sh` で両腕を nest へ戻す
4. leader と follower の見た目が揃っていることを確認してから `lerobot-record` を起動する

leader と follower が離れたまま録画ループに入ると、follower は最初の制御周期で leader の角へ動きます。

2026-10-18 11:56（JST）に保存した nest（度）。保存し直したあとは JSON が正本です。

| 関節 | follower | leader |
|------|----------|--------|
| shoulder_pan | -1.1 | -1.3 |
| shoulder_lift | -79.0 | -100.0 |
| elbow_flex | 36.5 | 86.0 |
| wrist_flex | 49.9 | 22.3 |
| wrist_roll | -81.2 | -93.6 |
| gripper | 0.7 | 0.0 |

各エピソードの開始は、この nest 付近で揃えます。変えるのは物体の位置です。

スマホ録画の「両方 nest へ」トグルは段階的に戻す: まず wrist_flex（モーター ID 4 = 手首ピッチ）を nest 角度まで戻し、揃ったら他の関節をまとめて nest へ戻して保持する。手首を先に水平へ戻すことで、他関節の戻し中に把持物が振れないようにする。先行関節は `SO101_RECORD_NEST_FIRST_JOINT` で変えられ、1.5 秒間まったく動かなければ自動で全関節 nest へ切替する。

### 本数と時間 {#episodes-and-time}

公式 CLI の既定は、録画 60 秒・リセット 60 秒・50 本です（[IL on real robots](https://huggingface.co/docs/lerobot/il_robots)、実装は `~/robot/lerobot` の `DatasetRecordConfig`）。このラボの pick-and-place は次にします。

| パラメータ | 公式既定 | このラボ |
|------------|----------|----------|
| `--dataset.num_episodes` | 50 | スモーク 5。学習用 40〜50 |
| `--dataset.episode_time_s` | 60 | 30 |
| `--dataset.reset_time_s` | 60 | 15（キーボード単体の `lerobot-record` 用。`record_with_buttons` では残す／捨てるのあと開始待ちへ進み、この待ちは使わない） |
| `--dataset.fps` | 30 | 30 |

タスクが 30 秒より早く終わったら `n`、または同じ Wi-Fi のブラウザの記録終了で切ります。上限まで待つと、終わったあとの静止が学習データに入ります。記録終了のあと、映像を見て「残す」か「捨てる」かを決めます。どちらも押すとすぐ次の開始待ちへ進みます（「成功」は不要）。物と腕の戻しは開始待ちで行い、揃ったら記録開始です。残した本は、次の記録開始を押す前に PC へ送ります。捨てた本は送りません。一時停止は記録時間とフレームだけ止め、腕の追従は続けます。

公式の集め方は、掴み方を揃え、**場所ごとに約 10 本、合計 50 本**です。カメラは固定し、対象物は `front` と `wrist` の両方に映します。

判断の記録: [D-20261018-02](reports/design_notes.md)。

最初は **5 エピソード**。本番の目安は 40〜50（[14 Step 3](14_single_arm_il.md)）。

`repo_id` には実行時刻が付きます（例: `local/so101_single_pickplace_smoke_20261018_130000`）。同じ名前で上書きしたいときだけ `--dataset.no_stamp=true`。

続きから取る場合は、ログに出たスタンプ付き `repo_id` と `--resume=true`、さらに **`--dataset.root`（必須）** を渡します。`num_episodes` は今回追加する本数です。`\` の直後に空白を入れないこと。

```bash
TASK="Pick the red neck of snake and place drop in the silver bowl"
REPO_ID=local/so101_single_snake_bowl_20261022_194956
ROOT=$HOME/.cache/huggingface/lerobot/$REPO_ID

./scripts/record_with_buttons.sh \
  --resume=true \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID \
  --teleop.type=so101_leader \
  --teleop.port=$LEADER_PORT \
  --teleop.id=$LEADER_ID \
  --robot.cameras="{ \
  front: {type: intelrealsense, serial_number_or_name: \"${SO101_REALSENSE_SERIAL}\", width: 640, height: 480, fps: 30}, \
  wrist: {type: opencv, index_or_path: /dev/v4l/by-path/platform-<wrist-camera-by-path> width: 640, height: 480, fps: 30} \
  }" \
  --dataset.repo_id=$REPO_ID \
  --dataset.root=$ROOT \
  --dataset.num_episodes=45 \
  --dataset.episode_time_s=30 \
  --dataset.reset_time_s=15 \
  --dataset.single_task="$TASK" \
  --dataset.push_to_hub=false \
  --dataset.streaming_encoding=true \
  --dataset.encoder_threads=2 \
  --display_data=false
```

引数は `lerobot-record` と同じです。キーボードだけで進めるときは、スクリプトの代わりに `lerobot-record` を使います。

録画ターミナルのキー（矢印が届かない SSH でも同じ）。意味は画面によって変わります。

| キー | 開始待ち | 録画中 | 確認中 |
|------|----------|--------|--------|
| `n` | 録画を始める | 止めて確認へ | 残す（すぐ開始待ちへ） |
| `r` | この待ちをやり直す | 見ずに捨てる | 捨てる（すぐ開始待ちへ） |
| `q` | セッションを止める | セッションを止める（この本は残さない） | セッションを止める（この本は残さない） |

### 同じ Wi-Fi のブラウザ（記録開始 / 記録終了 / 一時停止） {#record-buttons}

リーダーを両手で持ったまま、スマホから録画を始め、止め、残すか捨てるかを決めます。腕が接続されたあと、ターミナルに URL が出ます。スマホは Pi と同じ Wi-Fi で、そのアドレスを開きます（待受は `0.0.0.0:8770`）。

画面の上に、いまのエピソード（例: `1 / 5`）、保存済み本数、記録時間が出ます。開始待ち・録画中は `front` と `wrist` のライブ画像です。確認中は、その本の間引き画像をスライダで見ます。

| 画面 | 表示 | ボタン | キーボード | 腕 |
|------|------|--------|------------|----|
| 開始待ち | エピソード n/N、記録 0:00 / 上限、ライブ映像 | 記録開始、両方 nest へ | `n` | follower はリーダーに追従する（または nest 保持）。物戻しはここで行う。録画はしない |
| 録画中 | 記録の経過 / 上限、ライブ映像、フレーム数 | 記録終了、一時停止、捨てる | `n` で終了、`r` で捨てる | フレームを書く。記録終了ではまだ保存しない |
| 一時停止 | 記録時間は止まったまま。映像は動く | 再開、記録終了 | なし | follower は追従する。フレームは増えない |
| 確認 | 記録時間は止まった値。間引き画像 | 残す / 捨てる | `n` / `r` | follower は止まったまま。押すとすぐ次の開始待ちへ（「成功」は不要） |

一時停止に対応するキーはありません。記録時間（`episode_time_s`）とデータセットへ書くフレームだけ止まり、再開で続きから数えます。トルクは切れません。

「残す」は、次の記録開始の前に指定 PC へ送ります。最後の 1 本はセッション終了時に送ります。捨てた本は保存せず、送りません。確認中にリーダーを動かしても follower は止まり、開始待ちに入った瞬間に追いつきます。

ボタンが変えるのは進行だけです。フレームに成功・失敗の列は書きません。押し間違いの「捨てる」は、その場では取り消せません。非常停止は手元の ESTOP のままです。この画面はトルクを切りません。

ポートを変えるときは `SO101_RECORD_BUTTONS_PORT`、待受アドレスは `SO101_RECORD_BUTTONS_HOST` です。ポートを取れないときは、キーボードのまま録画を続けます。

判断の記録: [D-20261018-06](reports/design_notes.md)、操作の分け方は [D-20261018-08](reports/design_notes.md)、残す→開始待ちは [D-20261023-01](reports/design_notes.md)。

1 本あたり最大 30 秒です。早く終わったら記録終了または `n` で切れます。

録画中の書き込み先（`HF_LEROBOT_HOME` 未設定時）:

```text
~/.cache/huggingface/lerobot/<repo_id>/
  meta/info.json
  data/
  videos/
```

`repo_id` の `/` はそのままディレクトリ区切りです。ログに出た **スタンプ付き repo_id** と、このディレクトリのパスをレポートに写します。

### 指定 PC へ移す

**PC 間のパス・rsync・早見表の正本は [23_data_transfer.md](23_data_transfer.md)**（Pi→GPU 自動／手動、GPU→Thor、チェックポイント）。

送り先は gitignore 済みの `configs/dataset.local.env` です（雛形は `configs/dataset.local.env.example`）。PC を替えるときはこの3行を書き換えます。`scripts/record_with_buttons.sh` が起動時に読みます。

```bash
# 例: Tailscale の GPU（詳細は docs/22）
SO101_DATASET_SSH=${SO101_GPU_SSH}
SO101_DATASET_DIR=$HOME/.cache/huggingface/lerobot
SO101_DATASET_DELETE_LOCAL=1
```

「残す」で保存したディレクトリを、次の記録開始の前と、セッションの最後に `SO101_DATASET_SSH:SO101_DATASET_DIR/<repo_id>/` へ送ります。録画の制御ループのあいだには送りません。最後の同期が成功したときだけ Pi のそのディレクトリを消します。転送に失敗した本は Pi に残ります。`SO101_DATASET_SSH` が空なら、従来どおり Pi だけです。

学習をその PC で始めるときは、コピー先を `--dataset.root` に渡します（**仮の `local/my_so101_task` は使わない**。[23](23_data_transfer.md)）。MLflow の `mlflow_store/` には動画を入れません。

判断の記録: [D-20261018-07](reports/design_notes.md)。転送のタイミングと、終了処理が2回走った件は [D-20261018-08](reports/design_notes.md) と [F-20261018-02](reports/design_notes.md)。

---

## 2. 閲覧・選別（4090 の WSL） {#dataset-review}

データセットの中身を見て、残す本を決める作業は **4090 の WSL** で行います。Pi 4 ではやりません。

| 理由 | 内容 |
|------|------|
| ファイルの場所 | 残した本はセッションの最後に WSL へ送られ、成功すると Pi 側は消える |
| 重さ | `delete_episodes` は残した本の動画を書き直す。数十本は Pi 4 には重い |
| ビューア | 映像をコマ送りする `rerun` は、Pi の venv にも WSL の学習 venv にも入れない。閲覧は `so101-lab` の `.venv`（[§2b](#dataset-viz)） |

マシンの対応は [17 — 役割](17_act_record_train_infer.md#roles) と同じです。

| 項目 | 値 |
|------|-----|
| 入り方 | Pi から `ssh ${SO101_GPU_SSH}`（Tailscale `gpu`） |
| 作業ディレクトリ | so101-lab から見て `../lerobot`（＝ `~/robot/lerobot`） |
| CLI（編集） | `.venv/bin/lerobot-edit-dataset`（`<user>` で実行。[§3](#dataset-edit)） |
| CLI（閲覧） | `so101-lab` の `.venv/bin/lerobot-dataset-viz`（ログインユーザーで実行。[§2b](#dataset-viz)） |
| この WSL の `so101-lab` | 編集 CLI は `~/robot/lerobot` を使う。閲覧は `so101-lab` の `.venv`（`uv sync`） |

リポジトリと venv は **<user> 所有**です（2026-10-19 に root から変換）。`<user>` ログインのまま `.venv/bin/…` を実行します。`sudo` は付けません（[17 — 学習する](17_act_record_train_infer.md#train) と同じ。付けると `HOME` が `/root` に変わります）。

`--root` と `--new_root` は `$HOME/.cache/...` で明示します（ユーザ名に依存する `/home/<user>/...` は書かない）。

データセットに成功・失敗の列はありません。スマホで「残す」とした本だけが入っています。ここでの選別は、映像を見て捨てる番号を決めることです。

### 2a. いまのコブラのデータ（2026-10-19）

| 項目 | 値 |
|------|-----|
| `repo_id` | `local/so101_singlearm_pickup_cobra_20261018_205119` |
| `root` | `$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119` |
| 本数 | **66**（episode index は 0 から 65）。フレーム **14298**。fps 30 |
| タスク文 | `Grab the cobra by the neck and put its whole body inside the clear plastic container.` |
| カメラ | `observation.images.front` と `observation.images.wrist` |

別の録画を選ぶときは、この 2 つの名前だけを、そのスタンプ付き `repo_id` と絶対パスに置き換えます。

WSL に入ってから:

```bash
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../lerobot

.venv/bin/lerobot-edit-dataset \
  --repo_id=local/so101_singlearm_pickup_cobra_20261018_205119 \
  --root=$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119 \
  --operation.type=info \
  --operation.show_features=true
```

`info` はファイルを変えません。レポートに写すものは次です。

- `total_episodes` / `total_frames`
- `fps` とカメラキー（`observation.images.front` と `observation.images.wrist`）
- タスク文が、学習・推論で使う文面と一致すること

### 2b. 1 本ずつ映像を見る {#dataset-viz}

`rerun` は WSL の学習 venv（root 所有）には入れません。閲覧用の `lerobot[dataset-viz]` は **`so101-lab` の通常依存**（`pyproject.toml` 記載）なので、ログインユーザーで `uv sync` を一度実行するだけです。

```bash
# so101-lab リポジトリ直下で実行
uv sync --all-groups    # docs・tracking グループも一緒に入る
```

ビューアの窓は、その PC の WSL 端末で開きます。Pi へ SSH した画面では開きません。番号は 0 から順に変えます。**sudo 不要**です（付けると `HOME` が `/root` に変わります）。

```bash
# so101-lab リポジトリ直下で実行
.venv/bin/lerobot-dataset-viz \
  --repo-id local/so101_singlearm_pickup_cobra_20261018_205119 \
  --root $HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119 \
  --episode-index 0
```

見る点は [17 — デモの仕分け](17_act_record_train_infer.md#demo-review) と同じです。タスクが最後までできている本を残します。途中で止まっている本、`front` と `wrist` の両方に対象が映っていない本は、次の削除リストに入れます。

Hub の [visualize_dataset スペース](https://huggingface.co/spaces/lerobot/visualize_dataset) は、push したデータ用です。このローカルデータには使いません。

---

## 3. 編集 {#dataset-edit}

失敗エピソードの削除とタスク文の修正だけを先に使います。実行場所は [§2](#dataset-review) と同じ WSL です。  
**元ディレクトリは残し、結果は別 repo_id に出します。** 上書きしたくなったときも、消す前のパスをレポートに書いてからにします。

### 3a. エピソードを除く

`episode_indices` は **捨てる番号** です。残す番号ではありません。下の `[0, 4, 12]` は書き方の例なので、見た結果に置き換えてから実行します。

```bash
.venv/bin/lerobot-edit-dataset \
  --repo_id=local/so101_singlearm_pickup_cobra_20261018_205119 \
  --root=$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119 \
  --new_repo_id=local/so101_singlearm_pickup_cobra_20261018_205119_kept \
  --new_root=$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119_kept \
  --operation.type=delete_episodes \
  --operation.episode_indices="[0, 4, 12]"
```

終わったら、新しいディレクトリに対してもう一度 `info` をかけます。本数は 66 から、捨てた個数を引いた数です。カメラキーとタスク文が残っていることも見ます。学習に渡すのは `_kept` の方です。

新しいディレクトリは `<user>` 所有で作られます（2026-10-19 より前の root 実行で作ったディレクトリだけ root 所有のままなので、必要に応じて `sudo chmod -R a+rX`）。

### 3b. タスク文を直す

学習・推論で使う文面と揃えます。元を残すため `new_repo_id` と `new_root` を付けます。コブラの文面を変えないときは、この節は飛ばします。

```bash
.venv/bin/lerobot-edit-dataset \
  --repo_id=local/so101_singlearm_pickup_cobra_20261018_205119 \
  --root=$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119 \
  --new_repo_id=local/so101_singlearm_pickup_cobra_20261018_205119_task \
  --new_root=$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119_task \
  --operation.type=modify_tasks \
  --operation.new_task="Grab the cobra by the neck and put its whole body inside the clear plastic container."
```

特定のエピソードだけ変えるとき:

```bash
.venv/bin/lerobot-edit-dataset \
  --repo_id=local/so101_singlearm_pickup_cobra_20261018_205119 \
  --root=$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119 \
  --new_repo_id=local/so101_singlearm_pickup_cobra_20261018_205119_task \
  --new_root=$HOME/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119_task \
  --operation.type=modify_tasks \
  --operation.episode_tasks='{"2": "Grab the cobra by the neck and put its whole body inside the clear plastic container."}'
```

分割・結合・特徴削除・動画の再エンコードは、必要になったセッションでだけ使います。一覧は [LeRobot dataset tools](https://huggingface.co/docs/lerobot/using_dataset_tools) です。結合のコマンド例は [17 — デモの仕分け](17_act_record_train_infer.md#demo-review) にあります。

---

## 4. 学習へ渡す（GPU ホスト）

Pi では `lerobot-train` を回しません。GPU ホストに次を揃えます。

1. 採用したデータセットディレクトリ（`meta/` `data/` `videos/` ごと）
2. その `repo_id` と `single_task`
3. `~/robot/lerobot` のコミット（この手順を書いた時点は `943fae88`）

ローカルディレクトリを直接読む例（ポリシーは Hub に上げない）:

```bash
# GPU ホスト。DATASET_ROOT はコピー先の絶対パス
# 曲線はローカル MLflow（docs/16）。UI は別端末で ./scripts/start_mlflow.sh
./scripts/train_mlflow.sh \
  --dataset.repo_id=<採用した repo_id> \
  --dataset.root=$DATASET_ROOT \
  --policy.type=act \
  --policy.device=cuda \
  --policy.push_to_hub=false \
  --output_dir=outputs/train/act_so101_single \
  --job_name=act_so101_single
```

Hub にポリシーを置く場合は `hf auth login` のあと、[14 Step 4a](14_single_arm_il.md) の `--policy.repo_id=${HF_USER}/act_so101_single` を使います。`--policy.push_to_hub` の既定は `true` で、そのときは `repo_id` が必要です。

推論は [17](17_act_record_train_infer.md)（Thor が計算、Pi が腕）。カメラキー・解像度・タスク文は、採用したデータセットと一致させます。5 本のスモークの次にデモを足して学習し直す手順もそこにあります。

---

## 5. 実施をレポートに残す

各セッションの終わりに [single_arm_il_work_report.md](reports/single_arm_il_work_report.md) へ **事実だけ** 1 行足します。版と改訂履歴も 1 行上げます。推測でエピソード数や成功率を書きません。

| 欄 | 書くもの |
|----|----------|
| いつ | 日付 |
| ホスト | Pi か GPU ホストか。git は `so101-lab` と `~/robot/lerobot` の短い SHA。未コミットならその旨 |
| 段階 | 作成 / 閲覧 / 編集 / 学習 / 推論 |
| 成果物 | データセットディレクトリ、`info` の episodes・frames、または `outputs/train/...` |
| タスク文 | そのデータに入っている文 |
| 捨てたもの | 削除した episode index と理由（短く） |
| 次 | 未了なら「学習は未実施」のように残す |

うまくいかなかった試行は [design_notes.md](reports/design_notes.md) の `F-` に残します。外部のツール名を増やすときは [references.md](reports/references.md) に url と license を足します。

---

## うまくいかないとき

| 症状 | 確認 |
|------|------|
| シリアルを開けない | LeLab / Web Remote が動いていないか |
| 指定 PC にデータが無い | `configs/dataset.local.env` の `SO101_DATASET_SSH`。Pi から `ssh -o BatchMode=yes <user@host>` が通るか。失敗時は Pi の `~/.cache/huggingface/lerobot/<repo_id>/` に残る |
| ブラウザの記録開始／記録終了が届かない | ターミナルに出た `http://<Pi>:8770/` を、同じ Wi-Fi のスマホで開いているか。Web Remote の 8765 ではない。URL は腕の接続のあとに出る。開始待ちになるまでは記録開始は出ない。エピソード数と記録時間は同じページの上段 |
| 一時停止しても腕が止まる | 一時停止は記録時間とフレームだけ止める。腕を止めるのは手元の ESTOP |
| カメラが暗い・fps が落ちる | `wrist` の by-path。帯域が足りなければ cameras の wrist に `fourcc: MJPG` を足す（yaml の `wrist_follower` と同じ） |
| 最後に Hub へ上げようとして失敗 | `--dataset.push_to_hub=false` を付けたか。途中までのローカルディレクトリが残っていれば `info` で本数を見る |
| 学習データが Hub から落ちてこない | `--dataset.root` にローカルのディレクトリを渡す |
| 推論の見え方が録画と違う | カメラキー・解像度・`single_task` |
