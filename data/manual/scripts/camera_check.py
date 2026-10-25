import os

import numpy as np
import cv2
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from lerobot.cameras.realsense.camera_realsense import RealSenseCamera
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.opencv.camera_opencv import OpenCVCamera

# RealSense のシリアルは configs/lab.local.env の SO101_REALSENSE_SERIAL に置く
REALSENSE_SERIAL = os.environ.get("SO101_REALSENSE_SERIAL", "")

# 1. カメラ設定
config_hand = RealSenseCameraConfig(
    serial_number_or_name=REALSENSE_SERIAL,
    width=640, height=480, fps=30
)
config_front = OpenCVCameraConfig(
    index_or_path=6,
    width=640, height=480, fps=30
)

# 2. カメラオブジェクトの作成
cam_hand = RealSenseCamera(config_hand)
cam_front = OpenCVCamera(config_front)

# --- ここが重要：Webカメラの準備時間を5秒に延長 ---
cam_front.warmup_s = 5.0 

print("カメラに接続中 (Webカメラ -> RealSenseの順)...")

try:
    # 順番を入れ替えて、反応の遅いWebカメラを先に繋ぎます
    cam_front.connect()
    print("Webカメラ接続完了")
    
    cam_hand.connect()
    print("RealSense接続完了")

    print("画像をキャプチャ中...")
    img_front = cam_front.read()
    img_hand = cam_hand.read()

    # OpenCV用にBGR変換して保存
    cv2.imwrite("final_test_front.jpg", cv2.cvtColor(img_front, cv2.COLOR_RGB2BGR))
    cv2.imwrite("final_test_hand.jpg", cv2.cvtColor(img_hand, cv2.COLOR_RGB2BGR))
    
    print("成功！ 画像を保存しました。")

except Exception as e:
    print(f"エラーが発生しました: {e}")

finally:
    # disconnectは安全のため両方呼ぶ
    if hasattr(cam_hand, 'disconnect'): cam_hand.disconnect()
    if hasattr(cam_front, 'disconnect'): cam_front.disconnect()
    print("終了処理が完了しました。")

# config = RealSenseCameraConfig(
#     serial_number_or_name=os.environ["SO101_REALSENSE_SERIAL"],
#     fps=30,
#     width=640,
#     height=480,
#     use_depth=True
# )

# camera = RealSenseCamera(config)

# try:
#     camera.connect()
#     color_image = camera.read()
#     depth_image = camera.read_depth()

#     # --- 保存処理 ---
#     # RGBからBGRに変換（OpenCVはBGR形式のため）
#     color_bgr = cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR)
#     cv2.imwrite("color_test.jpg", color_bgr)
#     print("カラー画像を color_test.jpg として保存しました。")

#     # 深度画像を可視化用に変換（0-65535を0-255にスケーリング）
#     # 距離感が分かりやすいように色を付けます（ColorMap）
#     depth_normalized = cv2.normalize(depth_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
#     depth_colored = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)
#     cv2.imwrite("depth_test.jpg", depth_colored)
#     print("深度画像を depth_test.jpg として保存しました。")

# finally:
#     camera.disconnect()