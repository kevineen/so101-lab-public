# 学習済みモデル実機評価・選別 — 個人チェックリスト

正本手順: [24_model_eval_campaign.md](../24_model_eval_campaign.md) · 推論経路: [17_act_record_train_infer.md](../17_act_record_train_infer.md) · 結果の記録先: [model_eval_results.md](../reports/model_eval_results.md)

```bash
cp docs/checklists/model_eval.checklist.md docs/checklists/model_eval.local.md
```

| 記録 | 値 |
|------|-----|
| 名前 / 日付 | |
| 評価 ID（例: E-20261021-01） | |
| 対象モデル（M1〜M4） | |
| 物体の定位置メモ（写真のパスでも） | |
| 備考 | |

---

## 開始前（キャンペーンで 1 回）

- [ ] 対象モデル 4 つ（M1〜M4）の重みが WSL にある（[24 §1](../24_model_eval_campaign.md) の表）
- [ ] WSL で `config.json` 確認コマンドを実行し、各モデルのカメラ / `n_action_steps` を記録した
- [ ] WSL → Thor へ 4 重みを `~/so101_eval/<学習ディレクトリ>/` に rsync した
- [ ] Thor で `patch_draccus_py314.py` を実行し `already patched` / `patched:` を確認した
- [ ] Thor で `policy_server` を起動し `PolicyServer started on 0.0.0.0:8080` を確認した
- [ ] 結果記録用の評価 ID を決め、[model_eval_results.md](../reports/model_eval_results.md) に見出しを作った

## 毎セッション（電源を入れるたび）

- [ ] LeLab 停止
- [ ] Web Remote 停止
- [ ] ESTOP 手の届く位置
- [ ] follower ホーム付近・干渉なし
- [ ] Pi で `go_so101_home.sh --arm follower` が通る

## モデルを替えるとき（M1→M2→M3→M4）

- [ ] クライアント `Ctrl+C` → nest へ戻した
- [ ] `--pretrained_name_or_path` を Thor 上の新しいパスへ替えた
- [ ] `--actions_per_chunk` を替えた（ACT = 100 / Diffusion = 32）
- [ ] `--robot.cameras` を替えた（wrist-only モデルは `front` を削る）
- [ ] Thor のログに新しい `Policy type | Pretrained name or path` が出た

## 各試行（× 10）

- [ ] nest から開始（スマホ「nest へ」または `go_so101_home.sh`）
- [ ] コブラ・容器を定位置に置いた
- [ ] `infer_with_buttons.sh` 起動済みならスマホ「試行開始」（60 秒で自動結果画面。[24 §8](../24_model_eval_campaign.md#infer-buttons)）
- [ ] 結果を 1 行記録（成功 / 失敗種別 `no_reach`・`no_grasp`・`no_place`・`disturb` / 秒数）。スマホでも同じボタン
- [ ] nest へ戻した

## モデルの評価が終わったら

- [ ] 10 試行の表を埋めた
- [ ] 成功率・平均完了時間・失敗種別の分布を集計した
- [ ] 判定（合格 5/10 以上 / 落選）と理由を 1 行で書いた
- [ ] `scripts/log_eval_mlflow.py` で MLflow run に成功率・失敗内訳を返した（[16](../16_local_mlflow.md)）
- [ ] 落選モデルの重みは消していない

## キャンペーン全体の終わりに

- [ ] 4 モデルの比較表を埋めた
- [ ] 勝ち残りを 1 つ決めた（選出理由つき）
- [ ] 合格モデルがあれば位置ばらつき評価（3 箇所 × 3 試行）をした
- [ ] 全滅なら失敗種別の分布から次の一手を決めた（[24 §6](../24_model_eval_campaign.md#6-選別の基準)）
- [ ] 作業レポートに S- セッションで追記した
