# 第6章 — 力覚観測IL（Present_Loadプロキシ）

> 🎯 **章のゴール**
> ①STS3215の`Present_Load`を読み、把持・接触の力覚proxyを`observation.state`へ混ぜて録画できる
> ②力覚チャネル付きACTを既存モデルとA/B比較する手順を説明できる
> ③このproxyの限界（較正なし・ノイジー・指令側には出せない）を挙げられる

## レッスン一覧

| # | レッスン | 内容 | 時間目安 |
|---|---|---|---|
| 1 | [01_present_load.md](01_present_load.md) | Present_Load読み→力覚観測付き録画→ACT比較 | 60分（録画除く） |

## この章の位置づけ

VFA（Vision-Force-Action）方式の実機側入門です。sim側（`sim2rl` の
`task=press` + 特権的Teacher-Student）は
[sim2rl learn 第7章](../../../sim2rl/docs/learn/07_sim2real/README.md)
で既に扱いました。実機SO-101には力覚センサーが無いため、ここでは
**サーボ内蔵の負荷推定値（Present_Load）を観測に混ぜる**という最小の
形で「力を観測する政策」に触れます。

```text
sim: MuJoCo接触力 → touch観測 → 力帯RL → 蒸留      (sim2rl 第7章 L4-L5)
実機: STS3215 Present_Load → state追記 → ACT再学習   (この章)
将来: 工具先端センサ（荷重セル等）→ 較正 → 同一経路   (センサ選定ドキュメント参照)
```

⏭️ まずは [01_present_load.md](01_present_load.md) から。
