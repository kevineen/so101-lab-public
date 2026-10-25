# 第2章レッスン2 — ACT 学習と実機推論

> 🎯 **ゴール**
> ①`--policy.type=act` が「デモからほぼ新規学習」だと説明できる
> ②GPU で train → Thor で計算 → Pi は腕とカメラ、の分担を実行できる
> ③失敗時に「データ / カメラ / キャリブ」のどれを疑うか言える

正本: [17 — 録画・学習・Thor 推論](../../17_act_record_train_infer.md) · 概念の手順: [14 — Step 4a / 5](../../14_single_arm_il.md) · データセット: [15 §4](../../15_dataset_pipeline.md)

---

## 2.2-1 学習（GPU）

```bash
# 別端末: ./scripts/start_mlflow.sh  →  http://127.0.0.1:5000
./scripts/train_mlflow.sh \
  --dataset.repo_id=$REPO_ID \
  --policy.type=act \
  --output_dir=outputs/train/act_so101_single \
  --job_name=act_so101_single \
  --policy.device=cuda \
  --policy.repo_id=${HF_USER}/act_so101_single
```

曲線の見方: [16 — ローカル MLflow](../../16_local_mlflow.md)。

思い出しておくこと（第1章）:

- ポリシー本体は **あなたのデモから**学習（[ACT 論文](https://arxiv.org/abs/2304.13705)、R-PAPER-ACT）
- ResNet-18 は既定で **ImageNet 初期化**（完全ランダムではない）
- 報酬で学ぶ PPO の手順は別レッスン（[03_rl_procedure.md](../01_concepts/03_rl_procedure.md)）

Colab でも可（公式 ACT notebook）。Pi では回さない。

---

## 2.2-2 推論（実機・follower のみ）

- LeLab / Web Remote 停止
- 録画時と **同じカメラ設定**
- 計算は Thor、腕とカメラは Pi（[17](../../17_act_record_train_infer.md)）
- この Pi 4 で `lerobot-rollout` すると、ACT の行列積で落ちる

成功率が低くても、**クラッシュせず腕が意図した方向に動く**ところまでが第2章の完了目安です。  
5 本のスモークではポッドまで届かなくてよい。精度は 40〜50 本に足してから学習をやり直して上げます。

---

## 2.2-3 よくある切り分け

| 症状 | 先に疑うもの |
|------|----------------|
| 学習 loss が下がらない | データ破損・エピソード数不足・画像が真っ暗 |
| 推論で変な方向へ | `robot.id` / キャリブ取り違え、カメラキー不一致、デモが 5 本のまま |
| Pi で Illegal instruction | Pi 上で ACT を計算している。Thor のサーバを使う |
| Thor が `not callable` | `scripts/patch_draccus_py314.py` のあとサーバを上げ直す |
| Overload（leader） | 駆動腕として使っていないか。本経路では手テレオペのみ |

---

## 🧪 実習チェック

- [ ] ACT チェックポイントまたは Hub `policy.repo_id` がある
- [ ] Thor の `policy_server` と Pi の `robot_client` を短時間実行した（[17](../../17_act_record_train_infer.md)）
- [ ] 成功 ep / 試行 ep を checklist にメモした

---

## ✅ 理解度チェック

<details>
<summary>Q. ACT 推論で `--task` 文は必須か？</summary>

公式でも ACT ではスキップ可能なことが多い（言語を使わないため）。SmolVLA では録画時と同じタスク文が重要。
</details>

⏭️ 次の章: [03_smolvla/](../03_smolvla/README.md)
