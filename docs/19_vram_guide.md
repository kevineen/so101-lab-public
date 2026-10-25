# 19 — VRAM 目安: Diffusion Policy / VLA の学習と推論（量子化・vLLM/SGLang 含む）

2026-10-19 時点の目安。学習は **4090 24GB の WSL**（`gpu`）、推論は **Jetson Thor**（`policy_server`、[17](17_act_record_train_infer.md) の構成）。数値の出どとは LeRobot 公式 [hardware guide](https://huggingface.co/docs/lerobot/en/hardware_guide) と [lerobot issue #2216](https://github.com/huggingface/lerobot/issues/2216) の実測、goal は「ACT の次にどのポリシーを 4090 で回せるか」の判断材料。lerobot は 0.6.2（fork、`../lerobot`）。

学習手順の詳細（データセットの指定・MLflow・出力先）は [17](17_act_record_train_infer.md) と同じ形なので、ここでは繰り返さない。

---

## 1. どのポリシーが 4090 で学習できるか {#summary}

学習時ピーク VRAM（BS 8・AdamW・画像 640×480 の目安。BS に対しほぼ線形）:

| グループ | fork 内ポリシー | 学習時ピーク | 4090 (24GB) | 推論時 (bf16) |
|----------|-----------------|-------------:|-------------|---------------|
| Light BC | `act` / `vqbet` / `tdmpc` | ~2–6GB | ◎ | 1–2GB |
| Diffusion | `diffusion` / `multi_task_dit` | ~8–14GB | ◎（BS 16 も可） | 2–3GB |
| Small VLA | `smolvla` | ~10–16GB | ○ BS 4–8 | 1–2GB |
| Large VLA | `pi0` / `pi0_fast` / `pi05` / `xvla` / `wall_x` | ~24–40GB | △ **LoRA のみ**（BS 1–2 で Tight） | 8–10GB |
| Multimodal | `groot` / `eo1` | ~24–40GB | ×（要 A100 40GB+） | 8–10GB |

4090 での wall-clock 目安（~50 エピソード / ~45k フレーム / 5 epoch、公式ガイドの表より）:

- `act` BS 8: 30–60 分
- `diffusion` BS 8: 2–4 時間
- `smolvla` BS 4: L4/A10G で 3–6 時間 → 4090 ならもう少し速い

pi0 系（~3.3B）の 4090 判定は issue #2216 の実測: **LoRA FT >22.5GB（4090 でギリ）、Full FT ~70GB（A100 80GB/H100）、推論 >8GB**。

---

## 2. 見積もり式 {#formula}

VRAM は次で概算できる（バッチサイズにほぼ線形、解像度・系列長にも依存）:

| 手法 | 式 |
|------|-----|
| 推論 (bf16) | params × 2 B + 活性化（BS 1 なら小） |
| LoRA FT | params × 2 B（凍結重み）+ 活性化（バッチ依存）+ アダプタ分（小） |
| Full FT + AdamW | params × 14–16 B（bf16 重み + fp32 master + 勾配 + AdamW モーメント 2 本）+ 活性化 |

例: pi0 系 3.3B →

- 推論: 3.3B × 2 B ≈ 6.6GB + ビジョンエンコーダ活性化 → **8–10GB**
- LoRA FT: 6.6GB + 活性化（BS 1–2 + grad ckpt）→ **22.5GB 超**
- Full FT: 3.3B × ~16 B ≈ 53GB + 活性化 → **~70GB**

Diffusion はパラメータ自体は数十 M（重み <1GB）だが、ノイズ除去 U-Net の**活性化が支配的**になり 8–14GB になる、という読み方。

---

## 3. 4090 で実際に回す {#commands}

作業ディレクトリ・venv の作法は [17](17_act_record_train_infer.md#demo-review) と同じ（`<user>` ログイン、絶対パス、`sudo` を付けない）。

### diffusion — そのまま BS 8

```bash
# so101-lab リポジトリ直下から（隣接 clone 前提）
cd ../lerobot
.venv/bin/lerobot-train \
  --dataset.repo_id=local/<データセット> \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/<データセット> \
  --policy.type=diffusion \
  --policy.device=cuda \
  --policy.push_to_hub=false \
  --batch_size=8 \
  --steps=<episodes×frames÷batch×epoch> \
  --output_dir=outputs/train/diffusion_<task>_<日付> \
  --job_name=diffusion_<task>_<日付>
```

### SmolVLA — 4090 で回せる VLA の本命

```bash
.venv/bin/lerobot-train \
  --dataset.repo_id=local/<データセット> \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/<データセット> \
  --policy.path=lerobot/smolvla_base \
  --policy.freeze_vision_encoder=true \
  --policy.push_to_hub=false \
  --batch_size=4 \
  ...
```

`freeze_vision_encoder=true` で VRAM を大きく削れる（公式ガイドの OOM 対策第一候補）。

### pi0 / pi05 — LoRA + 勾配チェックポイント + bf16 で Tight 運用

通し手順（データ → 3090/Thor 学習 → Thor 推論）は **[21_pi05_thor.md](21_pi05_thor.md)**。

```bash
.venv/bin/lerobot-train \
  --dataset.repo_id=local/<データセット> \
  --dataset.root=$HOME/.cache/huggingface/lerobot/local/<データセット> \
  --policy.type=pi05 \
  --policy.pretrained_path=lerobot/pi05_base \
  --policy.gradient_checkpointing=true \
  --policy.dtype=bfloat16 \
  --policy.push_to_hub=false \
  --peft.r=32 \
  --peft.lora_alpha=32 \
  --batch_size=1 \
  ...
```

- フラグは 0.6.2 の `--help` で確認済み: `--peft.method_type`（既定 `LORA`）、`--peft.r`、`--peft.lora_alpha`、`--peft.target_modules`、`--policy.gradient_checkpointing`、`--policy.dtype`
- 22.5GB 超えのギリギリ運用。**必ず短いスモーク（数百 step）で VRAM と `nvidia-smi` を確認してから**本番の step 数を決める
- 等価バッチを保つなら `--batch_size=1` + `--gradient_accumulation`（学習時間は伸びる）
- Full FT は 4090 では不可能。必要なら HF Jobs（`--job.target=a100-large`）かクラウド租借

### OOM したときの定石（効く順）

1. `--batch_size` を下げ、`--gradient_accumulation` で実効バッチを戻す（VRAM は BS にほぼ線形）
2. `freeze_vision_encoder=true`（smolvla）
3. `gradient_checkpointing=true`（pi0 系。時間 +2〜3 割で活性化を削減）
4. 画像の crop/resize を詰める
5. LR スケジュールの再計算（steps を変えたら `--policy.scheduler_decay_steps` も揃える）

---

## 4. 大きいモデルの量子化（QLoRA / 4bit）{#quantization}

**lerobot 0.6.2 は PEFT/LoRA までが標準。4bit/QLoRA のフラグは無い**（2026-10-19、`lerobot-train --help` 確認）。やりたければ bitsandbytes + PEFT（`prepare_model_for_kbit_training`）を pi0/pi05 に自前で組み込むことになる。

理論目安（**未検証の計算値**。式は [§2](#formula)）:

| 精度 | 重み (3.3B pi0 系) | FT 合計目安 | 推論合計目安 |
|------|-------------------|-------------|--------------|
| bf16 | 6.6GB | LoRA 22.5GB+ / Full ~70GB | 8–10GB |
| 8bit | ~3.3GB | （同上、自作） | 5–7GB |
| 4bit NF4 | ~2.5–3GB※ | **QLoRA 自作で 8–12GB**（BS 1–2 + grad ckpt） | 3–6GB |

※ Gemma 本体のみ 4bit（3.3B × 0.5 B ≈ 1.7GB + 量子化定数）+ 量子化しない vision encoder (SigLIP) と action expert の bf16 分 ~1GB。

運用方針:

- **量子化するなら学習の重み削減が主目的**（QLoRA で 4090 に余裕を持って載る）。推論は Thor 128GB unified memory なら bf16 のままで困らない
- 量子化対象は Gemma 本体のみ。vision encoder と action expert（flow matching）は bf16 のまま品質優先
- 連続アクションの精度劣化リスクは未知数。**まず bf16 LoRA + BS 1 が回るか試し、駄目なら QLoRA** の順が低リスク
- 4bit は学習・推論とも ~1.3–2× 遅くなる（重みの逐次逆量子化）
- Pi 4 は量子化しても対象外。大きい行列積が Illegal instruction で落ちる（[17](17_act_record_train_infer.md#roles)）。推論は Thor 一本で

---

## 5. π0.7（pi07）— 2026-10 発表、本体の重みは未公開 {#pi07}

[ブログ](https://www.pi.website/blog/pi07)（2026-10）と[論文](https://arxiv.org/abs/2604.15483)が出た段階で、**重みは未公開**（2026-10-19 確認: [openpi](https://github.com/Physical-Intelligence/openpi) は pi0 / pi0_fast / pi05 まで、HF の physical-intelligence org にも無し）。今日の時点で学習・推論の対象外。

論文からわかる構成（~5B）:

- Gemma3 系 **4B** VLM バックボーン（400M ビジョンエンコーダ込み）+ FAST トークン、knowledge insulation レシピ
- **860M** flow-matching action expert（50 step チャンク・5 denoise、50Hz で最大 240ms）
- カメラ 4 本 × 履歴 6 フレームの MEM 型履歴エンコーダ → pi05 より活性化メモリも増える
- サブゴール画像の steering を使う場合のみ、BAGEL 14B 初期化の world model が別プロセスで必要

重みが出たときの VRAM 試算（式は [§2](#formula)。**未検証**）:

| 手法 | VRAM 目安 | 4090 |
|------|-----------|------|
| 推論 bf16 | 10GB + 活性化 → **12–15GB** | ○（Thor も可） |
| LoRA FT | pi05 3.3B の >22.5GB 実測から比例 → **~28–35GB** | ×（A100 40GB 級） |
| QLoRA 4bit（自作） | 重み ~3GB + 活性化 → **~14–18GB** | △ 可能性 |

**いま実用的なのは「π0.7 レシピ」の移植**。π0.5 ベースに論文の要素（エピソードメタデータプロンプト・リアルタイムチャンキング・knowledge insulation の FAST 損失）を乗せた openpi fork が既にあり、**SO-101 左腕マルチタスク（11 タスク・551 エピソード）の FT 例**も HF に上がっている（[twanghcmut/openpi-pi07-so101-left-arm-multitask](https://huggingface.co/twanghcmut/openpi-pi07-so101-left-arm-multitask)、pi05_base から PyTorch bf16、2×H100 MIG で 30k step ≈ 14.7h）。ただし open-loop MAE は素の pi0.5 FT より悪く実機結果なし、という初期段階。

ウォッチ: [openpi](https://github.com/Physical-Intelligence/openpi) のモデル追加・[pi.website](https://www.pi.website)・HF org・lerobot 本家のポリシー追加。

---

## 6. 推論サーバー: vLLM / SGLang で動くか {#vllm-sglang}

結論: **2026-10 時点で vLLM / SGLang どちらも VLA は未対応**（機能要望の段階）。実道は lerobot 標準の `policy_server`（Thor で稼働中の [17](17_act_record_train_infer.md) の形。アクションチャンキング async 推論が実機ループと既に繋がっている）。

| ポリシー | vLLM | SGLang | 実道 |
|----------|------|--------|------|
| `diffusion` / `multi_task_dit` | × 対象外（U-Net/DiT。トークンストリームではない） | × | `policy_server` |
| `act` / `smolvla` | × 同上 | × | `policy_server` |
| `pi0` / `pi05` | × [FR #42100](https://github.com/vllm-project/vllm/issues/42100)（2026-05） | × [FR #18266](https://github.com/sgl-project/sglang/issues/18266)（2026-02） | `policy_server` (bf16) |
| `pi0_fast` | ×（アクションをトークン化する型だが未対応） | × 同上 | `policy_server` |
| `groot` / `eo1` | × | × | NVIDIA 系スタック（TensorRT） |

フォローすべき動き:

- vLLM: VLA を第一級モデルファミリにする FR [#42100](https://github.com/vllm-project/vllm/issues/42100)
- SGLang: [#16929](https://github.com/sgl-project/sglang/issues/16929)（VLA 全般）・[#18266](https://github.com/sgl-project/sglang/issues/18266)（π0/π0-FAST。バッチロールアウト目的）
- この手の専用ランタイムも出始めている（例: [Portable Inference Runtime of Embodied AI Models](https://arxiv.org/html/2607.02501v2)）

素の vLLM/SGLang が今も有効な場所: **VLA の前段**（指令解釈・計画の LLM/VLM。experiments の SayCan 系）と、将来 pi0 系が載ったときのバッチロールアウト（シミュレーション大量評価）。

---

## 7. 参照 {#refs}

- [LeRobot Compute HW Guide（公式・VRAM 表と学習時間）](https://huggingface.co/docs/lerobot/en/hardware_guide)
- [lerobot issue #2216 — pi05 FT の GPU メモリ実測](https://github.com/huggingface/lerobot/issues/2216)
- [π0.7 ブログ](https://www.pi.website/blog/pi07) · [π0.7 論文](https://arxiv.org/abs/2604.15483) · [openpi](https://github.com/Physical-Intelligence/openpi)
- [QLoRA: 4bit Transformers with bitsandbytes](https://github.com/huggingface/blog/blob/main/4bit-transformers-bitsandbytes.md)
- vLLM / SGLang の FR は [§6](#vllm-sglang) のリンク先
