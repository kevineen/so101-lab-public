# 参考文献 · リンク · ライセンス

提出物・設計ノート・レポートで触れた **外部成果・資産・ツールは必ずここに登録**する。  
本文や `design_notes.md` からは **ID のみ**で参照する（リンク・ライセンス表記の抜けを防ぐ）。

| 項目 | 値 |
|------|-----|
| 版 | **v0.17** |
| 最終更新 | 2026-10-23 |
| 運用 | [AGENT.md](AGENT.md) §9 |

### 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v0.17 | 2026-10-23 | D-20261023-03 / F-20261023-01 を R-CODE-LEROBOT used_in に追加 |
| v0.16 | 2026-10-23 | R-DOC-SO101-MODEL-EVAL。D-20261023-02 を used_in に追加 |
| v0.15 | 2026-10-23 | D-20261023-01 を R-CODE-LEROBOT とデータセット手順の used_in に追加 |
| v0.14 | 2026-10-20 | R-PAPER-KAMINO と R-CODE-NEWTON を追加（GPU 動力学シミュ docs/22 にて使用） |
| v0.13 | 2026-10-18 | R-DOC-LEROBOT-SO101-HARDWARE を追加（学習第0章レッスン0から参照）。R-DOC-SO101-LEARN の used_in に `docs/learn/00_lab_map/00_setup_from_zero.md` を追加 |
| v0.12 | 2026-10-18 | R-DOC-SO101-ACT-RUNBOOK。D-20261018-10 と F-20261018-03 を既存 ID の used_in に追加 |
| v0.11 | 2026-10-18 | D-20261018-09 を R-CODE-LEROBOT とデータセット手順の used_in に追加 |
| v0.10 | 2026-10-18 | D-20261018-08 と F-20261018-02 を既存 ID の used_in に追加 |
| v0.9 | 2026-10-18 | D-20261018-07: データセット転送に rsync と OpenSSH を追加 |
| v0.8 | 2026-10-18 | D-20261018-06 を R-CODE-LEROBOT とデータセット手順の used_in に追加 |
| v0.7 | 2026-10-18 | R-TOOL-MLFLOW note: UI は Docker Compose 既定 |
| v0.6 | 2026-10-18 | ローカル MLflow（学習ログ）を追加 |
| v0.5 | 2026-10-18 | learn 論文索引用に SAC・π0・MolmoAct2・X-VLA を追加 |
| v0.4 | 2026-10-18 | データセットツールと片腕 IL 手順（docs/15）・作業レポートを追加 |
| v0.3 | 2026-10-17 | docs/learn カリキュラム ID を追加 |
| v0.2 | 2026-10-17 | 片腕 IL: LeRobot / SmolVLA / ラボ手順書を追加 |
| v0.1 | 2026-10-16 | 初版。sim2rl 作業レポート種まき分を登録 |

---

## 必須ルール（提出・Agent 共通）

1. **リンク必須** — 論文・リポジトリ・ドキュメント・データセット・モデル・資産は URL（または DOI / arXiv）を書く。ローカルパスだけの参照は不可（補足としてなら可）。
2. **ライセンス必須** — コード・メッシュ・データ・学習済み重みを使ったら `license` 欄を埋める。不明なら `unknown（要確認）` とし、提出前に解消する。
3. **新規利用のたび追記** — レポートや design_notes に新しい外部依存を書いたら、**同コミット／同ターンで**本ファイルに行を追加する。
4. **ID 採番** — `R-<種別>-<短い名>`。種別例: `PAPER` / `CODE` / `ASSET` / `LIC` / `DOC` / `ALG` / `DATA`。
5. **改変資産** — upstream の LICENSE + ローカル `NOTICE.md` の両方を書く（SO-101 など）。

---

## 登録テンプレ

```markdown
### R-PAPER-EXAMPLE

| 欄 | 内容 |
|----|------|
| type | paper / code / asset / license / doc / tool / data |
| title | |
| authors / org | |
| year | |
| url | https://... （必須） |
| license | SPDX 名または公式表記（必須。論文は "N/A (paper)" 可） |
| used_in | どの機能・節・design_notes ID か |
| note | 引用の仕方・改変の有無 |
```

---

## 自プロジェクト・ライセンス

### R-LIC-SIM2RL

| 欄 | 内容 |
|----|------|
| type | license |
| title | sim2RL |
| authors / org | sim2RL developers |
| year | 2026 |
| url | https://github.com/kevineen/sim2rl （ローカル: `~/robot/sim2rl`） |
| license | **MIT**（`LICENSE`）。第三者ロボット資産は `assets/robots/*/NOTICE.md` 個別 |
| used_in | 本レポート全体 |
| note | 提出時は本リポの LICENSE を添付またはリンク |

### R-ASSET-SO101

| 欄 | 内容 |
|----|------|
| type | asset |
| title | SO-ARM100 / SO-101 URDF & meshes |
| authors / org | TheRobotStudio |
| year | （upstream） |
| url | https://github.com/TheRobotStudio/SO-ARM100 |
| license | **Apache-2.0**（`assets/robots/so101/LICENSE.upstream` + [NOTICE.md](../../../sim2rl/assets/robots/so101/NOTICE.md)） |
| used_in | 全シミュレーション・実機モデル |
| note | ローカル改変はパス書き換えのみ（幾何・運動学変更なし）。upstream commit は NOTICE 参照 |

### R-ASSET-SO101-PARALLEL

| 欄 | 内容 |
|----|------|
| type | asset |
| title | so101_parallel（平行グリッパ） |
| authors / org | （sim2rl 同梱・NOTICE 参照） |
| year | 2026 |
| url | `~/robot/sim2rl/assets/robots/so101_parallel/NOTICE.md` |
| license | NOTICE 記載（CERN-OHL-P-2.0 / Apache-2.0 混在の可能性 → **提出前に NOTICE を再確認**） |
| used_in | grasp / agent_server |
| note | 提出物にメッシュを含める場合は NOTICE 全文を同梱 |

---

## 論文・手法

### R-PAPER-SGS

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Success Guided Sampling（Mega-Scale RL for Robot Control 関連） |
| authors / org | （論文著者。本文は arXiv 参照） |
| year | 2026 |
| url | https://arxiv.org/abs/2610.12465 |
| license | N/A (paper) |
| used_in | `train.sgs` · D-20261016-04 · `docs/sgs.md` · `docs/learn/papers.md` |
| note | CoRL 2026 表記は sim2rl docs に準拠 |

### R-PAPER-EVA

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Empirical VAE (EVA) |
| authors / org | （arXiv / 実装リポ参照） |
| year | 2026 |
| url | https://arxiv.org/abs/2610.06545 |
| license | N/A (paper) |
| used_in | EVA-ACT · D-20261016-03 · F-20261016-03 · `docs/learn/papers.md` |
| note | 実装参考: https://github.com/mapooon/EVA （利用時は当該リポの LICENSE を R-CODE-EVA として追加すること） |

### R-PAPER-ACT

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware (ACT / ALOHA) |
| authors / org | Zhao et al. |
| year | 2023 |
| url | https://arxiv.org/abs/2304.13705 |
| license | N/A (paper) |
| used_in | 行動チャンキング・IL 設計 · D-20261017-01 · D-20261018-03 · `docs/14_single_arm_il.md` · `docs/learn/papers.md` |
| note | |

### R-PAPER-SMOLVLA

| 欄 | 内容 |
|----|------|
| type | paper |
| title | SmolVLA: Efficient Vision-Language-Action Model for Robotics |
| authors / org | Hugging Face / Shukor et al. |
| year | 2025 |
| url | https://huggingface.co/papers/2506.01844 |
| license | N/A (paper) |
| used_in | D-20261017-01 · D-20261018-03 · `docs/14_single_arm_il.md` · `docs/learn/papers.md` |
| note | ベース重み: https://huggingface.co/lerobot/smolvla_base |

### R-CODE-LEROBOT

| 欄 | 内容 |
|----|------|
| type | code |
| title | Hugging Face LeRobot |
| authors / org | Hugging Face |
| year | 2024– |
| url | https://github.com/huggingface/lerobot |
| license | **Apache-2.0** |
| used_in | so101-lab `vendor/lerobot` · ACT / SmolVLA / record · D-20261017-01 · D-20261018-02 · D-20261018-06 · D-20261018-07 · D-20261018-08 · D-20261018-09 · D-20261018-10 · D-20261023-01 · D-20261023-02 · D-20261023-03 · F-20261018-02 · F-20261018-03 · F-20261023-01 |
| note | ラボは fork `kevineen/lerobot`。上流 LICENSE に従う |

### R-DOC-LEROBOT-IL

| 欄 | 内容 |
|----|------|
| type | doc |
| title | Imitation Learning on Real-World Robots（LeRobot） |
| authors / org | Hugging Face |
| year | 2025– |
| url | https://huggingface.co/docs/lerobot/il_robots |
| license | ドキュメント（コードは R-CODE-LEROBOT） |
| used_in | `docs/14_single_arm_il.md` · D-20261018-02 · `docs/15_dataset_pipeline.md` |
| note | ACT: https://huggingface.co/docs/lerobot/act · SmolVLA: https://huggingface.co/docs/lerobot/smolvla |

### R-DOC-LEROBOT-SO101-HARDWARE

| 欄 | 内容 |
|----|------|
| type | doc |
| title | SO-100 / SO-101 Hardware（LeRobot 公式: 部品・組立・配線） |
| authors / org | Hugging Face / TheRobotStudio |
| year | 2024– |
| url | https://huggingface.co/docs/lerobot/so101 |
| license | ドキュメント（ハード設計は R-ASSET-SO101 側に従う） |
| used_in | `docs/learn/00_lab_map/00_setup_from_zero.md` |
| note | 組立ガイド（TheRobotStudio 版 STL・手順）: https://github.com/TheRobotStudio/SO-ARM100 · ソース: https://huggingface.co/docs/lerobot/so101_so100_source |

### R-DOC-SO101-SINGLE-IL

| 欄 | 内容 |
|----|------|
| type | doc |
| title | so101-lab 片腕 IL 手順書 |
| authors / org | so101-lab |
| year | 2026 |
| url | https://github.com/kevineen/so101-lab/blob/main/docs/14_single_arm_il.md |
| license | so101-lab リポ LICENSE（不明なら unknown（要確認）） |
| used_in | D-20261017-01 · D-20261017-02 · D-20261018-01 · D-20261018-10 · T-P1-05 |
| note | ローカル正本: `docs/14_single_arm_il.md`。データセットの作成・閲覧・編集は R-DOC-SO101-DATASET-PIPELINE |

### R-DOC-LEROBOT-DATASET-TOOLS

| 欄 | 内容 |
|----|------|
| type | doc |
| title | Using Dataset Tools（LeRobot） |
| authors / org | Hugging Face |
| year | 2025– |
| url | https://huggingface.co/docs/lerobot/using_dataset_tools |
| license | ドキュメント（実装は R-CODE-LEROBOT、Apache-2.0） |
| used_in | D-20261018-01 · `docs/15_dataset_pipeline.md` |
| note | ストリーミングエンコード: https://huggingface.co/docs/lerobot/streaming_video_encoding · Hub 可視化: https://huggingface.co/spaces/lerobot/visualize_dataset |

### R-DOC-SO101-DATASET-PIPELINE

| 欄 | 内容 |
|----|------|
| type | doc |
| title | so101-lab データセット作成・閲覧・編集手順 |
| authors / org | so101-lab |
| year | 2026 |
| url | https://github.com/kevineen/so101-lab/blob/main/docs/15_dataset_pipeline.md |
| license | so101-lab リポ LICENSE（不明なら unknown（要確認）） |
| used_in | D-20261018-01 · D-20261018-02 · D-20261018-06 · D-20261018-07 · D-20261018-08 · D-20261018-09 · D-20261018-10 · D-20261023-01 · F-20261018-02 · F-20261018-03 · T-P1-05 · `docs/reports/single_arm_il_work_report.md` |
| note | ローカル正本: `docs/15_dataset_pipeline.md`。実施事実は `docs/reports/single_arm_il_work_report.md` |

### R-DOC-SO101-ACT-RUNBOOK

| 欄 | 内容 |
|----|------|
| type | doc |
| title | so101-lab 片腕 ACT（デモ追加・学習・Thor 推論） |
| authors / org | so101-lab |
| year | 2026 |
| url | https://github.com/kevineen/so101-lab/blob/main/docs/17_act_record_train_infer.md |
| license | so101-lab リポ LICENSE（不明なら unknown（要確認）） |
| used_in | D-20261018-10 · D-20261023-02 · F-20261018-03 · T-P1-05 |
| note | ローカル正本: `docs/17_act_record_train_infer.md`。録画の操作は R-DOC-SO101-DATASET-PIPELINE |

### R-DOC-SO101-MODEL-EVAL

| 欄 | 内容 |
|----|------|
| type | doc |
| title | so101-lab 学習済みモデル実機評価・選別（スマホ推論 UI 含む） |
| authors / org | so101-lab |
| year | 2026 |
| url | https://github.com/kevineen/so101-lab/blob/main/docs/24_model_eval_campaign.md |
| license | so101-lab リポ LICENSE（不明なら unknown（要確認）） |
| used_in | D-20261023-02 · T-P1-05 · `docs/reports/model_eval_results.md` |
| note | ローカル正本: `docs/24_model_eval_campaign.md`。推論スマホは `infer_buttons/`（`:8771`） |

### R-DOC-SO101-LEARN

| 欄 | 内容 |
|----|------|
| type | doc |
| title | so101-lab 初学者カリキュラム（実機 IL） |
| authors / org | so101-lab |
| year | 2026 |
| url | https://github.com/kevineen/so101-lab/blob/main/docs/learn/README.md |
| license | so101-lab リポ LICENSE（不明なら unknown（要確認）） |
| used_in | D-20261017-02 · D-20261018-03 · `docs/learn/00_lab_map/00_setup_from_zero.md` |
| note | ローカル: `docs/learn/`。運用コマンドは R-DOC-SO101-SINGLE-IL と R-DOC-SO101-ACT-RUNBOOK |

### R-DOC-SIM2RL-LEARN

| 欄 | 内容 |
|----|------|
| type | doc |
| title | sim2RL 学習カリキュラム |
| authors / org | sim2rl |
| year | 2026 |
| url | https://github.com/kevineen/sim2rl/blob/main/docs/learn/README.md |
| license | R-LIC-SIM2RL |
| used_in | D-20261017-02 · D-20261018-03 · so101-lab `docs/learn` 連携 |
| note | ローカル: `~/robot/sim2rl/docs/learn/` |

### R-PAPER-BIACT

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Bi-ACT: Bilateral Control-Based Imitation Learning via Action Chunking with Transformers |
| authors / org | Buamanee et al. |
| year | 2024 |
| url | https://arxiv.org/abs/2401.17698 |
| license | N/A (paper) |
| used_in | `algo=bi_act` · `docs/il_biact.md` · `docs/learn/papers.md` |
| note | プロジェクト: https://mertcookimg.github.io/bi-act/ |

### R-PAPER-DIFFPOLICY

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Diffusion Policy |
| authors / org | Chi et al. |
| year | 2023 |
| url | https://arxiv.org/abs/2303.04137 |
| license | N/A (paper) |
| used_in | EVA-Diffusion 比較の文脈 · F-20261016-03 · `docs/learn/papers.md` |
| note | |

### R-PAPER-PPO

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Proximal Policy Optimization Algorithms |
| authors / org | Schulman et al. |
| year | 2017 |
| url | https://arxiv.org/abs/1707.06347 |
| license | N/A (paper) |
| used_in | RL 学習 · F-20261016-01/02 · D-20261018-03 · `docs/learn/01_concepts/03_rl_procedure.md` |
| note | |

### R-PAPER-SAC

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning with a Stochastic Actor |
| authors / org | Haarnoja et al. |
| year | 2018 |
| url | https://arxiv.org/abs/1801.01290 |
| license | N/A (paper) |
| used_in | D-20261018-03 · `docs/learn/01_concepts/03_rl_procedure.md` · `docs/learn/papers.md` |
| note | sim2rl では `algo=sac` |

### R-PAPER-PI0

| 欄 | 内容 |
|----|------|
| type | paper |
| title | π0: A Vision-Language-Action Flow Model for General Robot Control |
| authors / org | Black et al. / Physical Intelligence |
| year | 2024 |
| url | https://arxiv.org/abs/2410.24164 |
| license | N/A (paper) |
| used_in | D-20261018-03 · `docs/learn/papers.md` · `docs/learn/04_other_vla/README.md` |
| note | ブログ: https://www.physicalintelligence.company/blog/pi0 · 実装: https://github.com/Physical-Intelligence/openpi |

### R-PAPER-MOLMOACT2

| 欄 | 内容 |
|----|------|
| type | paper |
| title | MolmoAct2: Action Reasoning Models for Real-world Deployment |
| authors / org | Fang et al. / Allen Institute for AI |
| year | 2026 |
| url | https://arxiv.org/abs/2605.02881 |
| license | N/A (paper) |
| used_in | D-20261018-03 · `docs/learn/papers.md` · `docs/10_molmoact2_thor.md` |
| note | コード: https://github.com/allenai/molmoact2 （モデルは Apache-2.0。論文は N/A） |

### R-PAPER-XVLA

| 欄 | 内容 |
|----|------|
| type | paper |
| title | X-VLA: Soft-Prompted Transformer as Scalable Cross-Embodiment Vision-Language-Action Model |
| authors / org | Zheng et al. |
| year | 2025 |
| url | https://arxiv.org/abs/2510.10274 |
| license | N/A (paper) |
| used_in | D-20261018-03 · `docs/learn/papers.md` · `docs/learn/04_other_vla/README.md` |
| note | LeRobot 側の解説: `vendor/lerobot/docs/source/xvla.mdx` |

### R-PAPER-SAYCAN

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Do As I Can, Not As I Say: Grounding Language in Robotic Affordances (SayCan) |
| authors / org | Ahn et al. |
| year | 2022 |
| url | https://arxiv.org/abs/2204.01691 |
| license | N/A (paper) |
| used_in | LLM agent / affordance rerank · so101-lab trainswap 実験 · `docs/learn/papers.md` |
| note | |

### R-PAPER-FRS

| 欄 | 内容 |
|----|------|
| type | paper |
| title | Improving Robotic Generalist Policies via Flow Reversal Steering |
| authors / org | Tang et al. / Stanford · UC Berkeley |
| year | 2026 |
| url | https://arxiv.org/abs/2606.13675 |
| license | N/A (paper) |
| used_in | `docs/learn/papers.md` · `docs/learn/04_other_vla/README.md` · vendor/lerobot FRS 実装 |
| note | 実装: lerobot フォークの `lerobot-frs-steering` / `lerobot-frs-dsbc-train`。解説: `vendor/lerobot/docs/frs_so101.md` |

### R-PAPER-KAMINO

| 欄 | 内容 |
|----|------|
| type | paper |
| title | On Solving the Dynamics of Constrained Rigid Multi-Body Systems with Kinematic Loops |
| authors / org | Tsounis, Grandia, Bächer et al. / Disney Research · NVIDIA · Google DeepMind |
| year | 2025 |
| url | https://arxiv.org/abs/2504.19771 |
| license | N/A (paper) |
| used_in | `docs/learn/papers.md` · `docs/22_kamino_sim.md` |
| note | Newton Kamino ソルバ（Proximal-ADMM）の元論文。実装は [R-CODE-NEWTON](#r-code-newton) |

---

## ライブラリ・ツール（利用時は版を protocol.json と揃える）

### R-ALG-SB3

| 欄 | 内容 |
|----|------|
| type | tool |
| title | Stable-Baselines3 |
| authors / org | Farama / SB3 authors |
| year | （使用版は lock / protocol） |
| url | https://github.com/DLR-RM/stable-baselines3 |
| license | **MIT** |
| used_in | PPO/A2C/SAC/TD3 |
| note | ベンチ `protocol.json` の版を提出時に転記 |

### R-ALG-MUJOCO

| 欄 | 内容 |
|----|------|
| type | tool |
| title | MuJoCo |
| authors / org | Google DeepMind |
| year | （使用版例: 3.14.0） |
| url | https://github.com/google-deepmind/mujoco |
| license | **Apache-2.0** |
| used_in | 精密評価・parity 基準 |
| note | |

### R-CODE-NEWTON

| 欄 | 内容 |
|----|------|
| type | tool |
| title | Newton（Kamino ソルバ同梱） |
| authors / org | NVIDIA · Disney Research · Google DeepMind |
| year | （使用版: 1.7.0 / warp-lang 1.18.0 — uv group `sim`） |
| url | https://github.com/newton-physics/newton |
| license | **Apache-2.0**（newton 本体。依存 warp-lang も Apache-2.0） |
| used_in | GPU 動力学シミュ `scripts/kamino_check.py` · `docs/22_kamino_sim.md` |
| note | Kamino は BETA 1（API 変更可能性）。旧 PyPI 名 `newton-physics` はスタブなので `newton` を使う。MJCF は assets の so101_scene.xml を共用 |

### R-ALG-GENESIS

| 欄 | 内容 |
|----|------|
| type | tool |
| title | Genesis |
| authors / org | Genesis authors |
| year | （使用版例: 1.4.2） |
| url | https://github.com/Genesis-Embodied-AI/Genesis |
| license | **Apache-2.0**（upstream 再確認） |
| used_in | 並列学習 · SGS 実験 |
| note | 提出物にエンジンを同梱しない場合も「利用ツール」として記載 |

### R-ALG-TORCH

| 欄 | 内容 |
|----|------|
| type | tool |
| title | PyTorch |
| authors / org | Meta / PyTorch Foundation |
| year | （例: 2.14） |
| url | https://pytorch.org/ |
| license | **BSD-style**（PyTorch LICENSE） |
| used_in | 学習・IL · F-20261018-03 · D-20261018-10 |
| note | Pi 4 の `2.11.0+cu128` は NVPL BLAS で、Cortex-A72 の ACT 順伝播が Illegal instruction になる |

### R-TOOL-MLFLOW

| 欄 | 内容 |
|----|------|
| type | tool |
| title | MLflow Tracking |
| authors / org | LF Projects / MLflow |
| year | 2018– |
| url | https://github.com/mlflow/mlflow |
| license | **Apache-2.0** |
| used_in | D-20261018-04 · D-20261018-05 · `docs/16_local_mlflow.md` · `tracking/` · 片腕 IL の学習ログ |
| note | ローカル sqlite（`mlflow_store/`、gitignore）。UI は Docker Compose（`ghcr.io/mlflow/mlflow:v2.22.1`）または `SO101_MLFLOW_BACKEND=uv`。ドキュメント: https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server |

### R-DOC-SO101-MLFLOW

| 欄 | 内容 |
|----|------|
| type | doc |
| title | so101-lab ローカル MLflow 手順 |
| authors / org | so101-lab |
| year | 2026 |
| url | https://github.com/kevineen/so101-lab/blob/main/docs/16_local_mlflow.md |
| license | so101-lab リポ LICENSE（不明なら unknown（要確認）） |
| used_in | D-20261018-04 · `docs/14_single_arm_il.md` Step 4 |
| note | ローカル正本: `docs/16_local_mlflow.md` |

### R-TOOL-RSYNC

| 欄 | 内容 |
|----|------|
| type | tool |
| title | rsync |
| authors / org | Andrew Tridgell / Wayne Davison and others |
| year | 1996– |
| url | https://github.com/RsyncProject/rsync |
| license | **GPL-3.0-or-later** |
| used_in | D-20261018-07 · D-20261018-08 · F-20261018-02 · `record_buttons/offload.py` |
| note | ドキュメント: https://download.samba.org/pub/rsync/rsync.1 |

### R-TOOL-OPENSSH

| 欄 | 内容 |
|----|------|
| type | tool |
| title | OpenSSH |
| authors / org | The OpenSSH Project |
| year | 1999– |
| url | https://www.openssh.com/ |
| license | **BSD-2-Clause**（OpenSSH の LICENSE は BSD 系。提出前に同梱 LICENSE を再確認） |
| used_in | D-20261018-07 · D-20261018-08 · `record_buttons/offload.py` |
| note | `ssh -o BatchMode=yes` で rsync の転送路にする。鍵が無いときは Pi に残す |

### R-LIC-ISAAC

| 欄 | 内容 |
|----|------|
| type | license |
| title | Isaac Sim / PhysX 利用 |
| authors / org | NVIDIA |
| year | （使用時） |
| url | https://developer.nvidia.com/isaac/sim |
| license | **NVIDIA EULA**（`OMNI_KIT_ACCEPT_EULA`）。再配布不可条件に注意 |
| used_in | `sim=physx` · F-20261016-04 |
| note | 提出物に Isaac バイナリを含めない。結果の数値引用のみなら EULA 範囲を確認 |

---

## プロジェクト内ドキュメント（リンク切れ防止用）

### R-DOC-PARITY

| 欄 | 内容 |
|----|------|
| type | doc |
| title | パリティ比較ガイド |
| url | `~/robot/sim2rl/docs/parity.md`（リポ相対: `docs/parity.md`） |
| license | R-LIC-SIM2RL に従う |
| used_in | D-20261016-01 · F-20261016-04 |
| note | |

### R-DOC-BENCH

| 欄 | 内容 |
|----|------|
| type | doc |
| title | ベンチマークとスコア比較 |
| url | `~/robot/sim2rl/docs/benchmarks.md` |
| license | R-LIC-SIM2RL |
| used_in | D-20261016-02 · F-20261016-01 |
| note | |

### R-DOC-REPRO

| 欄 | 内容 |
|----|------|
| type | doc |
| title | 再現性ガイド |
| url | `~/robot/sim2rl/docs/reproducibility.md` |
| license | R-LIC-SIM2RL |
| used_in | D-20261016-02 |
| note | |

### R-DOC-MAKEUP

| 欄 | 内容 |
|----|------|
| type | doc |
| title | メイクロードマップ |
| url | `~/robot/sim2rl/docs/makeup_roadmap.md` |
| license | R-LIC-SIM2RL |
| used_in | D-20261016-03 · F-20261016-02 |
| note | |

### R-DOC-IL-EVA

| 欄 | 内容 |
|----|------|
| type | doc |
| title | EVA-ACT / EVA-Diffusion 解説と実測 |
| url | `~/robot/sim2rl/docs/il_eva.md` |
| license | R-LIC-SIM2RL |
| used_in | D-20261016-03 · F-20261016-02/03 |
| note | |

### R-DOC-SGS

| 欄 | 内容 |
|----|------|
| type | doc |
| title | SGS 解説と検証実験 |
| url | `~/robot/sim2rl/docs/sgs.md` |
| license | R-LIC-SIM2RL |
| used_in | D-20261016-04 |
| note | |

---

## チェックリスト（提出前）

- [ ] レポート・スライド・design_notes に出る外部名は、すべて本ファイルに ID がある
- [ ] 各 ID に **url** と **license** がある（`unknown` が残っていない）
- [ ] 改変資産は NOTICE / upstream LICENSE を提出物に含めるかリンクしている
- [ ] NVIDIA / 商用 SDK は再配布しない旨を note に書いた
- [ ] 版・ライブラリ版は `protocol.json` / `metadata.json` と矛盾しない
