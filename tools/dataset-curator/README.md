# LeRobot Dataset Curator

Premiere 風の UI で LeRobot データセットを閲覧・選別・トリムし、キュレーション済みの
新しいデータセットとして書き出すローカル Web アプリ。

- 全エピソードをブラウザで閲覧 (複数カメラ同期再生)
- エピソード単位の削除マーク
- フレーム単位のイン/アウト点 (トリム範囲) 設定
- state/action の信号波形をタイムラインに表示 (グリッパー開閉が見える)
- 編集内容は `<dataset-root>/curation.json` に自動保存
- 「適用」で `*_curated` 新データセットを作成 (元は変更しない)

## 起動

```bash
cd ~/robot/so101-lab/tools/dataset-curator
./run.sh local/so101_singlearm_pickup_cobra_20261018_205119 \
    ~/.cache/huggingface/lerobot/local/so101_singlearm_pickup_cobra_20261018_205119
# → http://127.0.0.1:8787 をブラウザで開く (Chrome / Edge / Firefox 推奨: AV1 コーデック)
```

## 依存関係

Python は **lerobot フォークの venv**（正規配置 `~/robot/lerobot/.venv`、`LEROBOT_DIR` で上書き可）
を使用する。追加インストール不要（fastapi/uvicorn 含む）。

`apply_curation.py` は lerobot フォークの **内部 API**（`lerobot.datasets.dataset_tools` の
`_keep_episodes_from_video_with_av` / `_load_episode_with_stats` / `_write_parquet` 等）に依存する。
**フォークの更新で壊れる可能性がある**ため、動作確認は `tests` 相当のスモーク
（小さいデータセットへの適用）で行うこと。開発時点のフォークコミット: `7dccbe04` (frs ブランチ)。

## 操作 (ショートカット)

| キー | 動作 |
|---|---|
| `Space` | 再生 / 停止 |
| `←` / `→` | ±1 フレーム (再生中は停止) |
| `Shift+←/→` または `J` / `L` | ±1 秒 |
| `K` | 停止 |
| `I` / `O` | 現在のフレームにイン点 / アウト点を設定 |
| `X` | トリム解除 |
| `D` | エピソード削除トグル |
| `↑` / `↓` (PageUp/Dn) | 前 / 次エピソード (絞り込み中はその範囲で) |
| `Home` / `End` | イン点 / アウト点へ移動 |
| `?` | ヘルプ表示 |

タイムラインはクリックでシーク、青のマーカー (⟦I⟧/⟦O⟧) をドラッグして範囲調整もできる。

## curation.json

`<dataset-root>/curation.json`:

```json
{
  "version": 1,
  "episodes": {
    "5":  {"decision": "delete"},
    "12": {"decision": "keep", "trim": [30, 250], "reviewed": true}
  }
}
```

- `trim` はエピソードローカルの `[start, end)` フレーム (end は排他)。未記載のエピソードは全体保持。
- `reviewed` は UI 上で「確認済み」フィルタに使うだけのフラグ (適用には影響しない)。

## 適用 (書き出し)

UI の「適用」ボタン、または CLI 単体:

```bash
~/robot/lerobot/.venv/bin/python apply_curation.py \
  --repo-id local/mydataset \
  --root /path/to/mydataset \
  [--curation /path/to/curation.json] \
  [--output-repo-id local/mydataset_curated] [--output-root /path/to/out]
```

処理内容:

1. 削除マークのエピソードを除外
2. トリム範囲のデータ行のみ抽出 (frame_index / timestamp / index を振り直し)
3. 動画をフレーム範囲で再エンコード (SVT-AV1, 元のエンコーダ設定を引き継ぎ)。
   全話無編集のファイルはそのままコピー
4. エピソードメタデータ・統計を再計算して新データセットとして完成

出力は `LeRobotDataset` としてそのまま学習に使える:

```bash
lerobot-train --dataset.repo-id local/mydataset_curated --dataset.root /path/to/mydataset_curated ...
```

### 備考

- 動画がデータ行より短いエピソード (ドロップフレーム) は、適用時に動画側の実フレーム数へ
  クランプされる (自己整合的なデータセットになり、次エピソードのフレームを借りる
  元データセットの不整合も解消される)。UI に警告表示される。
- 元データセットは一切変更されない (curation.json の追記のみ)。

## ファイル構成

- `curate_server.py` — FastAPI サーバー (API + 動画 Range 配信)
- `apply_curation.py` — 適用パイプライン (lerobot 内部 API を利用)
- `static/` — フロントエンド (バニラ JS)
- `run.sh` — 起動スクリプト
