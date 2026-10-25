# 22 — Newton Kamino シミュレーション（GPU 動力学）

Newton（NVIDIA）の **Kamino ソルバ**で SO-101 の**動力学シミュレーション**を GPU 上で回す環境。
[12 MuJoCo sim](12_mujoco_sim.md) が姿勢を置いて `mj_forward` する**運動学**チェックなのに対し、
こちらは **重力・接触・PD サーボ**を刻み積分する。実機・USB・カメラは不要（Pi ではなく
**メイン PC（GPU）**で動かす。LeLab / Web Remote と同時起動してよい）。

| 項目 | 内容 |
|------|------|
| シーン（MJCF） | [`assets/robots/so101/sim/so101_scene.xml`](../assets/robots/so101/sim/so101_scene.xml) — 12 と共用 |
| スクリプト | [`scripts/kamino_check.py`](../scripts/kamino_check.py) |
| 環境（uv group `sim`） | `newton>=1.7.0` + `trimesh` + `scipy`（[`pyproject.toml`](../pyproject.toml)） |
| 動作確認機材 | RTX 4090 / WSL2 / Python 3.12 |
| 出典 | Kamino は Disney Research・NVIDIA・Google DeepMind による Proximal-ADMM ソルバ（[論文](../learn/papers.md)） |

シミュの使い分け: **12 MuJoCo**（運動学・干渉・Pi でも可） → **22 Kamino**（GPU 動力学・多数世界並列） →
**Isaac Lab**（[08](08_quest_isaacteleop.md) の高精度・学習向け）。

## セットアップ（初回のみ・uv）

```bash
# so101-lab リポジトリ直下で実行
uv sync --group sim        # newton + warp-lang + trimesh + scipy
```

- pip で入れる場合は `pip install newton`（旧名 `newton-physics` は**改名済みの空スタブ**なので注意）。
- GPU ドライバは通常の手順どおり。CUDA Toolkit は warp が内蔵 PTX から JIT コンパイルするので
  ローカルインストール不要（初回のみカーネルコンパイルで数分かかる）。
  カーネルキャッシュは `~/.cache/warp/`。
- このグループを sync すると docs グループのパッケージは一度外れる。
  ドキュメント配信に戻るときは `make docs-sync` で入れ直す（相互運害なし）。

## クイックスタート

```bash
# ホーム姿勢の重力保持チェック（PD サーボで直立を保てるか）
make sim-kamino                                    # = uv sync --group sim && uv run --group sim python scripts/kamino_check.py
uv run --group sim python scripts/kamino_check.py --sweep          # 全関節 0.5 Hz 正弦掃引
uv run --group sim python scripts/kamino_check.py --pose "0,-40,-20,-40,0,20"   # 姿勢保持（deg）
uv run --group sim python scripts/kamino_check.py --worlds 8        # 8 世界並列（GPU バッチ）
uv run --group sim python scripts/kamino_check.py --no-collide      # 衝突なし（高速）
```

関節の並び・角度の意味は [12](12_mujoco_sim.md) と同一
（`shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper`・deg・ホーム=0）。
exit code: `0`=OK / `1`=保持偏差しきい値超過 / `2`=エラー。

## 実測（2026-10・RTX 4090・WSL2）

| 条件 | 速度 | 備考 |
|------|------|------|
| worlds=1・衝突あり | **231 steps/s**（dt=0.005 で等速 1.16 倍） | グラフキャプチャあり |
| worlds=8・衝突あり | **210 steps/s**（実質 1,680 world-steps/s） | 8 並列でもほぼ減速しない = GPU バッチの本領 |
| グラフキャプチャなし | 5〜7 steps/s | カーネル launch 律速。キャプチャで約 30 倍 |
| ホーム姿勢保持 | 最大偏差 0.03° | PD（kp=998.22）で直立 |
| `--pose "0,-40,-20,-40,0,20"` | shoulder_lift に 6.7° の定常たわみ | 腕を水平に伸ばす姿勢は重力モーメントが最大。たわみ ≈ モーメント/kp で**物理的に妥当**（実機の STS3215 も同様にたわむ）。チェックのしきい値は `--tol-deg` |

## 何をしているか

1. **モデル取り込み** — `SolverKamino.register_custom_attributes(builder)` のあと
   `builder.add_mjcf("so101_scene.xml", parse_visuals=False, enable_self_collisions=False)`。
   位置サーボ `kp=998.22 / kv=2.731` は MJCF の `<position>` から
   `joint_target_ke/kd` に**自動取り込み**される（手書き不要）。
2. **自己衝突は既定 OFF** — 現行 `add_mjcf` は MuJoCo の「親子ジオム除外」を再現しない。
   既定のままだと隣接リンクの衝突 box 同士が常時接触して 30 倍遅くなり、物理も押し合う。
   `--self-collide` でオンに戻せる（arm↔机・床の接触は常に有効）。
3. **ソルバ設定** — `SolverKamino.Config.from_model()` をベースに
   衝突検出は `pipeline="unified"`（グリッパの STL メッシュ衝突のため。box/sphere だけでも
   `primitive` は ValueError を出すので基本 unified）、
   `max_contacts_per_world=512`（グリッパ微小 geom 多数で推定容量を超えると
   "contact capacity exceeded" 警告 + 接触欠落）。
4. **CUDA グラフキャプチャ** — ウォームアップ 3 ステップ後、1 ステップを
   `wp.ScopedCapture()` で捕まえ、以降は `wp.capture_launch(graph)` で再生。
   制御目標はデバイス配列の中身を書き換えるので、グラフ再生中でも反映される。
5. **積分** — `solver.step(state0, state1, control, contacts, dt)` を交換しながらループ。

## ハマりどころ

| 症状 | 原因と対処 |
|------|-----------|
| `pip install newton-physics` で中身がない | `newton` に改名済み（1.0.0 はスタブ） |
| `ValueError: shape '1' not supported by the primitive broad-phase` | `collision_detector.pipeline="unified"` を指定 |
| `Warning: per-world contact capacity exceeded` | `collision_detector.max_contacts_per_world` を 512 程度に |
| `ModuleNotFoundError: trimesh / scipy` | sim グループに同梱済み。単体 pip の人は `pip install trimesh scipy` |
| グラフキャプチャが失敗する | `wp.config.verify_cuda=True` のときは無効。スクリプトは自動フォールバック |
| 遅い（数 steps/s） | グラフキャプチャが効いていない / 自己衝突がオン。上記 3.-4. を確認 |

## 注意・ステータス

- Kamino は **BETA 1**。Newton 公式が「依存を推奨しない」と明記（安定版 BETA 2 は 2026 夏予定）。
  `newton` のバージョンを上げると API が変わる可能性がある。`uv lock --upgrade-package newton`
  の後は `uv run --group sim python scripts/kamino_check.py` のスモークを必ず回す。
- 現行インポータの既知の非互換（親子ジオム除外なし・contype/conaffinity 未解釈）により、
  MuJoCo 版 [12](12_mujoco_sim.md) と**接触判定は厳密一致しない**。干渉チェックの正本は引き続き 12。

## 今後の拡張（未実装）

- RL 学習用の並列環境化（`--worlds N` の観測をそのままバッファに。sim2rl [02_rl](../../../sim2rl/docs/learn/02_rl/README.md) との接続）
- テレオペ指令のシミュ事前ゲート（12 の将来項目と共通。接触力を observable で取得可能）
- 双腕シーン（`add_world` に左腕 builder を追加するだけで同じ枠組で載る見込み）
