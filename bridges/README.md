# bridges/

Isaac Teleop（メインPC）と SO-101（Pi）をつなぐ **アダプタ専用**の置き場。

## 実装

| パス | 状態 |
|------|------|
| [`isaacteleop_to_so101/`](isaacteleop_to_so101/) | **Phase D 最小実装**（WebSocket JSON・双腕 `left`/`right`） |

仕様の詳細は [docs/09_bridge_contract.md](../docs/09_bridge_contract.md)。  
起動: [`../scripts/start_bridge_receiver.sh`](../scripts/start_bridge_receiver.sh) / [`../scripts/start_bridge_sender_demo.sh`](../scripts/start_bridge_sender_demo.sh)。

## 方針

- このディレクトリに置くのは薄い変換・送受信だけ
- [NVIDIA/IsaacTeleop](https://github.com/NVIDIA/IsaacTeleop) や `vendor/lerobot` のコピーは置かない
- 稼働中は LeLab / Web Remote と同時起動しない（[docs/07_multi_host.md](../docs/07_multi_host.md)）

## 辿り方

| 知りたいこと | ドキュメント |
|--------------|--------------|
| どのマシンで何をするか | [docs/07_multi_host.md](../docs/07_multi_host.md) |
| Quest + Isaac Teleop 単体 | [docs/08_quest_isaacteleop.md](../docs/08_quest_isaacteleop.md) |
| メッセージ契約・安全動作 | [docs/09_bridge_contract.md](../docs/09_bridge_contract.md) |
| **通しの動作確認（Step 0〜4）** | [docs/11_quest_teleop_runbook.md](../docs/11_quest_teleop_runbook.md) |
| フェーズ全体 | [docs/roadmap.md](../docs/roadmap.md) |
