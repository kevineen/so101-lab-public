# 第4章レッスン1 — 新しい VLA / ポリシーをこのラボに載せるチェックリスト

> 🎯 **このレッスンのゴール**
> ①「新しいモデルを試したい」と思ったとき、何を順に確認すればよいか一覧できる
> ②観測キー・行動次元・キャリブ系の不一致が**学習前に**検出できる
> ③外部の重み・データを使うときのライセンス記録場所を言える

第4章 README の地図にないモデル（新発表の VLA・コミュニティ重みなど）を
載せるときの**一般手順**です。[10_molmoact2_thor.md](../../10_molmoact2_thor.md) で
MolmoAct2 向けに一度通してある内容を、モデル非依存の形にしたものです。

---

## 0. まず判断: 手を出すか（5 分）

| 質問 | 落ちたら |
|------|----------|
| 言語指示が必須か? | 否なら ACT / Diffusion で十分（[14](../../14_single_arm_il.md)） |
| 学習・推論の VRAM は 4090 / Thor に収まるか | 公式 README の推奨サイズと比較。載らないなら見送り |
| LeRobot 形式のチェックポイント（または学習コード）があるか | 無いと自前 adapter が必要。コストを先に見積もる |
| ライセンス・商用制限は? | [references.md](../../reports/references.md) に登録して確認。不明なら `unknown（要確認）` |

## 1. チェックポイントの事前確認（学習の前）

- [ ] 関節次元: このラボの片腕は **6**（follower）。双腕 12 の重みはそのまま使えない
- [ ] `control_mode`: `absolute joint pose` か。速度制御系なら変換層が要る
- [ ] カメラキー: 重みが読む `observation.images.*` の名前と数。**クライアント側の
      カメラキーを checkpoint に合わせる**（`rename_map` を渡せない構成のため）
- [ ] キャリブ系: 旧 SO-100/101 チェックポイントの `joint_signs` / `joint_offsets` は
      **先頭 6 関節のみ想定**。このラボの degree 系キャリブにその変換を付けない
      （[10 の「アームとキャリブレーション」節](../../10_molmoact2_thor.md)参照）
- [ ] dtype・推論モード: 例: `dtype=bfloat16` + `inference_action_mode=continuous`

## 2. サーバが受け付けるか（Thor）

- [ ] `~/robot/lerobot/src/lerobot/async_inference/constants.py` の `SUPPORTED_POLICIES` に
      モデル名があるか。**なければ両ホストの fork に追加**（編集は `kevineen/lerobot` 側。
      diffusion・smolvla・act 等は既定で含まれる）
- [ ] サーバは `PolicyClass.from_pretrained(パス)` しか呼ばないため、
      公開 Hub 名を直接開く経路が無い場合は LeRobot 形式へ変換/FT してから載せる

## 3. データと学習（FT するとき）

- [ ] 同じデータセット・同じ 10 試行評価プロトコル（[17 §5](../../17_act_record_train_infer.md)）で
      ACT と比較できる状態を作る（比較にならない条件では「試した」にならない）
- [ ] state / action の統計（quantile 等）がデータセットに無い場合は
      `augment_dataset_quantile_stats.py` を Thor で実行（[10](../../10_molmoact2_thor.md)）
- [ ] デモが少ないときは `train_mode_vlm=lora` / `freeze` + action expert は学習、等の
      公式の少データ設定を確認

## 4. 記録（載せたら必ず）

- [ ] [references.md](../../reports/references.md) に `R-` エントリ（url + license）
- [ ] 詰まった壁は [design_notes.md](../../reports/design_notes.md) に F- 候補として残す
      （SUPPORTED_POLICIES 編集のような「次の人が同じ壁に当たる」情報が最も価値がある）
- [ ] TODO に milestone を立て、作業レポートに S- セッションで評価を残す

---

## ✅ 理解度チェック

<details><summary>Q1. 公開された双腕用重みを、このラボの片腕 6 関節でそのまま推論できるか？</summary>

通常は否。関節次元・順序・カメラキーが一致しない。次元が合う自データでの FT か、
片腕用に公開された重み（例: MolmoAct2 の SO100/101 片腕版）を使う。
</details>

<details><summary>Q2. クライアント CLI は `rename_map` をサーバへ渡せない。カメラキーが重みと違うときどうする？</summary>

推論クライアント側のロボット定義でカメラキーを checkpoint の `observation.images.*` と
一致させる（サーバ側を変えない）。
</details>

<details><summary>Q3. 新しいモデルを async 推論サーバで動かそうとしたら `Policy type X not supported` で落ちた。直す場所は？</summary>

両ホストの `~/robot/lerobot`（fork `kevineen/lerobot`）の
`src/lerobot/async_inference/constants.py` の `SUPPORTED_POLICIES` に追加。
so101-lab 側のコミットではなく fork 側の変更。
</details>

⏭️ 次: [第5章 双腕への道](../05_bimanual/README.md)
