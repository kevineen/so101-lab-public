# 論文索引

カリキュラムで名前を出す論文のリンクです。提出・引用の ID 正本は [reports/references.md](../reports/references.md)。  
手順との対応は [第1章レッスン3 — 強化学習の学習手順](01_concepts/03_rl_procedure.md)。

---

## 強化学習

| ID | 論文 | 年 | リンク | このラボでの読みどころ |
|----|------|----|--------|------------------------|
| R-PAPER-PPO | Proximal Policy Optimization Algorithms（Schulman et al.） | 2017 | [arXiv:1707.06347](https://arxiv.org/abs/1707.06347) | sim2rl の既定アルゴリズム。reach の学習手順はこれを回す |
| R-PAPER-SAC | Soft Actor-Critic（Haarnoja et al.） | 2018 | [arXiv:1801.01290](https://arxiv.org/abs/1801.01290) | 単環境・サンプル効率。`algo=sac` の比較用 |
| R-PAPER-SGS | Success Guided Sampling | 2026 | [arXiv:2610.12465](https://arxiv.org/abs/2610.12465) | 成功しやすい初期状態を増やす。reach の基本手順のあと |

系譜（REINFORCE → PPO、SAC、GRPO）の長文は sim2rl [rl_methods.md](../../../sim2rl/docs/learn/rl_methods.md)。

---

## 模倣学習

| ID | 論文 | 年 | リンク | このラボでの読みどころ |
|----|------|----|--------|------------------------|
| R-PAPER-ACT | Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware（Zhao et al. / ACT, ALOHA） | 2023 | [arXiv:2304.13705](https://arxiv.org/abs/2304.13705) | 第2章。デモから行動チャンクを学ぶ |
| R-PAPER-BIACT | Bi-ACT（Buamanee et al.） | 2024 | [arXiv:2401.17698](https://arxiv.org/abs/2401.17698) | 力覚込みの ACT。実機の主経路は片腕 ACT のまま |
| R-PAPER-DIFFPOLICY | Diffusion Policy（Chi et al.） | 2023 | [arXiv:2303.04137](https://arxiv.org/abs/2303.04137) | 行動分布を拡散で表す IL。地図用 |
| R-PAPER-EVA | Empirical VAE (EVA) | 2026 | [arXiv:2610.06545](https://arxiv.org/abs/2610.06545) | sim2rl の EVA-ACT。LeRobot の重みとは別 |

公式ドキュメント: [LeRobot ACT](https://huggingface.co/docs/lerobot/act)（[R-DOC-LEROBOT-IL](../reports/references.md)）

---

## VLA（言語＋視覚→行動）

| ID | 論文 | 年 | リンク | このラボでの読みどころ |
|----|------|----|--------|------------------------|
| R-PAPER-SMOLVLA | SmolVLA（Shukor et al.） | 2025 | [HF papers](https://huggingface.co/papers/2506.01844) | 第3章。軽量 VLA の FT |
| R-PAPER-PI0 | π0: A Vision-Language-Action Flow Model for General Robot Control（Black et al.） | 2024 | [arXiv:2410.24164](https://arxiv.org/abs/2410.24164) | 第4章。要件が重い基盤モデル |
| R-PAPER-MOLMOACT2 | MolmoAct2: Action Reasoning Models for Real-world Deployment（Fang et al.） | 2026 | [arXiv:2605.02881](https://arxiv.org/abs/2605.02881) | 第4・5章。片腕スモークと双腕は [10](../10_molmoact2_thor.md) |
| R-PAPER-XVLA | X-VLA: Soft-Prompted Transformer as Scalable Cross-Embodiment VLA（Zheng et al.） | 2025 | [arXiv:2510.10274](https://arxiv.org/abs/2510.10274) | 第4章。embodiment を soft prompt で分ける |
| R-PAPER-SAYCAN | SayCan（Ahn et al.） | 2022 | [arXiv:2204.01691](https://arxiv.org/abs/2204.01691) | 言語をロボットのできることに接地する。trainswap 実験 |
| R-PAPER-FRS | Improving Robotic Generalist Policies via Flow Reversal Steering（Tang et al.） | 2026 | [arXiv:2606.13675](https://arxiv.org/abs/2606.13675) | フロー・マッチング VLA（π0/π0.5/SmolVLA）を逆流ステアリング。lerobot フォークに実装済み |

公式ドキュメント: [LeRobot SmolVLA](https://huggingface.co/docs/lerobot/smolvla)

---

## 物理シミュレータ

| ID | 論文 | 年 | リンク | このラボでの読みどころ |
|----|------|----|--------|------------------------|
| R-PAPER-KAMINO | On Solving the Dynamics of Constrained Rigid Multi-Body Systems with Kinematic Loops（Tsounis, Grandia, Bächer et al.） | 2025 | [arXiv:2504.19771](https://arxiv.org/abs/2504.19771) | Newton の Kamino ソルバの元論文（Proximal-ADMM）。運用正本は [22](../22_kamino_sim.md) |

実装: [newton-physics/newton](https://github.com/newton-physics/newton)（`pip install newton` に同梱・BETA）。
ラボでは GPU 動力学シミュ（[22](../22_kamino_sim.md)）として使用。運動学・干渉チェックは引き続き MuJoCo（[12](../12_mujoco_sim.md)）。

---

## 読み順の目安

```text
PPO（手順を回しながら） → ACT（実機 IL の第2章）
    → SmolVLA（第3章） → π0 / MolmoAct2 / X-VLA は地図として
```

判断の記録: [D-20261018-03](../reports/design_notes.md)。
