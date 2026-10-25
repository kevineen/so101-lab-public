# so101-lab ドキュメント

SO-101 の **ラボ運用**と、実機での **模倣学習（ACT → SmolVLA → 双腕）** を学ぶサイトです。  
PC でもスマホでも同じ内容が読めます（左上の ☰、🔍 で全文検索）。

## 学習カリキュラム（初学者）

[**概要と進め方**](learn/README.md) から、章の番号順に進めるのがおすすめです。

- [第0章 ラボ地図](learn/00_lab_map/README.md)
- [第1章 概念（IL / ACT / VLA）](learn/01_concepts/README.md)
- [第2章 片腕 ACT](learn/02_single_arm_act/README.md)
- [第3章 SmolVLA](learn/03_smolvla/README.md)
- [第4章 その他 VLA](learn/04_other_vla/README.md)
- [第5章 双腕への道](learn/05_bimanual/README.md)

運用コマンドの正本: [片腕 IL（14）](14_single_arm_il.md) · データセット: [15](15_dataset_pipeline.md) · **PC 間転送: [23](23_data_transfer.md)** · MLflow: [16](16_local_mlflow.md) · ACT: [17](17_act_record_train_infer.md) · VRAM: [19](19_vram_guide.md) · pi05: [21](21_pi05_thor.md) · **ラン台帳: [run_registry](reports/run_registry.md)** · **データ台帳: [dataset_registry](reports/dataset_registry.md)**

## 運用マニュアル（抜粋）

- [全体概要](01_overview.md) · [LeLab](02_lelab.md) · [Web Remote](03_web_remote.md)
- [キャリブ](04_calibration.md) · [カメラ](05_cameras.md) · [トラブルシュート](06_troubleshooting.md)
- [マルチホスト](07_multi_host.md) · [Quest](11_quest_teleop_runbook.md) · [drive_profile](13_drive_profiles.md)
- 索引: [運用マニュアル一覧](manual.md)

## sim2rl との関係

シム・強化学習の教科書は兄弟リポ  
`~/robot/sim2rl/docs/learn`（そちらも `make docs-serve`、既定は同じく `:8100`。同時起動時は片方のポートを変える）。

## このサイトの開き方

```bash
# so101-lab リポジトリ直下で実行
uv sync --all-groups    # 初回のみ
make docs-serve         # http://<PCのIP>:8100
```

- **PC**: <http://localhost:8100>
- **スマホ（同じ Wi-Fi）**: `http://<PCのLAN-IP>:8100`
- 静的生成: `make docs-build` → `site/`
