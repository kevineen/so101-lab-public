# 第4章 — その他の VLA（地図だけ先に）

> 🎯 **章のゴール**
> ①ACT / SmolVLA の次に何があるか一覧できる
> ②「今すぐ手を出さない理由」（GPU・データ・ライセンス）を言える
> ③ラボ既存の MolmoAct2 文書への入口を知っている
> ④（レッスン1）新しい VLA を自力で載せる手順を説明できる

この章は **読物＋ポインタ**です。第2・3章が通ってからで十分です。
実習（4.2b）と載せ方の一般手順（レッスン1）を除けば、座学のみで進められます。

## レッスン一覧

| # | レッスン | 内容 | 時間目安 |
|---|---------|------|----------|
| 1 | [01_onboarding_checklist.md](01_onboarding_checklist.md) | 新しい VLA を載せるチェックリスト | 30分（読物。載せるときに手元に置く） |

---

## 4.1 地図（2026-10 ラボ視点）

| モデル | 位置づけ | 論文 | ラボでの入口 |
|--------|----------|------|--------------|
| **ACT** | 軽量 IL。最初の通し | [R-PAPER-ACT](https://arxiv.org/abs/2304.13705) | 第2章 · [14](../../14_single_arm_il.md) |
| **SmolVLA** | 軽量 VLA。言語 FT | [R-PAPER-SMOLVLA](https://huggingface.co/papers/2506.01844) | 第3章 |
| **MolmoAct2** | AllenAI 系 VLA。片腕公開重みあり／双腕は自データ | [R-PAPER-MOLMOACT2](https://arxiv.org/abs/2605.02881) | [10_molmoact2_thor.md](../../10_molmoact2_thor.md) |
| **π0 / π0.5** | Physical Intelligence 系。要件が重いことが多い | [R-PAPER-PI0](https://arxiv.org/abs/2410.24164) | [21 pi05 + Thor](../../21_pi05_thor.md) · `~/robot/lerobot/docs/source/pi0.mdx` |
| **X-VLA** | soft prompt で機体差を吸収 | [R-PAPER-XVLA](https://arxiv.org/abs/2510.10274) | `~/robot/lerobot/docs/source/xvla.mdx` |
| **FRS** | π0/π0.5/SmolVLA を逆流積分でステアリング（モデル不改変・訓練不要） | [R-PAPER-FRS](https://arxiv.org/abs/2606.13675) | `~/robot/lerobot/docs/frs_so101.md`（`lerobot-frs-steering` / `lerobot-frs-dsbc-train`） |
| **Diffusion Policy** | 行動を拡散で生成する IL | [R-PAPER-DIFFPOLICY](https://arxiv.org/abs/2303.04137) | [14 Step 4c](../../14_single_arm_il.md)（同じデータで比較可） |
| **sim2rl EVA-ACT** | **シム**上の ACT 系（実機 LeRobot とは別実装） | [R-PAPER-EVA](https://arxiv.org/abs/2610.06545) | [sim2rl il_eva](../../../../sim2rl/docs/il_eva.md) · [09 Bi-ACT](../../../../sim2rl/docs/learn/09_advanced/05_paper_biact.md) |

ID とライセンス欄: [papers.md](../papers.md) · [references.md](../../reports/references.md)

> 💡 **先生の一言**: 「全部試す」より「ACT で計測可能な成功定義を作る → 同じタスクで SmolVLA と比較」が学習効率が良いです。

---

## 4.2 MolmoAct2（片腕スモーク）

- 公開 `lerobot/MolmoAct2-SO100_101-LeRobot` は **片腕・特定カメラキー**向け  
- 双腕 12 関節にはそのまま使わない  
- Pi 制御 / Thor 推論の分担は [10](../../10_molmoact2_thor.md)

第5章（双腕）に進む前の「VLA サーバを一度立てる」練習に使えます
（TODO T-P1-08 として milestone 化済み）。

## 4.2b 🧪 実習: 同じデータで ACT / SmolVLA / Diffusion を比較する

第2・3章で通したデータセットと 10 試行評価プロトコル（[17 §5](../../17_act_record_train_infer.md)）を
そのまま使い、**モデルだけ差し替える**実習です:

1. ACT の本番評価（第2章・[17](../../17_act_record_train_infer.md)）が 5/10 以上になったら着手
2. SmolVLA FT（第3章・[14 Step 4b](../../14_single_arm_il.md)）→ 同じプロトコルで 10 試行
3. Diffusion Policy（[14 Step 4c](../../14_single_arm_il.md)。`actions_per_chunk=32` に注意）→ 同じ 10 試行
4. [作業レポート](../../reports/single_arm_il_work_report.md)の比較表に 3 行並べる（同じ形式の S- セッション）

**見るポイント**: 成功率だけでなく、①学習時間 ②推論レート（チャンク長の違い）③
失敗の仕方（拡散は多様なデモに強いが外挿で振る舞いが変わる）を書き分ける。
シム側の比較（sim2rl EVA-ACT vs EVA-Diffusion、
[il_eva.md](../../../../sim2rl/docs/il_eva.md)）と見立てが一致するかも面白い問いです。

---

## 4.3 選ぶときの質問リスト

1. 言語指示は必須か？ → 必須なら VLA、否なら ACT でよい  
2. GPU メモリは足りるか？  
3. データセットのカメラキー・行動次元は重みと一致するか？  
4. ライセンス・商用制限は？ → [reports/references.md](../../reports/references.md) に書く  

---

## ✅ 理解度チェック

<details>
<summary>Q. sim2rl の EVA-ACT を学習すれば、そのまま LeRobot の ACT 実機推論に載るか？</summary>

通常は否。観測定義・正規化・チェックポイント形式が異なることが多い。アイデアの兄弟であり、重みの互換を仮定しない。実機は LeRobot 経路、シム比較は sim2rl 経路、と分ける。
</details>

⏭️ 次の章: [05_bimanual/](../05_bimanual/README.md)
