# SO-101 / Web UI マニュアル

Raspberry Pi 上の SO-101 とカメラを、別 PC のブラウザから扱うためのドキュメントです。  
マルチホスト・Quest / Isaac Teleop・将来ブリッジも **この索引から辿る**。

ブラウザ / スマホで読む: リポジトリルートで `uv sync --all-groups && make docs-serve`（手順はリポ直下の `README.md`）。

| ドキュメント | 内容 |
|--------------|------|
| [00_repos.md](00_repos.md) | so101-lab / lerobot フォーク / 他リポ・Git 運用 |
| [01_overview.md](01_overview.md) | 全体構成・役割分担・同時起動の注意 |
| [02_lelab.md](02_lelab.md) | LeLab のインストールと LAN 起動 |
| [03_web_remote.md](03_web_remote.md) | Web Remote（ブラウザ操作・二臂・API） |
| [04_calibration.md](04_calibration.md) | キャリブレーションと 1臂／2臂切替 |
| [05_cameras.md](05_cameras.md) | USB / Xiao・ESP32 MJPEG / RealSense の接続 |
| [06_troubleshooting.md](06_troubleshooting.md) | 権限・起動失敗・よくあるエラー |
| [13_drive_profiles.md](13_drive_profiles.md) | **drive_profile**（gentle_7v4 / full）と 12V follower 換装 |
| [14_single_arm_il.md](14_single_arm_il.md) | **片腕 IL**: デモ収集 → ACT / SmolVLA → 実機推論（運用正本） |
| [15_dataset_pipeline.md](15_dataset_pipeline.md) | **データセット**: ローカル作成・閲覧・編集、学習への引き渡し。実施ログは [作業レポート](reports/single_arm_il_work_report.md) |
| [16_local_mlflow.md](16_local_mlflow.md) | **実験管理・学習ログ**: ローカル MLflow（Docker、`:5000`）。学習は `train_mlflow.sh` 経由のルール、命名規約、比較軸 params、後付け登録、実機評価の返却 |
| [17_act_record_train_infer.md](17_act_record_train_infer.md) | **片腕 ACT の通し手順**: デモを足す、4090 で学習、Thor で推論、Pi は腕 |
| [18_real_eval.md](18_real_eval.md) | **RL ポリシーの実機評価**（T-P2-02）: ONNX 推論＋実機 reach 採点、安全策込み |
| [19_vram_guide.md](19_vram_guide.md) | **VRAM 目安**: Diffusion / VLA（pi0 系）の学習・推論、QLoRA 量子化、vLLM/SGLang 可否 |
| [20_turbovla.md](20_turbovla.md) | **TurboVLA**: コブラ片腕への載せ方・学習結果 |
| [21_pi05_thor.md](21_pi05_thor.md) | **片腕 pi05**: LoRA 学習（3090 / 任意で Thor）→ Thor 推論 |
| [22_kamino_sim.md](22_kamino_sim.md) | **Newton Kamino**: GPU 動力学シミュ（SO-101） |
| [23_data_transfer.md](23_data_transfer.md) | **PC 間転送**: データセット・チェックポイント（Pi / GPU / Thor） |
| [24_model_eval_campaign.md](24_model_eval_campaign.md) | **学習済みモデルの実機評価・選別**: M1〜M4 を 10 試行プロトコルで順に評価。結果は [model_eval_results](reports/model_eval_results.md) |
| [learn/](learn/README.md) | **初学者カリキュラム**（概念→ACT→SmolVLA→他VLA→双腕→**力覚観測IL** 🆕）。sim2rl learn と連携 |
| [07_multi_host.md](07_multi_host.md) | Pi / Jetson Thor / メインPC / Quest の役割・ポート・独占ルール。機械可読: [`configs/lab_hosts.yaml.example`](../configs/lab_hosts.yaml.example) |
| [08_quest_isaacteleop.md](08_quest_isaacteleop.md) | メインPC での Isaac Teleop + Quest 3 セットアップ |
| [09_bridge_contract.md](09_bridge_contract.md) | Isaac Teleop → SO-101 ブリッジ契約（Phase D MVP） |
| [11_quest_teleop_runbook.md](11_quest_teleop_runbook.md) | **Quest テレオペ動作確認（Step 0〜4・順を追う）** |
| [12_mujoco_sim.md](12_mujoco_sim.md) | MuJoCo 3D 環境（可動域・干渉チェック・実機不要） |
| [checklists/](checklists/) | 個人用チェックリスト（Quest・片腕 IL 等 + `*.local.md`） |
| [10_molmoact2_thor.md](10_molmoact2_thor.md) | 双腕 MolmoAct2（Pi が実機、Jetson Thor が推論） |
| [roadmap.md](roadmap.md) | Phase A〜E の進め方 |
| [reports/](reports/) | **提出用レポート** · [TODO](reports/TODO.md) · [Agent](reports/AGENT.md) · [工夫/失敗](reports/design_notes.md) · [参考文献・ライセンス](reports/references.md) · [片腕 IL](reports/single_arm_il_work_report.md) |
| [experiments/](experiments/) | trainswap / SayCan 実験ドキュメント |

設定ファイル: `configs/so101_dual_cam.yaml`（リポ直下）  
起動スクリプト: `scripts/`  
ブリッジ置き場: `bridges/`
