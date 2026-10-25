# sim2RL 作業レポート

| 項目 | 値 |
|------|-----|
| 版 | **v0.2** |
| 最終更新 | 2026-10-18 |
| 対象リポ | `~/robot/sim2rl` @ `90a2831`（master） |
| 期間 | 2026-09-26 〜 2026-10-12（コミット約 38 件） |
| 提出用途 | 進捗・成果の提出用正本（スライド・数値の索引） |
| 関連 | [presentation.md](../../../sim2rl/docs/presentation.md) · [slides/sim2rl_overview.md](../../../sim2rl/slides/sim2rl_overview.md) · [更新管理](README.md) · [工夫/失敗](design_notes.md) · [参考文献・ライセンス](references.md) |

### 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v0.2 | 2026-10-18 | §7: 片腕 ACT は 5 本スモークの学習と Thor 推論まで。主結果の数値は変更なし |
| v0.1 | 2026-10-18 | §7 に片腕 IL 作業レポートへのリンクを追加。数値は変更なし（主結果の版上げ v0.2 は T-P0-01） |
| v0.1 | 2026-10-16 | 初版。リポ履歴・ベンチ・文書化済み実測を作業レポートとして集約。design_notes / references へリンク |

---

## 1. 要旨

**sim2RL** は、SO-101（SO-ARM100）向けに **学習・精密評価・System ID・システム統合をシミュレータ適材適所で分担**し、共通 URDF / StateDict / 正規化行動で一貫性を保証するマルチシミュレータ強化学習パイプラインである。

本期間で、(1) 7 バックエンドの統合とパリティ計測、(2) 再現可能なベンチマーク基盤、(3) 模倣学習（EVA-ACT / Bi-ACT）と適応カリキュラム（SGS）、(4) 学習・発表用ドキュメントとスライド生成までを実装・実行した。提出時は本レポート＋ `benchmarks/` の表＋ `slides/sim2rl_overview.md` から生成する PPTX/PDF を一式とする。

---

## 2. 目的と課題

| 課題 | 本プロジェクトの方針 |
|------|----------------------|
| Sim2Real ギャップ | System ID（Newton）→ 学習（Genesis / mjwarp）→ 精密評価（MuJoCo）→ 統合（Gazebo/ROS 2） |
| シミュレータ選定のジレンマ | 1 エンジンに全役割を載せない。EE パリティをテストで保証 |
| 再現性 | run ごとに `config.yaml` / `metadata.json`（git SHA・seed・ライブラリ版）を保存 |
| 応用目標（中長期） | マネキンへのメイク施術を Stage ゲートで段階分解（`makeup_roadmap.md`） |

---

## 3. 実施内容（作業履歴の要約）

時系列は `sim2rl` の git log に準拠。詳細はコミットメッセージを正とする。

### 3.1 基盤（2026-09-26〜09-27）

- コア構造: Registry + 共通 StateDict、MuJoCo / Genesis / Newton / ROS 2–Gazebo
- Quest 3 / Isaac Teleop アダプタ（IK テレオペ）
- CI（Python 3.12/3.13）、MkDocs 学習サイト、日本語 docstring

### 3.2 シミュレータ拡張・再現性（09-30〜10-07）

- MuJoCo Warp（GPU 並列）、PhysX（Isaac Sim）、Newton Featherstone
- **パリティ CLI**（同一プロトコルで EE 軌道差を定量化）
- タッチセンサ、`task=trace`（メイク Stage-1）、メイクロードマップ／マニュアル

### 3.3 エージェント・テレオペ・データフロー（10-02〜10-05）

- LLM エージェントサーバ、SayCan 風アフォーダンス再ランキング
- dora データフロー（sim / agent / demo / teleop）
- Bluetooth ゲームパッド、`so101_parallel`（平行グリッパ）
- Marp スライド生成（`slides/report_md.py`）

### 3.4 IL / カリキュラム / クラウド（10-07〜10-12）

- EVA-ACT / EVA-Diffusion（模倣学習）と実測表
- Bi-ACT（`algo=bi_act`）
- Success Guided Sampling（SGS）と Genesis 上の検証実験
- Colab / レンタル GPU 学習フロー、教師 AI（MkDocs + BM25）
- ローカル MuJoCo reach ベンチマークスナップショットのコミット

---

## 4. 主な成果物

| 区分 | 場所 | 提出での使い方 |
|------|------|----------------|
| ソース・設定 | `sim2rl/src/` · `configs/` | 再現・拡張の根拠 |
| クロスシムパリティ | `benchmarks/20261007-064833_full5/` | 「エンジン間差」の定量表 |
| RL ベンチ（短時間） | `benchmarks/20261012-100431_bench/` | プロトコル付き比較表（20k steps） |
| 学習カリキュラム | `docs/learn/`（全 11 章） | 教育・オンボーディング |
| IL 実測 | `docs/il_eva.md` | Stage-1 / BC の数値引用 |
| SGS 実測 | `docs/sgs.md` §8 | adaptive reset の傾向検証 |
| 発表デッキ正本 | `slides/sim2rl_overview.md` | `make slides` → PPTX/PDF |
| 提出ガイド | `docs/presentation.md` | run zip の中身の説明 |

---

## 5. 実験結果（実行済み・文書化済み）

### 5.1 クロスシムパリティ（2026-10-06、`full5`）

- **環境**: RTX 系 GPU、libs: torch 2.14 / mujoco 3.14 / genesis 1.4.2 / newton 1.6.1 / isaacsim 6.0.1
- **プロトコル**: home settle → シード済みアクションリプレイ 300 steps @ 0.02 s、基準 = MuJoCo
- **git**: `2da3603`（dirty）

| sim | EE mean [m] | EE max [m] | qpos RMSE [rad] | settle EE [m] |
|-----|-------------|------------|-----------------|---------------|
| mujoco | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| mjwarp | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| genesis | 0.0049 | 0.0130 | 0.0018 | 0.0000 |
| newton | 0.0068 | 0.0439 | 0.0064 | 0.0000 |
| physx | 0.0251 | 0.1303 | 0.0365 | 0.0044 |

**読み取り**: Genesis は平均 EE 差 ≈ 5 mm（設計目標の「cm オーダー一致」内）。PhysX は動力学差が大きく、学習シムとしては別扱いが妥当。一次情報: `sim2rl/benchmarks/20261007-064833_full5/parity.md`。

### 5.2 MuJoCo reach ベンチ（2026-10-12、`bench`、短時間スモーク）

- **条件**: PPO/A2C × seed 1–3、**20 000 steps**、評価は常に MuJoCo 10 ep、RTX 3090（WSL2）
- **git**: `6646b9f`（dirty）
- **結果要約**: 成功率は概ね 0%（A2C seed3 のみ 10%）。`mean_best_dist` ≈ 0.07–0.10 m で random と同程度。

**読み取り**: プロトコルとハーネスの通電確認としては有効だが、**学習未収束のスモーク**であり、成果主張の主数値には使わない。長時間 run（例: SGS 検証の 400k–600k）の表を主結果とする。一次情報: `sim2rl/benchmarks/20261012-100431_bench/benchmark.md`。

### 5.3 模倣学習 EVA-ACT（2026-10-07、trace line、IK デモ 60 ep）

出典: `sim2rl/docs/il_eva.md`

| ポリシー | success | RMS 横偏差 | on-path RMS | coverage |
|----------|---------|------------|-------------|----------|
| PPO 100k | 50% | 33.4 mm | — | 0.05 |
| IK エキスパート | 100% | 15.7 mm | **1.71 mm** | 0.89 |
| **EVA-ACT（BC）** | **100%** | **15.8 mm** | **1.53 mm** | **0.89** |
| EVA-ACT `gauss_cvae` | 100% | 15.8 mm | 1.50 mm | 0.90 |
| EVA-Diffusion | 80% | 18.1 mm | 3.3 mm | 0.73 |

- Stage-1 ゲート（on-path RMS &lt; 2 mm）を **BC で通過**（PPO 単体では不足）。
- 推論レイテンシ（RTX 4090）: EVA-ACT ≈ 540 ms/chunk、EVA-Diffusion ≈ 210 ms/chunk（`replan_every` で制御周期は維持可能）。

### 5.4 Success Guided Sampling（2026-10-12、Genesis）

出典: `sim2rl/docs/sgs.md` §8。評価条件は SGS の有無で同一（MuJoCo・決定的・10 ep）。

**reach（600k steps）**: SGS は学習曲線 AUC で優位。seed7 では uniform が終盤まで成功率 0 に対し SGS は 0.20 到達。  
**grasp（400k）**: 最終成功率 0.10 → **0.30**（SGS）。  
※ 評価 ep 数が少なく「傾向の検証」。確定優劣の主張にはシード拡大が必要。

---

## 6. システム構成（提出用 1 枚）

| 役割 | ツール |
|------|--------|
| System ID | NVIDIA Newton（微分可能物理） |
| 並列学習 | Genesis / MuJoCo Warp |
| 精密評価 | MuJoCo（ベンチ・クロスシム評価の既定） |
| 産業物理 | PhysX（Isaac Sim、ヘッドレス） |
| 統合 | Gazebo + ROS 2（`/joint_commands` `/joint_states`） |
| デモ収集 | Quest 3 / ゲームパッド / キーボード / IK・RL エキスパート |
| オーケストレーション | dora + LLM エージェント（SayCan 風） |

共通契約: **StateDict** · **正規化行動 [-1,1]** · **共通サーボパラメータ** · 単一 URDF（`assets/robots/so101*`）。

---

## 7. 現状の到達点と限界

### 到達点

- [x] マルチシム＋パリティ計測のパイプラインが動く
- [x] 再現可能なベンチマーク出力（csv/md/protocol.json）をコミット運用
- [x] メイク Stage-0/1 のタスク定義と Stage-1 向け BC（EVA-ACT）のゲート通過実績
- [x] 学習ドキュメント 11 章＋発表スライド正本
- [x] SGS・Bi-ACT・クラウド学習フローの実装

### 限界・未了（提出時に正直に書く）

詳細・着手手順は [TODO.md](TODO.md)。要約のみ:

- 短時間 MuJoCo bench（20k）は未収束 → **主結果にしない**（→ T-P0-01）
- Stage-1 の `eval_report.json` パス未固定（→ T-P0-02）
- メイク Stage-2 以降は未実装（→ T-P2-01）
- 実機 `real_eval.csv` 未整備（→ T-P2-02、機材待ち）
- Quest→Pi は別レポート候補（→ T-P1-03 · [roadmap.md](../roadmap.md)）
- 片腕 ACT はコーヒー 5 本の学習と Thor 推論まで。ポッド未到達。40〜50 本の再学習は未了（→ T-P1-05 · [single_arm_il_work_report.md](single_arm_il_work_report.md) · [17](../17_act_record_train_infer.md)）

---

## 8. 工夫・失敗（要約）

詳細は **[design_notes.md](design_notes.md)**。提出時はそちらの D-/F- を添付または節として引用する。

| ID | 要約 |
|----|------|
| D-20261016-01 | 適材適所シム + パリティで一貫性を測る |
| D-20261016-02 | ベンチ行に seed / git SHA / run_dir を必須添付 |
| D-20261016-03 | メイク Stage 分解、Stage-1 は BC（EVA-ACT）で通す |
| D-20261016-04 | SGS でリセットをフロンティアへ |
| F-20261016-01 | 20k reach ベンチは未収束 → 主結果にしない |
| F-20261016-02 | Stage-1 を PPO だけでは通せなかった |
| F-20261016-03 | EVA-Diffusion は同ステップで品質劣位（速度は有利） |
| F-20261016-04 | PhysX はパリティが大きく学習シム主候補から外す |
| D-20261018-10 | 片腕 ACT は 4090 で学習し、Thor が計算して Pi が腕を動かす |
| F-20261018-03 | この Pi 4 では ACT の順伝播が落ちる。Thor の Python 3.14 はパッチ前、設定を読めない |

---

## 9. 提出セット（チェックリスト）

- [ ] 本レポート（本ファイル、版番号確認）
- [ ] [design_notes.md](design_notes.md)（工夫・失敗）
- [ ] [references.md](references.md) 末尾の提出前チェック（**全 ID に url + license**）
- [ ] `slides/sim2rl_overview.md` → PPTX または PDF（`cd ~/robot/sim2rl && make slides`）
- [ ] `benchmarks/20261007-064833_full5/parity.md`（パリティ）
- [ ] `docs/il_eva.md` 実測表 または該当 `runs/<dir>/eval_report.json`（IL）
- [ ] （任意）代表 run の zip: `config.yaml` + `metadata.json` + `training_curve.png` + `eval_report.json`
- [ ] 資産同梱時: SO-101 `NOTICE.md` / Apache-2.0（R-ASSET-SO101）

---

## 10. 今後の更新予定

残件の正本は **[TODO.md](TODO.md)**。主結果の版上げは v0.3（T-P0-01）。v0.2 は片腕 ACT の事実修正だけで、§5 の数値は変えていない。  
Agent 運用は **[AGENT.md](AGENT.md)**（引用・ライセンスは §9）。ここにチェックリストを複製しない。

---

## 11. 参照・ライセンス

**一覧の正本は [references.md](references.md)。** 本文では ID のみを使う。

主なもの（抜粋）:

| ID | 内容 | ライセンス |
|----|------|------------|
| R-LIC-SIM2RL | sim2RL 本体 | MIT |
| R-ASSET-SO101 | SO-ARM100 URDF/meshes | Apache-2.0 |
| R-PAPER-SGS | arXiv:2610.12465 | N/A (paper) |
| R-PAPER-EVA | arXiv:2610.06545 | N/A (paper) |
| R-PAPER-ACT | arXiv:2304.13705 | N/A (paper) |
| R-PAPER-BIACT | arXiv:2401.17698 | N/A (paper) |
| R-ALG-SB3 / MUJOCO / GENESIS | 学習・評価スタック | MIT / Apache-2.0 / Apache-2.0 |

- リポジトリ: `~/robot/sim2rl`（README / `docs/` / `benchmarks/` / `slides/`）
- ラボハブ: `~/robot/so101-lab/docs/`（実機・Quest・カメラ運用）
