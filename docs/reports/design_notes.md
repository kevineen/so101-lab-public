# 工夫した点 · 試してダメだった点

提出用の「設計判断」と「ネガティブ結果」の正本。  
成功だけ書くと再現も審査も弱いので、**失敗も残す**。参考文献・ライセンスは必ず [references.md](references.md) に行を足してから、ここから ID で参照する。

| 項目 | 値 |
|------|-----|
| 版 | **v0.17** |
| 最終更新 | 2026-10-27 |
| 運用 | [AGENT.md](AGENT.md) §9 · [references.md](references.md) |

### 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v0.17 | 2026-10-27 | D-20261027-01: GR-BC 導入（N 視点化・ロールアウト録画 opt-in・報酬ラベリング）。F-20261027-01: v3.0 parquet は finalize まで未完成 |
| v0.16 | 2026-10-23 | F-20261023-01 / D-20261023-03: Feetech `is_using` 固まりとスマホ「バス復旧」 |
| v0.15 | 2026-10-23 | D-20261023-02: 推論をスマホ（8771）で試行開始・一時停止・成功／失敗記録 |
| v0.14 | 2026-10-23 | D-20261023-01: 残す／捨てるのあとリセット「成功」を挟まず開始待ちへ |
| v0.13 | 2026-10-18 | D-20261018-10: 片腕 ACT は 4090 で学習し Thor で推論。F-20261018-03: Pi の ACT 順伝播と Thor の Python 3.14 |
| v0.12 | 2026-10-18 | D-20261018-09: スマホにエピソード数、記録時間、ライブ映像、一時停止 |
| v0.11 | 2026-10-18 | D-20261018-08: スマホは Start/Stop のあと確認してから残し、そのあと転送。F-20261018-02: finalize が2回走り消したあとの rsync が失敗に見えた |
| v0.10 | 2026-10-18 | D-20261018-07: 録画は Pi に書いて指定 PC へ rsync。成功後に Pi 側を消す |
| v0.9 | 2026-10-18 | D-20261018-06: 録画の成功／失敗を同じ Wi-Fi のブラウザから送る。F-20261018-01: docs 用 venv に MLflow サーバを入れると重い |
| v0.8 | 2026-10-18 | D-20261018-05: MLflow UI は Docker Compose 既定 |
| v0.7 | 2026-10-18 | D-20261018-04: 学習曲線はローカル MLflow。重みと store は gitignore |
| v0.6 | 2026-10-18 | D-20261018-03: learn に論文索引とシム reach の RL 手順を追加 |
| v0.5 | 2026-10-18 | D-20261018-02: 録画の初期位置は leader の現在角。秒数は 30/15、本数は 5 のあと 40〜50 |
| v0.4 | 2026-10-18 | D-20261018-01: データセット一連を docs/15 に分け、実施は作業レポートへ |
| v0.3 | 2026-10-17 | D-20261017-02: docs/learn 初学者カリキュラム（sim2rl 連携） |
| v0.2 | 2026-10-17 | D-20261017-01: 片腕 IL（ACT/SmolVLA）を暫定主経路に |
| v0.1 | 2026-10-16 | 初版。sim2rl 実装・計測から既知の工夫／失敗を種まき |

---

## 書き方（必須フィールド）

新規エントリは次の見出し＋表。ID は `D-YYYYMMDD-NN`（工夫）または `F-YYYYMMDD-NN`（失敗）。

```markdown
### D-20261016-01 — 短いタイトル

| 欄 | 内容 |
|----|------|
| kind | `design`（工夫） / `failed`（ダメだった） / `mixed` |
| date | YYYY-MM-DD |
| context | どの TODO / 実験 / 機能か |
| what | 何をしたか（1–3 文） |
| why | なぜそうしたか / 何を期待したか |
| outcome | 結果（数値があれば単位・n 付き） |
| keep? | 採用継続 / 捨てた / 条件付きで残す |
| refs | [references.md](references.md) の ID（例: R-PAPER-SGS, R-LIC-SIM2RL）**必須・1つ以上** |
| evidence | パスまたは「なし（判断のみ）」 |
```

**ルール**

- `refs` 空欄禁止。論文・コード・資産・ツールを使ったら必ず references に登録してから書く。
- 失敗は恥ずかしい話ではなく **提出資産**。「何がダメだったか」「次に何を避けるか」を `outcome` / `keep?` に書く。
- レポート本文には要約だけ。詳細は本ファイル。

---

## 工夫した点（design）

### D-20261016-01 — シミュレータ適材適所＋パリティで一貫性を測る

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-06 前後 |
| context | sim2rl コアアーキテクチャ |
| what | 学習=Genesis/mjwarp、精密評価=MuJoCo、System ID=Newton、統合=Gazebo/ROS2 に役割分担。共通 URDF / StateDict / 正規化行動。`parity` CLI で EE 軌道差を定量化 |
| why | 1 エンジンに学習・検証・統合を全部載せると速度と精度のトレードオフで破綻しやすい |
| outcome | Genesis 対 MuJoCo の EE mean ≈ 4.9 mm（`full5`）。PhysX は mean ≈ 2.5 cm と大きく、学習シムとしては別扱い |
| keep? | 採用継続。評価は常に MuJoCo 側 |
| refs | R-LIC-SIM2RL, R-ASSET-SO101, R-DOC-PARITY |
| evidence | `sim2rl/benchmarks/20261007-064833_full5/parity.md` |

### D-20261016-02 — ベンチ行に seed / git SHA / run_dir を必須添付

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-09〜10 |
| context | `sim2rl.benchmark.run` / 再現性 |
| what | 比較表の各行が `metadata.json` 由来の git SHA と学習 `run_dir` を持つ。プロトコルは `protocol.json` |
| why | 「同じ数字を他人が出せる」を提出・査読の売りにする |
| outcome | `benchmark.md` と Colab ノートで再実行経路が文書化済み |
| keep? | 採用継続。提出数字は dirty SHA を避ける（TODO T-P1-02） |
| refs | R-DOC-BENCH, R-DOC-REPRO, R-LIC-SIM2RL |
| evidence | `sim2rl/docs/benchmarks.md` · `sim2rl/docs/reproducibility.md` |

### D-20261016-03 — メイクを Stage ゲートに分解し、Stage-1 は BC で先に通す

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-06〜07 |
| context | makeup roadmap / IL |
| what | 口紅・チークを一気に狙わず Stage0 reach → Stage1 trace（非接触）…と分解。PPO が Stage-1 ゲートに届かない前提で EVA-ACT（BC）を実装 |
| why | 接触・曲面の前に「線をなぞる」精度床を定量ゲートで固定したい |
| outcome | PPO 100k: on-path 未達（RMS 横 33.4 mm）。EVA-ACT: on-path RMS ≈ 1.53 mm でゲート通過 |
| keep? | 採用継続。Stage-2 以降は TODO P2 |
| refs | R-PAPER-EVA, R-PAPER-ACT, R-DOC-MAKEUP, R-DOC-IL-EVA |
| evidence | `sim2rl/docs/il_eva.md` 実測表 |

### D-20261016-04 — SGS でリセット分布をフロンティアへ寄せる

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-12 |
| context | `train.sgs` / grasp·reach |
| what | Success Guided Sampling を PPO 学習に組み込み、一様リセットと比較 |
| why | 易しい初期状態ばかりだと学習信号が薄い、という論文主張を自環境で検証 |
| outcome | 少数シードだが学習曲線 AUC で SGS 優位。seed7 reach では uniform 終盤 0% に対し SGS 0.20 |
| keep? | 条件付き（シード拡大が TODO T-P1-01）。trace は非対応と明記 |
| refs | R-PAPER-SGS, R-DOC-SGS |
| evidence | `sim2rl/docs/sgs.md` §8 |

### D-20261027-01 — GR-BC 導入: 2 視点化・opt-in ロールアウト録画・報酬ラベリング

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-27 |
| context | 片腕 IL の発展（失敗・介入データ活用）· `~/robot/GR-BC`（fork `nview` ブランチ）· docs/26 |
| what | ① upstream の 3 視点固定（`--cameras nargs=3`・`camera_count=3`・キャッシュ 6144 次元検証・`min_camera_hits<=3`）を N 視点に一般化。`min_camera_hits` の既定を None＝全視点一致にして 3 視点時の論文則を保存。② スマホ評価（infer_buttons）に `SO101_INFER_RECORD=1` でロールアウト録画を opt-in 追加。`robot.send_action` を tee して実指示アクションを記録、結果ボタンでエピソード確定し `grbc_manifest.jsonl` に成否を残す（未採点は破棄・ラベル捏造なし）。③ `apps/grbc/add_reward_labels.py` で lerobot フォークの `modify_features` を使い `next.reward`/`next.done` 付きコピーを作成 |
| why | GR-BC のデータ要件（LeRobot v3.0 + フレーム単位スパース成功ラベル）とラボの実況（2 カメラ・スマホ採点・報酬列なし）のギャップを、既存フローを壊さずに埋める。Pi+Jetson 構成ではフォークの `lerobot-rollout`（dagger/episodic 戦略）が使えないため infer_buttons を拡張 |
| outcome | GR-BC 側テスト 58 件合格（`tests/grbc/test_nview.py` 追加）。teamB（20ep・1 視点）で grbc-export: 到達率 1.0・重み生成。USE_GRBC=true/false で 20 ステップ学習完了（4090）。infer_buttons テスト 24 件合格。**実機での録画セッションは未検証**（初回は数試行で様子見） |
| keep? | 採用。録画は既定オフ（従来評価は完全不変）。効果検証は全成功デモでは不可能で、失敗ロールアウトが混ざる反復から。2 視点は論文設定外の改変で、効果が出なければ 3 台目カメラ追加を再検討。テスト用カメラは 96×128 以上必要（SVT-AV1 の最小 64×64 未満で C レベル FPE 落ち） |
| refs | R-PAPER-GRBC, R-CODE-GRBC, R-ASSET-MCR-CKPT, R-CODE-LEROBOT |
| evidence | `~/robot/GR-BC`（commit 8cfd460/930e3b4）· `apps/grbc/add_reward_labels.py` · `infer_buttons/rollout_record.py` · `infer_buttons/tests/test_rollout_record.py` · `docs/26_grbc_posttraining.md` |

---

## 試したけどダメだった点（failed / mixed）

### F-20261016-01 — MuJoCo reach 20k steps ベンチを「成果」に使えない

| 欄 | 内容 |
|----|------|
| kind | `failed` |
| date | 2026-10-12 |
| context | T-P0-01 の前提 · `20261012-100431_bench` |
| what | PPO/A2C × 3 seed、20 000 steps でベンチを回し提出用の表を得た |
| why | 短時間でプロトコルとハーネスの通電確認、および早期の数字が欲しかった |
| outcome | 成功率ほぼ 0%（A2C seed3 のみ 10%）。random と `mean_best_dist` 同程度 → **未収束スモーク** |
| keep? | 捨てないが **主結果にしない**。付録／通電確認扱い。長時間 run を主結果に（T-P0-01） |
| refs | R-DOC-BENCH, R-ALG-SB3 |
| evidence | `sim2rl/benchmarks/20261012-100431_bench/benchmark.md` |

### F-20261016-02 — Stage-1 trace を PPO だけで通そうとした

| 欄 | 内容 |
|----|------|
| kind | `failed` |
| date | 2026-10-07 計測 |
| context | makeup Stage-1 / RL |
| what | reach と同様に PPO で trace を学習しゲート（on-path RMS &lt; 2 mm）を狙った |
| why | 既存 RL パイプラインだけで Stage-1 を終わらせたかった |
| outcome | 100k steps でも RMS 横 33.4 mm・coverage 0.05。終点ショートカット局所解 |
| keep? | Stage-1 の主経路は BC（EVA-ACT）。RL は補助・蒸留用 |
| refs | R-DOC-IL-EVA, R-DOC-MAKEUP, R-ALG-SB3 |
| evidence | `sim2rl/docs/il_eva.md` |

### F-20261016-03 — EVA-Diffusion を同ステップ数で EVA-ACT に並ばせようとした

| 欄 | 内容 |
|----|------|
| kind | `mixed` |
| date | 2026-10-07 |
| context | IL ablation |
| what | DiT + DDIM の EVA-Diffusion を同一デモ・同ステップ数で比較 |
| why | 拡散政策が追従品質で勝つか、レイテンシとのトレードオフを見たい |
| outcome | success 80%・on-path RMS 3.3 mm で ACT より劣位。一方 ms/chunk は Diffusion≈210 vs ACT≈540（RTX 4090）で **速度は拡散側が有利** |
| keep? | ベースラインとして残す。品質主戦場は ACT。実機リアルタイム化では compile 等とセットで再検討 |
| refs | R-PAPER-EVA, R-PAPER-DIFFPOLICY, R-DOC-IL-EVA |
| evidence | `sim2rl/docs/il_eva.md` レイテンシ表 |

### F-20261016-04 — PhysX を Genesis 並みの学習シム候補とみなすとパリティが厳しい

| 欄 | 内容 |
|----|------|
| kind | `failed` |
| date | 2026-10-06 |
| context | parity `full5` |
| what | mujoco / mjwarp / genesis / newton / physx を同一プロトコルで比較 |
| why | Isaac 系物理も学習・評価に使えるなら選択肢が増える |
| outcome | PhysX の EE mean 0.025 m・max 0.13 m と基準から大きく乖離。クロスシム「学習→MuJoCo 評価」の前提が弱い |
| keep? | 参考バックエンドとして残す。主学習は Genesis/mjwarp、主評価は MuJoCo |
| refs | R-DOC-PARITY, R-LIC-ISAAC（利用時） |
| evidence | `sim2rl/benchmarks/20261007-064833_full5/parity.md` |

### D-20261017-02 — 実機 IL を docs/learn カリキュラム化し sim2rl learn と対にする

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-17 |
| context | so101-lab 教育・オンボーディング |
| what | `docs/learn/` に第0〜5章（ラボ地図→概念→片腕ACT→SmolVLA→他VLA→双腕地図）を追加。運用コマンドは docs/14 に残し、learn は順序と概念を担当。sim2rl `docs/learn` から相互リンク |
| why | 初学者が「短腕/片腕 ACT→言語 VLA→双腕」の順で自学でき、シム RL（sim2rl）と実機 IL（so101-lab）を混同しないようにする |
| outcome | 索引・roadmap Phase E・sim2rl learn README/07/09 を更新 |
| keep? | 採用。章の追加は同フォルダに足す |
| refs | R-DOC-SO101-LEARN, R-DOC-SIM2RL-LEARN, R-DOC-SO101-SINGLE-IL, R-PAPER-ACT, R-PAPER-SMOLVLA |
| evidence | `docs/learn/README.md` |

### D-20261017-01 — 第2駆動腕を切り、片腕 ACT / SmolVLA で学習を先に進める

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-17 |
| context | so101-lab 実機 IL · T-P1-05 |
| what | 物理 leader を Web Remote 第2駆動腕にすると肘 Overload／トルク不足。`leader_arm.enabled: false` にし、デモは `so101_leader` 手テレオペ、学習対象は follower のみ。手順を `docs/14_single_arm_il.md` に固定 |
| why | soft `gentle_7v4` では定格トルクは上がらない。12V follower 換装までの間も ACT/VLA 試行を止めない |
| outcome | ドキュメント・yaml 既定・チェックリストを片腕経路に更新（実測学習は未実施 → T-P1-05） |
| keep? | 換装完了まで採用。双腕常用時は [13](../13_drive_profiles.md) に戻す |
| refs | R-PAPER-ACT, R-PAPER-SMOLVLA, R-CODE-LEROBOT, R-DOC-LEROBOT-IL, R-DOC-SO101-SINGLE-IL |
| evidence | `docs/14_single_arm_il.md` · `configs/so101_dual_cam.yaml` |

### D-20261018-01 — データセットの一連を手順書と作業レポートに分ける

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL · T-P1-05 |
| what | 作成・閲覧・編集・学習への引き渡しを `docs/15_dataset_pipeline.md` に書き、実施事実は `docs/reports/single_arm_il_work_report.md` に積む。14 はキャリブ・テレオペ・推論の正本のまま、15 へリンクする |
| why | 14 に閲覧・編集と提出ログを足すと運用コマンドと実施記録が混ざる。Hub 未ログインの Pi では、先にローカル保存（`push_to_hub=false`）でデータセットを残せるようにする |
| outcome | 手順とレポート雛形を追加。環境確認（両腕・D435・follower 先端）まで。デモ本数は 0。学習は未実施 |
| keep? | 採用。セッションごとにレポートへ事実を足し、失敗は F- に残す |
| refs | R-DOC-SO101-DATASET-PIPELINE, R-DOC-LEROBOT-DATASET-TOOLS, R-CODE-LEROBOT, R-DOC-SO101-SINGLE-IL |
| evidence | `docs/15_dataset_pipeline.md` · `docs/reports/single_arm_il_work_report.md` |

### D-20261018-02 — 録画の初期位置は leader の現在角、本数はスモーク 5 / 学習 40〜50

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL · T-P1-05 |
| what | `lerobot-record` は開始座標を持たない。各エピソードの初期位置は録画開始時の leader 関節角とし、ラボ nest（`~/.cache/so101-lab/home_poses.json`）は録画前に両腕を揃える姿勢として使う。pick-and-place は録画 30 秒・リセット 15 秒、スモーク 5 本、学習用 40〜50 本。手順は `docs/15_dataset_pipeline.md` |
| why | 公式既定は 60 秒 / 60 秒 / 50 本で、接続時に home へ戻る処理もない。nest を録画の開始座標として書くと、record がその JSON を読むように読める。短いタスクで 60 秒待つと、終了後の静止が学習データに入る |
| outcome | 15 に「初期位置」「本数と時間」を追記。14 の録画コマンドへ秒数を足し、初学者レッスン・チェックリスト・Web Remote からリンク。実録画は未実施 |
| keep? | 採用。タスクが長くなるときは `episode_time_s` を延ばす。nest の数値は JSON が正本 |
| refs | R-DOC-LEROBOT-IL, R-CODE-LEROBOT, R-DOC-SO101-DATASET-PIPELINE |
| evidence | `docs/15_dataset_pipeline.md` · `~/.cache/so101-lab/home_poses.json`（`updated_at` 2026-10-18T02:56:44Z） |

### D-20261018-03 — learn に論文索引とシム reach の強化学習手順を置く

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab `docs/learn` · sim2rl `docs/learn/02_rl` |
| what | 論文リンクを `docs/learn/papers.md` に集め、PPO で reach を回す手順を第1章レッスン3にした。仕組みの正本は sim2rl 第2章のまま、実習ページからも論文へリンクする |
| why | 実機 IL の章に論文 URL が散らばり、RL は「sim2rl を見よ」だけで手順がカリキュラムから辿れなかった。実機 PPO を最初の手順にすると失敗コストが大きい |
| outcome | 論文索引・レッスン3・第4章の論文列・mkdocs を追加。学習の実行は未実施 |
| keep? | 採用。長い導出は sim2rl に残し、so101-lab は順番とリンクを担当する |
| refs | R-DOC-SO101-LEARN, R-DOC-SIM2RL-LEARN, R-PAPER-PPO, R-PAPER-SAC, R-PAPER-ACT, R-PAPER-SMOLVLA, R-PAPER-PI0, R-PAPER-MOLMOACT2, R-PAPER-XVLA |
| evidence | `docs/learn/papers.md` · `docs/learn/01_concepts/03_rl_procedure.md` |

### D-20261018-04 — 学習曲線はローカル MLflow に残し、重い成果物は git に入れない

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL の学習ログ · T-P1-05 |
| what | `lerobot-train` のロガー呼び出しはそのままに、`scripts/train_mlflow.sh` がロガークラスをローカル MLflow に差し替える。UI は `./scripts/start_mlflow.sh`（sqlite、`:5000`）。チェックポイント重みと評価動画は学習 `output_dir` に置き、MLflow にはスカラー・短いパラメータ・設定 JSON とチェックポイントのパスだけを書く |
| why | 曲線を手元に残したい。クラウドの実験サービスへアカウントとデータを送らず、`vendor/lerobot` も改変しない。重みと `mlflow_store/` をコミットするとリポジトリが肥大する |
| outcome | 手順 `docs/16_local_mlflow.md`、ロガー `tracking/`、gitignore を追加。学習そのものは未実施。2026-10-18 に `uv run --group tracking -m unittest tracking.tests.test_mlflow_tracking` が 4 件成功（スカラーは sqlite、重みファイルは artifact に入らない） |
| keep? | 採用。動画を UI に載せるときだけ `SO101_MLFLOW_LOG_MEDIA=1`（コピー先も gitignore の store） |
| refs | R-TOOL-MLFLOW, R-DOC-SO101-MLFLOW, R-CODE-LEROBOT |
| evidence | `docs/16_local_mlflow.md` · `tracking/logger.py` · `configs/mlflow.yaml` · `.gitignore` |

### D-20261018-05 — MLflow UI は Docker Compose を既定にする

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab ローカル学習ログ · D-20261018-04 の続き |
| what | `docker-compose.yml` で `ghcr.io/mlflow/mlflow:v2.22.1` を起動。ホストの `mlflow_store/` を `/mlflow` にマウントし、`--serve-artifacts` で HTTP 経由の artifact 書き込みにする。`./scripts/start_mlflow.sh` の既定 backend を `docker` にし、`SO101_MLFLOW_BACKEND=uv` で従来のホスト起動を残す |
| why | UI 用に so101-lab の Python に MLflow を入れなくてよく、学習クライアント（lerobot venv）とサーバのライフサイクルを分離できる。パス差は artifact proxy で吸収する |
| outcome | `make mlflow-serve` で `:5000/health` が応答。学習記録のクライアント側は変更なし（ポートが開いていれば HTTP） |
| keep? | 採用 |
| refs | R-TOOL-MLFLOW, R-DOC-SO101-MLFLOW |
| evidence | `docker-compose.yml` · `scripts/start_mlflow.sh` · `docs/16_local_mlflow.md` |

### F-20261018-01 — so101-lab の venv で MLflow サーバを上げると重い

| 欄 | 内容 |
|----|------|
| kind | `failed` |
| date | 2026-10-18 |
| context | D-20261018-04 の初版（このマシンで `mlflow server`） |
| what | `pyproject.toml` の dependency group `tracking` に MLflow 本体を入れ、`./scripts/start_mlflow.sh` が `uv sync --group tracking` してから `:5000` を待った |
| why | 学習曲線を同じチェックアウトで見られると思った |
| outcome | サーバ起動時に sklearn / pandas などを含む一式が入った。`uv sync --group tracking` は docs グループ（mkdocs）を環境から外した |
| keep? | 捨てた。この venv は docs だけ。UI は Docker Compose（D-20261018-05）。Docker が無いときだけ `SO101_MLFLOW_BACKEND=uv` |
| refs | R-TOOL-MLFLOW, R-DOC-SO101-MLFLOW |
| evidence | `docs/16_local_mlflow.md` · `scripts/start_mlflow.sh` |

### D-20261018-06 — 録画の成功／失敗は同じ Wi-Fi のブラウザから、キーボードと同じフラグで送る

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL のデモ録画 · T-P1-05 |
| what | `scripts/record_with_buttons.sh` が `lerobot-record` と同じ引数で録画し、`0.0.0.0:8770` にスマホ向けの「成功」「失敗」「中止」を出す。成功は `n`、失敗は `r`、中止は `q`。vendor の record は編集せず、`init_keyboard_listener` と `record_loop` のモジュールグローバルを差し替える |
| why | 物理 leader を両手で持っていると、録画端末の `n` / `r` に届きにくい。Web Remote はシリアルを占有するので録画中は起動できない。ブラウザボタンは進行フラグだけを書き、腕のポートは開かない |
| outcome | 単体テストでフラグがキーボードと一致することを確認。実機での録画本数は 0。データセットに成功列は増えない。失敗は従来どおりその本を保存しない |
| keep? | 採用。ポートが取れないときはキーボードだけで続ける。押し間違いの失敗はその場で取り消せない（`r` と同じ） |
| refs | R-CODE-LEROBOT, R-DOC-SO101-DATASET-PIPELINE |
| evidence | `record_buttons/` · `scripts/record_with_buttons.sh` · `docs/15_dataset_pipeline.md` |

### D-20261018-07 — 録画は Pi に書き、保存後に指定 PC へ送ってから Pi 側を消す

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL のデモ録画 · T-P1-05 · Pi の保存容量 |
| what | `configs/dataset.local.env` の `SO101_DATASET_SSH` と `SO101_DATASET_DIR` を送り先にする。`save_episode` のあと rsync し、`finalize` で揃ってから `SO101_DATASET_DELETE_LOCAL=1` のとき Pi のそのデータセットディレクトリだけ消す。vendor の record は編集しない |
| why | デモの正本を MLflow と同じ PC に置き、Hugging Face には上げない。録画のフレームをネットワーク先へ直接書くと、切断でその本が中途半端になる。送り先 IP はよく変わるので git に入れない |
| outcome | 単体テストで、転送失敗時は Pi に残り、成功時だけ消えることを確認。実機の録画本数は 0。2026-10-18 時点で Pi から `${SO101_GPU_LAN_IP}:5000` は届いていなかった |
| keep? | 採用。`SO101_DATASET_SSH` が空なら Pi だけ。失敗した転送は消さない |
| refs | R-CODE-LEROBOT, R-DOC-SO101-DATASET-PIPELINE, R-TOOL-RSYNC, R-TOOL-OPENSSH |
| evidence | `record_buttons/offload.py` · `configs/dataset.local.env.example` · `docs/15_dataset_pipeline.md` |

### D-20261018-08 — スマホは Start / Stop のあと映像を見てから残し、そのあと転送する

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL のデモ録画 · T-P1-05 · `0.0.0.0:8770` |
| what | 開始待ちで Start（`n`）するまでフレームを書かない。Stop で止め、front / wrist の間引き JPEG を見てから「残す」か「捨てる」かを決める。残した本だけ、次の Start の前とセッション最後に rsync する。確認中は follower を動かさない |
| why | 録画中の「成功」は、止めることと残すことが同時だった。転送も保存と同時に始まり、見る前に Pi 側が消えることがあった。残す判断のあとに送り、制御ループ中は rsync しない |
| outcome | ロボットを動かさず `record_buttons.tests` を実行して確認。実機の新しい録画本数は 0。D-20261018-06 の「押した瞬間に成功」は、この操作に置き換える |
| keep? | 採用。ポートが取れないときはキーボードの `n` / `r` / `q`。押し間違いの「捨てる」は取り消せない |
| refs | R-CODE-LEROBOT, R-DOC-SO101-DATASET-PIPELINE, R-TOOL-RSYNC, R-TOOL-OPENSSH |
| evidence | `record_buttons/` · `docs/15_dataset_pipeline.md` |

### D-20261018-09 — スマホにエピソード数、記録時間、ライブ映像、一時停止を出す

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL のデモ録画 · T-P1-05 · `0.0.0.0:8770` |
| what | 同じページに、いまのエピソード / 予定本数、保存済み本数、記録またはリセットの経過時間、`front` / `wrist` のライブ JPEG を出す。記録開始・記録終了・一時停止を置く。一時停止は `lerobot_record` の `time.perf_counter` と `add_frame` だけ止め、制御ループは回したままにする。vendor の record は編集しない |
| why | リーダーを持ったまま、何本目か、あと何秒か、ペンとマウスパッドが映っているかを見たい。一時停止で腕のトルクを切ると、追従が切れたまま次のフレームが危険になる |
| outcome | ロボットを動かさず `record_buttons.tests` を実行して確認。実機の新しい録画本数は 0。一時停止にキーボード相当は無い |
| keep? | 採用。一時停止中も follower はリーダーに追従する。トルクを切るのは手元の ESTOP |
| refs | R-CODE-LEROBOT, R-DOC-SO101-DATASET-PIPELINE |
| evidence | `record_buttons/` · `docs/15_dataset_pipeline.md` |

### F-20261018-02 — finalize が2回走り、消したあとの rsync が失敗に見えた

| 欄 | 内容 |
|----|------|
| kind | `failed` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL のデモ録画 · `so101_single_pickpen_edge_mousepad_smoke_20261018_080916` |
| what | 5 本・1425 フレームの録画の最後に「データセットを移しました（Pi 側は削除）」のあと、同じパスへの rsync が `No such file or directory` になり「Pi に残しています」と出た。実体は転送先にあり、Pi 側は無かった |
| why | `VideoEncodingManager` と `record()` の `finally` がどちらも `dataset.finalize()` を呼ぶ。1 回目で同期して消し、2 回目が消したディレクトリを送ろうとして失敗した |
| outcome | データは失っていない（転送先に 5 エピソード、front / wrist の mp4）。2 回目の finalize は成功済みなら何もしないようにした。制御ループは別問題で、実測 9.49 Hz（目標 30 Hz） |
| keep? | 失敗の出方は直す。9.49 Hz の録画そのものは、このエントリでは直していない |
| refs | R-CODE-LEROBOT, R-DOC-SO101-DATASET-PIPELINE, R-TOOL-RSYNC |
| evidence | 転送先 `${SO101_GPU_SSH}:$HOME/.cache/huggingface/lerobot/local/so101_single_pickpen_edge_mousepad_smoke_20261018_080916`（`total_episodes` 5、`total_frames` 1425）。Pi 側の同じパスは不在 |

### D-20261018-10 — 片腕 ACT は 4090 で学習し、Thor が計算して Pi が腕を動かす

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-18 |
| context | so101-lab 片腕 IL · T-P1-05 · コーヒーポッドのスモーク |
| what | 録画とクライアントは Pi、`lerobot-train` は 4090 の WSL（`../lerobot`）、順伝播は Thor の `policy_server`（`:8080`）。重みは `checkpoints/last/pretrained_model` を Thor のホームへ rsync する。5 本・5,000 step の重みは比較用に残し、次の学習の初期値にはしない。届かせる学習は、残した本にデモを足した新しい `output_dir` でやり直す |
| why | 腕とカメラは Pi にある。この Pi 4 では ACT の順伝播が落ちる（F-20261018-03）。4090 の学習 venv は root 所有で、実機シリアルも無い。Thor は CUDA が見え、MolmoAct2 と同じ gRPC の分け方で ACT も載る |
| outcome | 2026-10-18、5 本・1332 フレームで 5,000 step まで学習した。Thor で約 40 秒、follower は目標に向かって動いた。ポッドには届いていない。手順は `docs/17_act_record_train_infer.md` |
| keep? | 採用。`max_relative_target=5`、切断時はトルクを切らない。ESTOP は手元 |
| refs | R-CODE-LEROBOT, R-ALG-TORCH, R-DOC-SO101-SINGLE-IL, R-DOC-SO101-DATASET-PIPELINE, R-DOC-SO101-ACT-RUNBOOK |
| evidence | データセット `${SO101_GPU_SSH}:~/.cache/huggingface/lerobot/local/so101_single_coffee_smoke_20261018_085324`。重み `.../act_so101_coffee_smoke_20261018/checkpoints/last/pretrained_model`。Thor `$HOME/act_so101_coffee_smoke_20261018` |

### D-20261023-01 — 残す／捨てるのあと「成功」を挟まず開始待ちへ進む

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-23 |
| context | so101-lab 片腕 IL のデモ録画 · `record_with_buttons` · `0.0.0.0:8770` |
| what | 確認で「残す」または「捨てる」を押したら、vendor の `reset_time_s` 待ちとスマホの「成功」を飛ばし、すぐ次の開始待ちへ進む。物と腕の戻しは開始待ち（leader 追従または nest 保持）で行い、揃ったら記録開始 |
| why | 残す→成功→記録開始の 2〜3 step が両手テレオペ中に余分だった。捨てるはもともとリセットを飛ばしており、残すだけ「成功」が必要だった |
| outcome | `record_buttons` の単体テストで、keep 後の reset slice が走らないことを確認。実機再録画は未実施 |
| keep? | 採用。キーボード単体の `lerobot-record` は従来どおり `reset_time_s` を使う。残すあとに「失敗」で取り消す経路は無くなる（押し間違いは選別で捨てる） |
| refs | R-CODE-LEROBOT, R-DOC-SO101-DATASET-PIPELINE |
| evidence | `record_buttons/hook.py` · `docs/15_dataset_pipeline.md` · `record_buttons/tests/test_server.py` |

### D-20261023-02 — 推論もスマホで試行開始・一時停止・結果記録する

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-23 |
| context | so101-lab 片腕 IL 実機評価 · T-P1-05 / snake_bowl · `0.0.0.0:8771` |
| what | `scripts/infer_with_buttons.sh` が `robot_client` と同じ引数で推論し、スマホに試行 n/N・経過・ライブ映像・開始／一時停止／成功・失敗種別を出す。vendor の `control_loop` だけ差し替え、開始待ちでは観測をサーバへ送らない |
| why | 録画は 8770 で両手テレオペ中にボタンを押せるが、推論は `Ctrl+C` とターミナル依存で 10 試行の成功／失敗種別が残りにくい。評価プロトコル（[24](../24_model_eval_campaign.md)）と同じ操作を画面に載せる |
| outcome | ロボットを動かさず `infer_buttons.tests` を実行して確認。実機の snake_bowl 順次推論は未実施（SmolVLA 学習中・トルク ON は別確認） |
| keep? | 採用。ポート既定 8771（録画 8770 と分離）。ESTOP は手元のまま。この画面はトルクを切らない |
| refs | R-CODE-LEROBOT, R-DOC-SO101-ACT-RUNBOOK, R-DOC-SO101-MODEL-EVAL |
| evidence | `infer_buttons/` · `scripts/infer_with_buttons.sh` · `docs/24_model_eval_campaign.md` §8–9 · `infer_buttons/tests/test_server.py` |

### F-20261023-01 — 推論中に Feetech `is_using` が固まり Port is in use が続く

| 欄 | 内容 |
|----|------|
| kind | `failed` |
| date | 2026-10-23 |
| context | so101-lab 片腕推論 · `infer_with_buttons` · snake_bowl |
| what | 試行終了や nest 解除のあと、`Present_Position` の sync_read が `[TxRxResult] Port is in use!` で落ち、ready / result の観測が約 2 秒間隔で失敗し続けた |
| why | OS のポート占有ではなく、Feetech SDK の `port_handler.is_using` がパケット途中切れ／重なりで True のまま残る。一度固まると以降の TX が全部失敗する |
| outcome | クライアント再起動で復帰。`web_remote` には `_release_bus_port` があったが推論スマホ経路には無かった |
| keep? | 失敗として残す。対策は D-20261023-03 |
| refs | R-CODE-LEROBOT |
| evidence | 端末ログ `ready observation failed` / `result observation failed` · `web_remote/web_remote/session.py` `_release_bus_port` |

### D-20261023-03 — スマホ「バス復旧」と観測失敗時の is_using クリア

| 欄 | 内容 |
|----|------|
| kind | `design` |
| date | 2026-10-23 |
| context | F-20261023-01 · `infer_buttons` · `0.0.0.0:8771` |
| what | `release_bus_port` で `is_using=False`（必要なら `clearPort`）。観測／制御が Port is in use のとき自動クリア。スマホに「バス復旧」ボタン（ready / running / result） |
| why | 評価中にクライアント再起動すると試行カウントとサーバ接続が切れる。手元の ESTOP ではなくバスフラグだけの復旧を画面から押せるようにする |
| outcome | 単体テストでフラグクリアとボタン配線を確認。実機再発時の手動ボタン確認は未実施 |
| keep? | 採用。USB 本体切断（deleted FD）は再起動が必要で、このボタンでは直らない |
| refs | R-CODE-LEROBOT |
| evidence | `infer_buttons/serial_health.py` · `infer_buttons/hook.py` · `infer_buttons/server.py` · `infer_buttons/tests/test_server.py` |

### F-20261018-03 — Pi では ACT が落ち、Thor の Python 3.14 はそのままでは設定を読めない

| 欄 | 内容 |
|----|------|
| kind | `failed` |
| date | 2026-10-18 |
| context | so101-lab 片腕 ACT 推論 · T-P1-05 |
| what | Pi の `lerobot-rollout` はカメラと follower を繋いだあと、行動を出す前に Illegal instruction（終了コード 132）で落ちた。Thor の `policy_server` は、ACT の設定を読むときに `typing.Dict[str, PolicyFeature] \| None is not callable` で落ちた |
| why | Pi の torch は `2.11.0+cu128` で、大きい行列積が Cortex-A72 では実行できない命令になる。Thor の venv は Python 3.14.2、draccus 0.8.0 で、Union 注釈を argparse の `type=` に渡している |
| outcome | Pi では行動は出ていない。Thor は `scripts/patch_draccus_py314.py` のあとサーバを上げ直し、CUDA の forward が `(1, 100, 6)` になった。その状態で実機は約 40 秒動いた |
| keep? | この Pi で ACT を計算しない。パッチは venv の site-packages なので、作り直したらスクリプトを再実行する |
| refs | R-CODE-LEROBOT, R-ALG-TORCH, R-DOC-SO101-ACT-RUNBOOK |
| evidence | Pi: `vendor/lerobot/.venv` の torch `2.11.0+cu128`。Thor: `draccus/wrappers/field_wrapper.py` をその venv だけ修正。手順 `docs/17_act_record_train_infer.md` |

### F-20261027-01 — v3.0 データセットの parquet は finalize まで読めない

| 欄 | 内容 |
|----|------|
| kind | `failed` |
| date | 2026-10-27 |
| context | GR-BC ロールアウト録画の単体テスト · `infer_buttons/rollout_record.py` · lerobot フォーク v0.6.2 |
| what | `LeRobotDataset.create` → `save_episode` の直後に pandas で `data/**/*.parquet` を読むと `Parquet magic bytes not found in footer` で失敗。ファイルはヘッダ（PAR1）だけ書かれ、フッタが無い |
| why | v3.0 の DatasetWriter は parquet をストリーム書き込みしており、フッタ（メタデータ）は `LeRobotDataset.finalize()` で閉じるときに初めて書かれる。`save_episode` の戻り時点ではデータファイルは未完成 |
| outcome | `RolloutRecorder.close()` で `finalize()` を呼ぶように修正（`LeRobotDataset.finalize` の docstring も "otherwise the dataset will be invalid" と明記）。テストは close 後に検証して 5 件合格 |
| keep? | 失敗として残す。**録画・変換スクリプトで v3.0 データセットを書いたら、読む前に必ず finalize**。セッション途中のデータセットディレクトリを読まない運用（docs/26 に明記済み） |
| refs | R-CODE-LEROBOT |
| evidence | `infer_buttons/rollout_record.py` `close()` · `lerobot/src/lerobot/datasets/lerobot_dataset.py` `finalize()` docstring · `infer_buttons/tests/test_rollout_record.py` |

---

## 未記入メモ（後でエントリ化）

作業中に気づいたがまだ表にしていないこと。週次で空にする。

- [ ] dirty ツリーのままベンチをコミットした運用の反省（T-P1-02 とセットで F 化可）
- [ ] Quest / so101-lab 側の失敗談（腕落下・ブラウザ非対応など）→ 別レポート着手時に F 追加
- [x] 片腕 ACT 初回スモークの成功／失敗 → D-20261018-10 · F-20261018-03（40〜50 本の再学習は未了）
