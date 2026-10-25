cd ~/robot/lerobot
# use vendor/lerobot/.venv



lerobot-record \
  --robot.config_file ~/robot/so101-lab/configs/so101_dual_cam.yaml \
  --fps 30 \
  --repo-id kevineen/so101_test_data \
  --num-episodes 10 \
  --warmup-time-s 5