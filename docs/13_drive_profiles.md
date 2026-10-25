# 13 — drive_profile（腕ごとの速度 / 加速度）と 12V 換装

Web Remote は両ポートをソフト上は `so101_follower` として位置制御しますが、**ハードの減速比・電源は腕ごとに違います**。  
過負荷を避ける暫定策として腕ごとに `drive_profile` を持ち、後から **12V follower へ換装**しても yaml の 1 行で切り替えられるようにしてあります。

設定正本: [`../configs/so101_dual_cam.yaml`](../configs/so101_dual_cam.yaml)  
実装: [`../web_remote/web_remote/drive_profile.py`](../web_remote/web_remote/drive_profile.py)

---

## 結論（先に読む）

| いまの運用 | やること |
|------------|----------|
| **片腕 IL（ACT / SmolVLA）を進める** | Web Remote は `leader_arm.enabled: false`。デモは手テレオペ → [14_single_arm_il.md](14_single_arm_il.md) |
| 物理 **leader** を第2駆動腕にしている | `leader_arm.drive_profile: gentle_7v4`（かつ `enabled: true`） |
| 第2腕を **本物の follower（できれば 12V）** に換装した | `leader_arm.enabled: true` + `drive_profile: full`（または `follower_12v`） |
| トルク不足をソフトだけで「定格アップ」したい | **できない**。遅い動きで過負荷しにくくするだけ |

**絶対にやらないこと:** 7.4V 向け leader モータに **12V 電源を入れない**（焼損）。

---

## なぜ leader は弱いのか

SO-101 公式の役割分担:

| | Follower（駆動） | Leader（手で動かす） |
|--|------------------|----------------------|
| 狙い | 位置制御・作業 | バックドライバブルなテレオペ |
| 肘など | 減速 **1:345** が多い | 肘は **1:191** など低減速 |
| 電源 | 7.4V 系、または **12V オプション** | **常に 7.4V 系（供給は 5V）** |
| 目安 stall | 〜19.5 kg·cm @7.4V / 〜30 @12V | 同電圧でもギア比で不利 |

Web Remote のタブ名 `leader` は「第2ポート」の意味で、ハードが leader のままだと **駆動腕としてはトルク不足 → Overload・ランプ点滅** になりやすいです。

---

## プロファイル一覧

| yaml の値 | 別名 | step（°/tick） | 体幹 Acceleration | 用途 |
|-----------|------|----------------|-------------------|------|
| `full` | `follower_12v`, `12v`, `follower_full` | RateRouter そのまま（cruise 30 / approach 12） | 変更しない（LeRobot 既定 ≈254） | 本物の follower。**12V 換装後もこれ** |
| `gentle_7v4` | `gentle`, `leader_gentle`, `leader_7v4_gentle` | ×0.4 かつ上限 8°（homing 上限 5°） | **変更しない**（保持力を落とさない） | 物理 leader を暫定駆動 |

### ゆっくり上げようとして落下するとき

Feetech の **Acceleration を下げると** 目標への追従が柔らかくなり、重力に負けて腕が落ちます。  
`gentle_7v4` は **指令の刻み（step）だけ小さく**し、サーボ加速度は既定のままにしています。

- それでも落ちる／上がらない → トルク不足（leader ギア）または Overload。12V follower 換装を検討  
- 肘が +90° 付近で `safe` が張り付く → 端押し込み／過負荷。ESTOP・電源リセット後、端を避けて動かす

腕名ごとのデフォルト（yaml に `drive_profile` が無いとき）:

- `follower` → `full`
- `leader` → `gentle_7v4`

### ソフトがやっていること

1. **制御ループ** — グローバルな RateRouter の step に、腕の `step_scale` / `max_step_deg` を掛ける（ここが「遅さ」の本体）  
2. **接続直後** — `body_acceleration` が設定されているプロファイルだけ Feetech Acceleration を書く（`gentle_7v4` は書かない）  
3. **go-home** — 同じプロファイルの homing 上限を使う  

定格トルクやギア比は変わりません。指令を刻んでピーク衝撃を下げます。**保持用に Acceleration は下げない**（落下の原因になる）。

---

## yaml 例（現行ラボ）

```yaml
robot:
  follower_arm:
    port: ${SO101_FOLLOWER_PORT}
    drive_profile: full
  leader_arm:
    enabled: true
    port: ${SO101_LEADER_PORT}
    drive_profile: gentle_7v4   # 暫定。換装後は full
```

変更後は **Web Remote を再起動**（設定は起動時に読む）。

確認:

```bash
# 起動ログに drive_profile=... が出る
./scripts/start_web_remote.sh

# または API
curl -s http://127.0.0.1:8765/api/info | python3 -m json.tool | head -80
# → drive_profiles.follower / drive_profiles.leader
```

---

## 12V follower への換装手順（第2腕）

ハードウェアを揃えてからソフトを切り替える。

### 1. ハード

1. 第2腕を **follower 仕様のモータ構成**にする（全関節 1:345 系が典型）  
2. 12V 版 STS3215（C018 / C047 等）を使うなら **12V 5A 以上の専用電源**  
3. 旧 leader（7.4V）用 5V 電源をその腕に繋いだままにしない  
4. USB by-id を確認し、yaml の `leader_arm.port` を合わせる  

### 2. キャリブ

モータ／組み立てが変わったら再キャリブ必須 → [04_calibration.md](04_calibration.md)

```bash
lerobot-calibrate \
  --robot.type=so101_follower \
  --robot.port=/dev/serial/by-id/<第2腕のby-id> \
  --robot.id=my_leader_drive
```

（id を変えるなら yaml / 起動引数の `--leader-id` も合わせる。）

### 3. プロファイル切替

```yaml
leader_arm:
  drive_profile: full          # または follower_12v
```

再起動後、`/api/info` の `drive_profiles.leader.name` が `full` であること。

### 4. 動作確認（短時間）

1. テレオペ ON・leader タブ  
2. 肘・肩をゆっくり端近くまで（無理に押し切らない）  
3. Overload / 点滅が無いか  
4. 問題なければ nest 保存 → [03_web_remote.md](03_web_remote.md)

---

## チューニング（必要なら）

プリセット定数は `web_remote/web_remote/drive_profile.py` の `DRIVE_PROFILES`。

| 字段 | 意味 |
|------|------|
| `step_scale` | RateRouter step への倍率 |
| `max_step_deg` | 追従の絶対上限（°/tick） |
| `homing_max_step_deg` | nest / go-home 時の上限 |
| `body_acceleration` | Feetech 1–254。小さいほど遅い。`None` で既定のまま |

新しいプリセットを足す場合は別名を `DRIVE_PROFILE_ALIASES` にも足し、本ドキュメントの表を更新する。

---

## トラブルシュート

| 症状 | 確認 |
|------|------|
| leader 肘 Overload・ランプ点滅 | [06_troubleshooting.md](06_troubleshooting.md)。まず ESTOP・電源リセット。`gentle_7v4` か確認 |
| 再起動しても速い | yaml のインデント / キー名。起動ログの `drive_profile=` |
| 換装後も遅い | まだ `gentle_7v4` のまま → `full` に変更して再起動 |
| 12V にしたら動かない / 異常発熱 | **電圧取り違え**を疑う。即電源オフ |

関連: [03_web_remote.md](03_web_remote.md) · [04_calibration.md](04_calibration.md) · [06_troubleshooting.md](06_troubleshooting.md) · [14_single_arm_il.md](14_single_arm_il.md)
