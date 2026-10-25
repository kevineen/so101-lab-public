# 推論評価動画

実機推論の録画（スマホ外撮りで可）を置く場所。  
台帳の `video_path` からここを指す: [docs/reports/run_registry.md](../../docs/reports/run_registry.md)

## 置き方

```text
data/eval_videos/<run_id>/
  trial01.mp4
  trial02.mp4
  ...
  README.md   # 任意。試行メモ
```

例: `data/eval_videos/R-20261021-01/trial01.mp4`

- **git に大きな mp4 は入れない**（`.gitignore` 済み想定。入れるなら LFS か外部共有）
- 台帳 CSV / Markdown にはパスだけ書く
- ファイル名は `trialNN.mp4`（ゼロ埋め 2 桁）に揃えると後から並べやすい
