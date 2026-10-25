# 第5章 — 双腕への道（いまは地図）

> 🎯 **章のゴール**
> ①なぜ「今は片腕」なのかを説明できる
> ②双腕に進む前のハード条件を列挙できる
> ③sim2rl の双腕レベル分けとラボ文書の対応がわかる

**現状**: 物理 leader を第2 **駆動**腕にするとトルク不足 → 片腕 IL が主経路（第0・2章）。

---

## 5.1 進む前のチェックリスト（ハード）

- [ ] 第2腕を **follower 仕様**（できれば 12V + 専用電源）に換装  
- [ ] **7.4V leader モータに 12V を入れない**  
- [ ] 再キャリブ（`my_leader_drive` または bi 用 id）  
- [ ] yaml: `leader_arm.enabled: true` + `drive_profile: full`  

手順正本: [13_drive_profiles.md](../../13_drive_profiles.md)

---

## 5.2 ソフト側の二つの顔

| 経路 | ロボット型 | 文書 |
|------|------------|------|
| Web Remote 二臂駆動 | 両ポート `so101_follower` | [03](../../03_web_remote.md) · [13](../../13_drive_profiles.md) |
| MolmoAct2 双腕推論 | `bi_so_follower`（12 関節） | [10_molmoact2_thor.md](../../10_molmoact2_thor.md) |
| Quest ブリッジ | 契約 JSON → 左右 | [09](../../09_bridge_contract.md) · [11](../../11_quest_teleop_runbook.md) |

IL データも **録画時と推論時で同じロボット定義**にする（[10](../../10_molmoact2_thor.md) の注意）。

---

## 5.3 sim2rl 双腕レッスンとの対応

[sim2rl 09 — 双腕ロードマップ](../../../../sim2rl/docs/learn/09_advanced/02_dual_arm.md) の Level 1〜3:

| sim2rl Level | ラボでの近いもの |
|--------------|------------------|
| Level 1（2台独立） | 片腕ずつ別ポリシー・別実験（いまの主経路に近い） |
| Level 2（12 関節1ロボット） | `bi_so_follower` / MolmoAct2 双腕 |
| Level 3（協調タスク） | 将来。メイク・組立など |

シムで 12 関節の観測次元を先に紙に書いてから、実機の `left_*` / `right_*` キーに落とすと安心です。

---

## 5.4 学習順の再掲

```text
片腕 ACT → 片腕 SmolVLA →（任意）他 VLA 片腕スモーク
    → ハード換装 → 双腕キャリブ → 双腕データ → 双腕 VLA/ACT
```

焦って双腕データだけ先に取ると、トルク・キャリブ・カメラキーで詰まりやすいです。

---

## ✅ 理解度チェック

<details>
<summary>Q. いま `leader_arm.enabled: true` のまま ACT 双腕データを録るべきか？</summary>

駆動として leader を使うなら非推奨（トルク不足）。テレオペ用に手で動かすのは可だが、第2腕の **自律駆動データ**は換装後が安全。片腕データを先に資産化するのがラボ方針。
</details>

---

## カリキュラムの終わりに

お疲れさまです。次のアクション候補:

1. [T-P1-05](../../reports/TODO.md) — 片腕 ACT 通しの実測を残す  
2. sim2rl 第7章で Sim2Real チェックリストを読む  
3. 換装計画を [13](../../13_drive_profiles.md) に沿って部品リスト化  

索引に戻る: [learn/README.md](../README.md)
