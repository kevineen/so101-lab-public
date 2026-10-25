# 第6章レッスン1 — Present_Loadを観測へ混ぜて力覚付きACTを学ぶ

> 🎯 **このレッスンのゴール**
> ①`read_present_load=true` で何が`observation.state`に加わるか説明できる
> ②力覚チャネル付きデータセットを録画し、ACTをA/B比較する手順を回せる
> ③proxyの限界を挙げ、真の力覚センサー導入の判断材料を持つ

## 6.1-1 仕組み: サーボ電流負荷を力覚proxyにする

STS3215は内部で負荷推定値を常時計算しており、読み取り専用レジスタ
`Present_Load`（アドレス60、符号付き、およそ0.1%単位）として公開しています。
lerobotフォークの `so_follower` はこれを設定1つで観測へ混ぜられます
（`~/robot/lerobot` の `src/lerobot/robots/so_follower/`）:

```yaml
# Pi側の robot 設定（LeLabの--robot-configや録画コマンドの--robot-overrides）
read_present_load: true
```

有効にすると各フレームで `Present_Load` を全モータへ sync-read し
（追加バス読み出し1回 ≈ 1ms級。`max_relative_target` 利用時の追加読み出しと同種）、
観測辞書に `{motor}.load` スカラーが加わります。

**重要な設計**: このlerobotのデータセット経路では、スカラー観測は
**すべて `observation.state` へ統合**されます（位置の後に負荷の順）。
つまり `observation.state` は 6次元 → **12次元**（6関節角度 + 6負荷）になり、
ACT/Diffusion/SmolVLAは**コード変更なしに**この力覚チャネルを入力として
消費します。`read_present_load` を false のままなら従来の6次元のまま
（既存データセット・チェックポイントとの互換は完全に不変）。

## 6.1-2 実習: 録画→学習→A/B比較

録画は通常のテレオペ録画（[docs/14](../../14_single_arm_il.md) /
[docs/17](../../17_act_record_train_infer.md)）と同じ手順で、robot設定に
`read_present_load: true` を足すだけです。

```bash
# Pi（LeLab経由の場合は robot 設定ファイルを編集、またはCLIオーバーライド）
lerobot-record --robot.so101_follower.port=/dev/ttyACM0 \
  --robot.so101_follower.read_present_load=true \
  --dataset.repo-id=local/so101_pickup_load_v1 ...（カメラ等はdocs/14と同じ）
```

学習（GPUホスト、`scripts/train_mlflow.sh` 経由でMLflow記録を忘れずに）:

```bash
# 力覚なし（既存の比較対象。Cobraデータセット等）
./scripts/train_mlflow.sh --dataset local/<既存データセット> ... # 6次元state

# 力覚あり（今回録画した12次元stateデータセット）
./scripts/train_mlflow.sh --dataset local/so101_pickup_load_v1 ... # 12次元state
```

ACTは`observation.state`の次元をデータセットのメタデータから自動で拾うため、
学習設定の変更は不要です。評価は
[docs/24 モデル評価キャンペーン](../../24_model_eval_campaign.md)の10試行
プロトコルで既存4モデル（ACT front+wrist等）と並べてください。

**比較で見ること**:

| 観点 | 期待される効き目 |
|---|---|
| 把持の安定性（掴み直しの減少） | gripper負荷チャネルが「掴んだ/掴みそこね」の早期判定材料になる |
| 接触課題（押し付け・挿入っぽい動作） | 接触瞬間の各関節負荷上昇が状態に見える |
| 到達精度 | **変わらないはず**（自由空間では負荷≈重力分のみ） |

## 6.1-3 限界と先の道

- **較正なしの相対値**: `Present_Load` はN換算ではない。A/B比較や変化点検知には
  使えるが、simの力帯ゲート（0.5〜2N等）との直接対応は取れない
- **ノイジー**: サーボ内部推定はバス通信・温度でドリフトする。平滑化
  （EMA等）を入れるか、そのまま学習に任せるかはデータを見て判断
- **指令側には出せない**: 観測専用。力で動かす（インピーダンス的な挙動）には
  servoのゲイン・モード側の作業が別途必要
- **真の力覚へ**: 工具先端にひずみゲージ式荷重セル（HX711）やFSRを付け、
  電子秤で較正して同一の`{name}.load`経路に流す拡張が自然な次歩
  （sim側の`full_scale`較正の考え方と同じ。センサ候補の比較は
  `sim2rl/docs/sensor_selection.md` 参照）

### 理解度チェック

1. `read_present_load=true` のとき `observation.state` の次元と内容は？
2. この経路でACTのコードを変える必要が無いのはなぜか？
3. Present_Loadで「できないこと」を2つ挙げよ。
（答え: ①12次元 = 6関節角度（deg）+ 6モータ負荷（0.1%級の符号付き相対値）。
②スカラー観測はデータセット経路で`observation.state`へ統合され、ACTは
stateを丸ごと入力するため。③例: N換算・較正された絶対力の読み、力による
指令（観測専用）、sim力帯ゲートとの直接対応。）
