# Agent 指示メモ — reports / TODO 運用

Cursor Agent（および人間）が **提出用レポートと残リストを壊さず更新する**ための手順書。  
ユーザーが「TODO を進めて」「レポート更新」「提出準備」と言ったら、まず本ファイルと [TODO.md](TODO.md) を読む。

**マルチホスト（どの PC で何をするか・SSH・rsync）** のときは先に  
[`configs/lab_hosts.yaml`](../../configs/lab_hosts.yaml.example) を読む（無ければ `.example` をコピーして設定。Cursor ルール `lab-hosts`）。

---

## 1. 役割分担（何を触るか）

| パス | 役割 | Agent がやること |
|------|------|------------------|
| [TODO.md](TODO.md) | 残リスト正本 | 着手・完了・blocked のステータス更新、サマリ表の数合わせ |
| [sim2rl_work_report.md](sim2rl_work_report.md) 等 | 提出用本文 | 事実（数値・パス・SHA）のみ追記。推測で埋めない |
| [design_notes.md](design_notes.md) | **工夫 / 失敗** | 判断・ネガティブ結果をエントリ化。`refs` 必須 |
| [references.md](references.md) | **リンク・ライセンス正本** | 外部依存を ID 登録（url + license 必須） |
| [README.md](README.md) | 索引・更新ルール | 新規レポート追加時のみ表を更新 |
| `~/robot/sim2rl/benchmarks/` · `runs/` · `docs/` | **一次情報** | 実験結果はここに書き、レポートは要約＋リンク |
| `~/robot/so101-lab/reports/`（リポ直下） | 旧メモ | **新規は書かない**（docs/reports を使う） |

数値の正本は常に sim2rl 側。本フォルダは「提出用の物語・判断ログ・引用／ライセンス」。

---

## 2. 標準ワークフロー（1 TODO = 1 サイクル）

```
1. TODO.md から 1 件選ぶ（ユーザー指定が無ければ P0 の open 先頭）
2. status → in_progress、owner に agent またはユーザー名、notes に開始日
3. where のリポで do を実行（長時間学習はユーザー確認を取ってから）
4. evidence パスが実在することを確認（ls / ファイル先頭を読む）
5. 指定の report 節を更新し、レポートの「版」と改訂履歴を 1 行追加
6. 【必須】新しい外部依存があれば references.md に ID 追加（url + license）
7. 【推奨→実質必須】工夫や失敗があれば design_notes.md に D-/F- エントリ
   （refs に references の ID を1つ以上。空 refs 禁止）
8. TODO を done にし、完了済みセクションへ移動（または status=done のまま一覧に残す）
9. TODO サマリ表の件数を数え直す
10. ユーザーに: 完了 ID / evidence / レポート版 / design_notes ID / refs ID / 次候補
```

**並列禁止の目安**: 同じレポート節を触る TODO は直列。独立な計測同士は並列可。

---

## 3. やってよいこと / 禁止

### よい

- TODO の `do` に書かれたコマンドの実行（短時間・CPU/既存 GPU スモーク）
- `benchmarks/*/benchmark.md` · `parity.md` · `eval_report.json` の要約をレポートへ転記
- 改訂履歴・チェックリスト `[x]`・サマリ表の更新
- 新規レポートファイルの追加（README 表も更新）
- blocked 解除条件が満たされたら `open` に戻す

### 禁止（先にユーザー確認）

- **商用利用が制限・不明な資産（MCR 重み・DINOv3 系重み等）に依存する設計・実装の開始**（ゲート正本: `~/robot/AGENTS.md` 商用利用ゲート）
- **長時間 GPU 学習**（≥50k steps や Colab 課金）を黙って開始
- 実機 SO-101 のトルク ON・テレオペ本番（安全・独占ルールあり → `docs/07` `11`）
- git commit / push（ユーザーが明示したときだけ。既存の committing ルールに従う）
- 一次情報（csv/json）を消す・上書きせずに「見た目だけ」レポート数値を捏造
- dirty ツリーの SHA を「クリーン再現」と書いて提出用に使う
- **参考文献 URL なし・ライセンス欄なし**で外部成果をレポート／design_notes に書く
- 失敗を握りつぶして成功だけレポートする（ネガティブは `design_notes.md` の F- へ）

---

## 4. ユーザー発話 → Agent の動き

| ユーザーが言うこと | Agent がすること |
|--------------------|------------------|
| 「TODO 見せて」「残リスト」 | `TODO.md` の open/P0 を短く要約。詳細はファイルを指す |
| 「次やって」「P0 進めて」 | T-P0-01 から順に 1 件。長時間なら確認してから |
| 「T-P0-02 やって」 | 当該 ID のみ。ワークフロー完走（refs / design_notes 含む） |
| 「レポート更新して」 | 直近の evidence / git log と TODO done を照合し、未反映なら追記 |
| 「提出準備」 | T-P0-03 + レポート §8 + [references.md](references.md) 提出前チェック |
| 「TODO 追加: …」 | 末尾テンプレで ID 採番（同優先度の最大 NN+1）。サマリ更新 |
| 「これは後回し」 | `deferred` + notes に理由 |
| 「工夫した点を書いて」「失敗も残して」 | [design_notes.md](design_notes.md) に D-/F-。先に references 登録 |
| 「参考文献 / ライセンス追加」 | [references.md](references.md) に ID。url + license 必須 |

---

## 5. レポート追記の型（コピペ用）

事実節に足すときは最低この 4 点:

```markdown
- **いつ**: YYYY-MM-DD
- **どこ**: `benchmarks/<dir>/` または `runs/<dir>/`
- **git**: `<short-sha>`（dirty なら明記）
- **数字**: 指標名と値（単位つき）。n（episodes/seeds）も書く
```

版上げ例（レポート先頭）:

```markdown
| 版 | **v0.2** |
| 最終更新 | 2026-10-16 |
```

改訂履歴に 1 行:

```markdown
| v0.2 | 2026-10-16 | T-P0-01: 200k reach ベンチを主結果に。20k は付録へ |
```

---

## 6. プロンプト例（ユーザーが Agent に貼る用）

### 残リストから 1 件消化

```
docs/reports/AGENT.md と TODO.md に従い、P0 の open 先頭を 1 件だけ進めて。
長時間 GPU が必要なら実行前に確認して。完了後 TODO と sim2rl_work_report を更新し、
evidence パスを報告して。
```

### 提出チェックだけ

```
docs/reports/AGENT.md の提出準備フローで、
sim2rl_work_report.md §8 と TODO の P0 を照合し、足りないものだけリストアップして。
まだ学習は回さない。
```

### 新規 TODO 追加

```
docs/reports/TODO.md に P1 で追加して:
（目的・コマンド案・期待成果物を書く）
AGENT.md のテンプレに合わせ、サマリ表も更新。
```

### 工夫・失敗・引用を追記

```
docs/reports/AGENT.md §9 に従い、次の内容を design_notes.md と references.md に追加して。
参考文献は URL とライセンス必須。refs 空欄禁止。
（内容を書く）
```

---

## 7. Cursor への常設

手順の正本は本ファイル。ルールはリンクのみ（二重管理しない）。

| 場所 | 用途 |
|------|------|
| `so101-lab/.cursor/rules/reports-todo.mdc` | ラボを単体ワークスペースにしたとき |
| `~/.cursor/rules/reports-todo.mdc` | ホーム（`$HOME`）ワークスペース用 |

ルールを変えるときは **本 AGENT.md を先に直し**、`.mdc` は要約の同期だけにする。

---

## 8. 完了報告の型（Agent → ユーザー）

```
完了: T-P0-0x — <タイトル>
evidence: <path>
report: sim2rl_work_report v0.x §…
design_notes: D-… / F-…（無ければ「判断変更なし」）
references: R-…（新規が無ければ「追加なし」）
TODO: open P0 残り N 件。次候補: T-…
```

長文の作業日誌はレポート本体に書かず、design_notes / TODO notes / 改訂履歴に残す。

---

## 9. 引用・ライセンス・工夫／失敗（必須ポリシー）

### 9.1 references.md

- 論文・GitHub・データ・モデル・ロボット資産・SDK を **名前で触れたら** ID を登録する。
- 各 ID に **`url`（必須）** と **`license`（必須）**。不明は `unknown（要確認）` とし提出前に潰す。
- 論文のみ参照でコードを使っていない場合: `license: N/A (paper)` で可。
- 改変して使う資産: upstream URL + LICENSE 名 + ローカル `NOTICE.md` パス。

### 9.2 design_notes.md

- **工夫** → `D-YYYYMMDD-NN`（kind=`design`）
- **ダメだった** → `F-YYYYMMDD-NN`（kind=`failed` または `mixed`）
- フィールド `refs` に references の ID を **1 つ以上**（空禁止）
- 失敗は削除せず残す。後から「採用しなかった理由」として提出に使える

### 9.3 レポート本文との関係

- 本文は要約と ID リンク（例: 「詳細は design_notes `D-20261016-01`、出典 `R-PAPER-SGS`」）
- 参考文献一覧のコピペ源は常に [references.md](references.md)
- 提出前チェックリストは references.md 末尾を実行する
