# データセット台帳（dataset registry）

録画・編集・派生データセットを **1 セット = 1 行** で管理する正本。  
学習ランからは [run_registry.md](run_registry.md) の `dataset_id` で参照する（repo 名のコピペだけにしない）。

| 項目 | 値 |
|------|-----|
| 版 | **v0.1** |
| 最終更新 | 2026-10-21 |
| スプレッドシート用 | [dataset_registry.csv](dataset_registry.csv) |
| 手順 | [15_dataset_pipeline.md](../15_dataset_pipeline.md) · 転送 [23](../23_data_transfer.md) |

### 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v0.1 | 2026-10-21 | 初版。WSL 上の主要セットと派生関係、Pi のみの断片を登録 |

---

## 使い方

1. 録画が終わったら **`D-YYYYMMDD-NN`** を採番し、本ファイルの一覧と CSV に 1 行追加  
2. `repo_id` はスタンプ付きの実名（例: `local/so101_singlearm_pickup_cobra_rgb_20261020_225627`）  
3. 編集・色変換で別ディレクトリを出したら **新しい D- ID**（`parent_id` に元を書く）  
4. 学習したら run 台帳の `dataset_id` にこの ID を入れる（双方向: 下の「このセットを使ったラン」も更新）  
5. 大きな動画・parquet は git に入れない。パスだけ書く  

### 列の意味

| 列 | 必須 | 説明 |
|----|------|------|
| `dataset_id` | ✓ | 台帳 ID。`D-YYYYMMDD-NN` |
| `date` | ✓ | 作成日（録画 or 派生処理の日） |
| `status` | ✓ | `raw` / `curated` / `derived` / `smoke` / `abandoned` / `pi_only` |
| `repo_id` | ✓ | LeRobot の `local/...`（学習の `--dataset.repo_id`） |
| `root_host` | ✓ | 実体がある場所。例: `wsl:~/.cache/huggingface/lerobot/<repo_id>` |
| `task` | ✓ | `single_task` / tasks.parquet の文面 |
| `episodes` / `frames` / `fps` | ✓ | `meta/info.json` |
| `cameras` | ✓ | キー名を `+` 連結（解像度は `cam_notes`） |
| `cam_notes` | | 例: `front 424x240@15; wrist 640x480@30` |
| `parent_id` | | 派生元の `D-…`（curated / depthrgb など） |
| `derived_how` | | `delete_episodes` / `merge` / `depth_to_turbo_rgb` など |
| `used_by_runs` | | このセットを使った `R-…` をカンマ区切り |
| `note` | | 所見・捨てた本の方針など |
| `refs` | | `S-…` / `F-…` / `D-…`（design_notes） |

---

## 一覧（新しい順）

| dataset_id | date | status | repo（短い名） | ep/fr/fps | cameras | parent | used_by_runs | note |
|------------|------|--------|----------------|-----------|---------|--------|--------------|------|
| D-20261020-05 | 2026-10-20 | derived | `…_depthrgb480_20261020_225627` | 6/1797/15 | front+front_depth+wrist | D-20261020-02 | R-20261021-04, R-20261021-06 | depth→TURBO RGB + 480 系 |
| D-20261020-04 | 2026-10-20 | derived | `…_rgb480_20261020_225627` | 6/1797/15 | front+wrist | D-20261020-03 | R-20261021-03, R-20261021-05 | RGB 480 リサイズ系 |
| D-20261020-03 | 2026-10-20 | derived | `…_rgb_20261020_225627` | 6/1797/15 | front+wrist | D-20261020-02 | R-20261021-01 | depth 録画から RGB のみ抽出 |
| D-20261020-02 | 2026-10-20 | derived | `…_depthrgb_20261020_225627` | 6/1797/15 | front+front_depth+wrist | D-20261020-01 | R-20261021-02 | 1ch depth→TURBO 3ch |
| D-20261020-01 | 2026-10-20 | raw | `…_depth_20261020_225627` | 6/1797/15 | front+front_depth+wrist | — | （派生のみ） | 銀ボウル文面。front 424×240 |
| D-20261018-03 | 2026-10-18 | curated | `…_cobra_…_205119_curated` | 46/8567/30 | front+wrist | D-20261018-02 | R-20261019-01, R-20261019-02, R-20261020-01, R-20261020-02 | 評価キャンペーン本線 |
| D-20261018-02 | 2026-10-18 | raw | `…_cobra_…_205119` | 66/14298/30 | front+wrist | — | （curated へ） | 透明容器文面 |
| D-20261018-01 | 2026-10-18 | smoke | `…_coffee_smoke_…_085324` | 5/1332/30 | front+wrist | — | R-20261018-01 | コーヒー ACT スモーク |
| D-20261018-P1 | 2026-10-18 | smoke | `…_pickpen_…_082553` | 5/1021/30 | front+wrist | — | — | ペン。把持断念系 |
| D-20261018-P0 | 2026-10-18 | smoke | `…_pickpen_…_080916` | 5/1425/30 | front+wrist | — | — | ペン（前セッション） |
| D-20261018-C1 | 2026-10-18 | pi_only | `…_coffee_20261018_203243` | 1/265/30 | （要確認） | — | — | Pi のみ。不完全の可能性 |
| D-20261018-C0 | 2026-10-18 | abandoned | `…_coffee_20261018_203154` | 0/0/30 | — | — | — | 空 |
| D-20261018-W0 | 2026-10-18 | smoke | `…_wrist_smoke_…_063145` | 1/646/30 | （wrist 想定） | — | — | Pi のみ |

`repo` の正式名は CSV の `repo_id` 列を正とする。

---

## 派生関係（コブラ depth 系）

```text
D-20261020-01  depth 生録（front+front_depth+wrist）
 ├── D-20261020-02  depthrgb（TURBO 3ch）
 │    └── D-20261020-05  depthrgb480
 ├── D-20261020-03  rgb のみ
 │    └── D-20261020-04  rgb480
```

```text
D-20261018-02  cobra 66ep
 └── D-20261018-03  curated 46ep  ← 評価キャンペーン M1–M4
```

---

## 詳細（よく触るセット）

### D-20261020-01 — depth 生録（銀ボウル）

| 欄 | 内容 |
|----|------|
| repo_id | `local/so101_singlearm_pickup_cobra_depth_20261020_225627` |
| root | WSL `~/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_depth_20261020_225627` |
| task | `Grab the cobra by the neck and put its whole body inside the silver bowl.` |
| cameras | front 424×240@15（+ depth mm）· wrist 640×480@30 · dataset fps 15 |
| note | ACT は 1ch depth をそのまま食えない → D-20261020-02 へ色変換 |

### D-20261018-03 — curated 46ep（透明容器・評価本線）

| 欄 | 内容 |
|----|------|
| repo_id | `local/so101_singlearm_pickup_cobra_20261018_205119_curated` |
| task | `Grab the cobra by the neck and put its whole body inside the clear plastic container.` |
| cameras | front+wrist · 640×480 系 · 30 fps |
| used_by | R-20261019-01/02 · R-20261020-01/02（[24](../24_model_eval_campaign.md) M1–M4） |

### 行の追加テンプレ

```markdown
| D-YYYYMMDD-NN | YYYY-MM-DD | raw | `local/...` | N/F/fps | front+wrist | — | | |
```

---

## 関連

- 学習ラン台帳: [run_registry.md](run_registry.md)（`dataset_id` で結合）
- データ手順: [15](../15_dataset_pipeline.md)
