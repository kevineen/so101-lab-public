# 第1章 — 概念: IL・ACT・VLA

> 🎯 **章のゴール**
> ①強化学習（RL）と模倣学習（IL）の違いを説明できる
> ②ACT が「何を入力し何を出すか」を図で描ける
> ③言語・音声指示にはなぜ VLA（SmolVLA 等）が要るか言える
> ④シムの reach を PPO で回す順番を説明できる

## レッスン一覧

| # | レッスン | 内容 | 時間目安 |
|---|---------|------|----------|
| 1 | [01_il_vs_rl.md](01_il_vs_rl.md) | IL vs RL、デモの意味 | 20分 |
| 2 | [02_act_vs_vla.md](02_act_vs_vla.md) | ACT vs SmolVLA、音声の位置 | 25分 |
| 3 | [03_rl_procedure.md](03_rl_procedure.md) | シム reach の PPO 手順（CPU） | 30〜90分 |

**進め方**: レッスン1・2を読んでから第2章の実機実習へ。レッスン3はシムで RL を一周するとき（実機トルクは使わない）。論文リンクは [papers.md](../papers.md)。

### 深掘り

| トピック | 場所 |
|----------|------|
| MDP・報酬・PPO の詳説 | [02_rl](../../../../sim2rl/docs/learn/02_rl/README.md) |
| reach を回す短い手順 | [03_rl_procedure.md](03_rl_procedure.md) |
| 論文リンク | [papers.md](../papers.md) |
| 手法系譜（ACT / Diffusion 含む） | [rl_methods.md](../../../../sim2rl/docs/learn/rl_methods.md) |
| 観測→ネットワーク→行動 | [03_pytorch](../../../../sim2rl/docs/learn/03_pytorch/README.md) |

⏭️ [01_il_vs_rl.md](01_il_vs_rl.md)
