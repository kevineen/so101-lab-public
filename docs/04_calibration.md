# 04 — キャリブレーションと 1臂／2臂切替

## 結論（よくある質問）

**1臂↔2臂の切替や再起動のたびにキャリブし直す必要はありません。**

キャリブ結果はディスクに保存されます。同じ `--robot.id` で起動すれば、その JSON を読み込むだけです。

保存場所の例:

```
~/.cache/huggingface/lerobot/calibration/robots/so_follower/my_follower.json
~/.cache/huggingface/lerobot/calibration/robots/so_follower/my_leader_drive.json
```

| 操作 | 再キャリブ |
|------|------------|
| 1臂 ↔ 2臂（`enabled` / `--no-leader`） | 不要 |
| Web Remote / LeLab の再起動 | 不要 |
| UI で follower / leader タブ切替 | 不要 |
| **初回**、またはモータ／組み立て変更後 | **必要** |
| `--robot.id` を変えた | その id は新規なので必要 |

## Web Remote 用キャリブ（初回）

Web Remote は両ポートを **so101_follower** として駆動します。  
（LeLab の「物理 leader テレオペ」用キャリブ `so101_leader` / `my_leader` とは別物です。）

```bash
# follower
lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=${SO101_FOLLOWER_PORT} \
  --robot.id=my_follower

# leader ポートをブラウザから動かす用
lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=${SO101_LEADER_PORT} \
  --robot.id=my_leader_drive
```

## ブラウザから特定モータ（例: グリッパー）だけ直す

初回キャリブ済みなら、Web Remote 画面下部の **Calibration** パネルで再調整できます。

1. アームタブで対象を選ぶ  
2. モータにチェック（グリッパーなら `gripper`）  
3. **キャリブ開始** → 手で端まで動かす（難しければ **ブラウザ駆動 ON** で ± ジョグ）→ **現在を min / max**（または範囲記録）  
4. **保存して終了**

詳細手順は [03_web_remote.md](03_web_remote.md) の「ブラウザでグリッパー min/max を直す」。

## 1臂に戻す（Web Remote）

どれか一つで十分です（再キャリブ不要）:

1. yaml: `leader_arm.enabled: false`（**2026-10 時点のラボ既定**）
2. 起動: `./scripts/start_web_remote.sh --no-leader`

片腕で ACT / SmolVLA を回す手順: [14_single_arm_il.md](14_single_arm_il.md)。

## 2臂に戻す（Web Remote・第2駆動腕）

物理 leader のまま駆動するのはトルク不足になりやすいです。換装後に:

1. yaml: `leader_arm.enabled: true` と `drive_profile: full`（[13](13_drive_profiles.md)）
2. `my_leader_drive` のキャリブ JSON が既にあればそのまま起動

## 片腕 IL 用テレオペキャリブ（LeLab / lerobot-record）

デモ収集では leader を **手で動かす**ので、Web Remote 用の `my_leader_drive` とは別に:

```bash
lerobot-calibrate \
  --teleop.type=so101_leader \
  --teleop.port=${SO101_LEADER_PORT} \
  --teleop.id=my_leader
```

が必要です（無ければ Step として [14](14_single_arm_il.md) を参照）。

## 第2腕を 12V follower に換装したとき

モータ／電源が変わったら **再キャリブが必要**です。終わったら yaml の `leader_arm.drive_profile` を `full`（または `follower_12v`）へ。  
手順の全体は [13_drive_profiles.md](13_drive_profiles.md)。

## LeLab 用キャリブとの関係

| 用途 | type | 典型的な id |
|------|------|-------------|
| LeLab / `lerobot-record` leader テレオペ（手で動かす側） | `so101_leader` | `my_leader` |
| LeLab / Web Remote / IL の follower | `so101_follower` | `my_follower` |
| Web Remote で旧 leader ポートを駆動（片腕 IL では使わない） | `so101_follower` | `my_leader_drive` |

物理 leader として LeLab で使う場合と、Web Remote で「第 2 の駆動腕」として使う場合で、**キャリブファイル（id）が分かれます**。混同しないようにしてください。
