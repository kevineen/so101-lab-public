# SO-ARM100 / SO-101 robot assets

- **Upstream project**: [TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100)
  (open-source 3D-printed robot arm designed for the LeRobot ecosystem)
- **Upstream commit**: `5f6d2b876a53a4872e405b991dd925556c9e38a4`
- **Source files**: `Simulation/SO101/so101_new_calib.urdf` and `Simulation/SO101/assets/*.stl`
- **License**: Apache License 2.0 — full text in [`LICENSE.upstream`](LICENSE.upstream)
- **Lab copy**: Vendored under `so101-lab/assets/robots/so101/` for Quest relative-EE IK
  (same layout as the laboratory `sim2rl` checkout).

## MuJoCo シーン（sim/so101_scene.xml）

- **Upstream project**: [SinfonIAUniandes/lerobot_robot_so101_mujoco](https://github.com/SinfonIAUniandes/lerobot_robot_so101_mujoco)
  （`robotstudio_so101/so101.xml` — robot-studio 由来の MJCF。SO-101 本体・慣性・
  サーボゲイン・グリッパー衝突ジオメトリを含む）
- **License**: Apache License 2.0（同上）
- **追加ファイル**（`meshes/` に取り込み）:
  `ArduCam_M12Lens.stl`, `moving_jaw_so101_gripper_part0_v1.stl`,
  `moving_jaw_so101_gripper_part1_v1.stl`, `wrist_roll_follower_so101_gripper_part0_v1.stl`,
  `wrist_roll_follower_so101_camera_mount.stl`
- **Local modifications**: `meshdir` を `../meshes` へ変更、机・床・障害物（mocap box）・
  固定カメラ・ホームキーフレームを追加、衝突 geom に名前付け
  （`shoulder_servo_box` 等）。アーム本体の tree・慣性・レンジは無変更。

## Local modifications (URDF)

- URDF renamed to `so101.urdf`; mesh references rewritten from
  `filename="assets/<name>.stl"` to `filename="meshes/<name>.stl"`
  (geometry files moved into the `meshes/` directory). No geometric or
  kinematic changes were made.

## Regenerating / updating

```bash
git clone --depth 1 https://github.com/TheRobotStudio/SO-ARM100.git /tmp/SO-ARM100
cp /tmp/SO-ARM100/Simulation/SO101/so101_new_calib.urdf  assets/robots/so101/so101.urdf
cp /tmp/SO-ARM100/Simulation/SO101/assets/*.stl          assets/robots/so101/meshes/
sed -i 's|filename="assets/|filename="meshes/|g' assets/robots/so101/so101.urdf
```

Then update the commit hash recorded above.
