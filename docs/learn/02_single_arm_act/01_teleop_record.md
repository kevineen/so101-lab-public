# 第2章レッスン1 — テレオペとデモ録画

> 🎯 **ゴール**
> ①follower / leader の id を取り違えない
> ②カメラなしテレオペと、録画用カメラありを使い分けられる
> ③スモーク 5 ep を録れる

正本コマンド: [14 — Step 0〜3](../../14_single_arm_il.md)

---

## 2.1-1 キャリブ（写真を撮る前の「ゼロ点」）

| id | type | 用途 |
|----|------|------|
| `my_follower` | `so101_follower` | 駆動・録画・推論 |
| `my_leader` | `so101_leader` | **手**テレオペ |
| `my_leader_drive` | （使わない） | Web Remote 第2駆動用 |

初めてなら [14 Step 1](../../14_single_arm_il.md) の `lerobot-calibrate` を実行。

---

## 2.1-2 テレオペにカメラは要るか？

| 目的 | カメラ |
|------|--------|
| 追従の感触確認だけ | **不要** |
| ACT / VLA 用データ | **必要**（学習・推論と同じキー） |

確認だけ:

```bash
# 変数は 14 の「ラボ固定値」を export してから
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID \
  --teleop.type=so101_leader \
  --teleop.port=$LEADER_PORT \
  --teleop.id=$LEADER_ID
```

---

## 2.1-3 録画のコツ（初学者）

1. **タスク文を先に決める**（後で SmolVLA でも同じ文を使う）  
2. 録画前に leader と follower を同じ開始姿勢へ揃える（nest 可）。開始位置は leader の現在角  
3. 最初は **5 episodes**、録画 30 秒。早く終わったら `n`、または同じ Wi-Fi のブラウザで記録終了→残す／捨てる（残すとそのまま開始待ち。[15](../../15_dataset_pipeline.md#record-buttons)） 
4. 本番は目安 **40〜50 ep**（物体位置のバリエーションを繰り返す）  
5. LeLab と Web Remote は止める  

手順: [14 Step 3](../../14_single_arm_il.md) · 初期位置と秒数: [15 — 初期位置](../../15_dataset_pipeline.md#initial-pose) · ローカル録画・閲覧・編集: [15](../../15_dataset_pipeline.md) · 個人チェック: checklist Step 3

---

## 🧪 実習チェック

- [ ] `my_leader` が存在する（`my_leader_drive` ではない）
- [ ] カメラなしテレオペで follower が追従する
- [ ] （任意）カメラ付きで映像キー名をメモした
- [ ] スモーク録画 5 ep

---

## ✅ 理解度チェック

<details>
<summary>Q. 録画時のカメラキーを推論時に変えるとどうなる？</summary>

学習時と観測のチャネルがずれ、性能が落ちるか起動・前処理で失敗しやすい。キー名・解像度・fps を揃えるのが鉄則。
</details>

⏭️ [02_train_eval.md](02_train_eval.md)
