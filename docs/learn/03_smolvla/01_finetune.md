# 第3章レッスン1 — SmolVLA ファインチューン

> 🎯 **ゴール**
> `--policy.path=lerobot/smolvla_base` で自データに合わせて学習し、実機で短い推論ができる

---

## 3.1-1 ACT とのコマンド差

| | ACT | SmolVLA |
|--|-----|---------|
| 指定 | `--policy.type=act` | `--policy.path=lerobot/smolvla_base` |
| 依存 | ベースに含まれる | `.[smolvla]` extra |
| データ | 同じ LeRobot データセットで可 | **タスク文付き**が重要 |

```bash
# 依存（初回、lerobot の venv）
cd ~/robot/lerobot
uv pip install --python .venv/bin/python -e ".[smolvla]"
# so101-lab リポジトリ直下で実行

./scripts/train_mlflow.sh \
  --policy.path=lerobot/smolvla_base \
  --dataset.repo_id=$REPO_ID \
  --batch_size=64 \
  --steps=20000 \
  --output_dir=outputs/train/smolvla_so101_single \
  --job_name=smolvla_so101_single \
  --policy.device=cuda \
  --policy.repo_id=${HF_USER}/smolvla_so101_single
```

UI は学習前に `./scripts/start_mlflow.sh`（[16](../../16_local_mlflow.md)）。

詳細・VRAM 調整: [14 Step 4b](../../14_single_arm_il.md)

公式の目安: バリエーションを繰り返した **〜50 ep** 程度から。少なすぎると弱い、とドキュメントにあります。

---

## 3.1-2 推論

録画時の **`single_task` と同じ文**を `--task` に渡す（[14 Step 5](../../14_single_arm_il.md)）。

---

## 🧪 実習チェック

- [ ] `.[smolvla]` が入っている
- [ ] FT が最後まで走った（または途中 ckpt でスモーク）
- [ ] 実機で `--task` 付き rollout を試した

---

## ✅ 理解度チェック

<details>
<summary>Q. なぜ「ベースを FT」するのか？ ACT のように type だけで始めないのか？</summary>

SmolVLA は大規模事前学習で視覚・言語・行動の結合を既に持っている。自ラボのデータでその結合を機体・カメラ・タスクに合わせるのが FT。ACT は軽量でデモから立ち上げる設計。
</details>

⏭️ [02_language_voice.md](02_language_voice.md)
