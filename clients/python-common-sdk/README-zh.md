# EVA OS Python 客户端

本项目是连接 EVA OS 实时多模态 AI 服务的官方 Python 参考实现。它展示了如何通过 API 进行身份验证，使用 LiveKit 建立 WebRTC 连接，并处理实时的双向音视频流。

## 前置要求

### 系统依赖
本项目依赖 `PortAudio` 库。在安装 Python `PyAudio` 库之前，**必须**先安装系统级的开发头文件。

*   **Ubuntu / Debian (及 Rockchip/树莓派等嵌入式系统):**
    ```bash
    sudo apt-get update
    sudo apt-get install libportaudio2 portaudio19-dev
    ```

*   **macOS:**
    ```bash
    brew install portaudio
    ```

*   **Windows:**
    通常 `pip` 会自动安装预编译的二进制包（Wheels）。

### Python 环境
*   需要 Python 3.11 或更高版本。

## 安装步骤

1.  **克隆代码仓库:**
    ```bash
    git clone git@github.com:AutoArk/EVA-OS.git
    cd EVA-OS/clients/python-common-sdk
    ```

2.  **创建并激活虚拟环境 (推荐):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  
    ```

3.  **安装 Python 依赖:**
    ```bash
    pip install livekit requests pyaudio numpy python-dotenv opencv-python
    ```

## 配置说明

在项目根目录下创建一个 `.env` 文件。

```ini
# .env 文件
# 必填：API Key
EVA_API_KEY=YOUR_ACTUAL_API_KEY_HERE
```

### EvaClient 参数详细说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| **api_key** | `str` | **是** | 无 | **认证密钥**。<br>用于访问 Eva API 服务的凭证。 |
| **mic_index** | `int` | 否 | `0` | **麦克风设备索引**。<br>指定用于录音的输入设备 ID。`0` 通常代表系统默认麦克风。 |
| **spk_index** | `int` | 否 | `0` | **扬声器设备索引**。<br>指定用于播放音频的输出设备 ID。`0` 通常代表系统默认扬声器。 |
| **mic_sample_rate** | `int` | 否 | `48000` | **麦克风采样率 (Hz)**。<br>录音时的音频采样频率，默认为 48kHz 。 |
| **spk_sample_rate** | `int` | 否 | `48000` | **扬声器采样率 (Hz)**。<br>播放时的音频采样频率，默认为 48kHz。 |
| **mic_channels** | `int` | 否 | `1` | **麦克风通道数**。<br>`1` 表示单声道 (Mono)，`2` 表示立体声 (Stereo)。 |
| **spk_channels** | `int` | 否 | `1` | **扬声器通道数**。<br>`1` 表示单声道 (Mono)，`2` 表示立体声 (Stereo)。 |
| **frame_size_ms** | `int` | 否 | `60` | **音频帧时长 (毫秒)**。<br>每次处理或传输的音频数据块的时间长度。这会影响延迟和网络包的大小。 |
| **camera_index** | `int` | 否 | `0` | **摄像头设备索引**。<br>通常 `0` 对应默认系统摄像头。若有多个摄像头，请依序尝试。 |
| **video_width** | `int` | 否 | `640` | **视频宽度**。<br>摄像头捕获图像的水平像素数。ARM 设备建议不要设置过高。 |
| **video_height** | `int` | 否 | `480` | **视频高度**。<br>摄像头捕获图像的垂直像素数。 |
| **video_fps** | `int` | 否 | `30` | **视频帧率**。<br>每秒传输的帧数 (FPS)。在低性能设备上建议设为 15 或 20 以降低负载。 |
| **base_url** | `str` | 否 | `...` | **Eva API 地址**。<br>默认为 `https://eva.autoarkai.com`，用于常规 HTTP 请求。 |
| **wss_url** | `str` | 否 | `...` | **WebSocket 地址**。<br>默认为 `wss://rtc.autoarkai.com`，用于实时音频流传输。 |

---

### 如何获取音频设备索引
由于 `PyAudio` 对设备索引非常敏感，我们提供了一个辅助脚本来列出当前可用的设备。

1.  运行该脚本：
    ```bash
    python list_audio_devices.py
    ```
2.  找到对应的 `Index` 数字，作为入参传递给EvaClient。

## 使用指南

运行主程序：

```bash
python python_example.py
```

### 预期行为
1.  客户端启动并初始化音频系统和摄像头。
2.  请求认证 Token 并连接到 WebRTC 房间。
3.  激活指定的麦克风设备，开始推送音频流。
4.  激活指定的摄像头设备，开始推送视频流。
5.  订阅房间内的音频流，并通过指定的扬声器设备播放。

## 故障排除

*   **安装 `pyaudio` 失败 (fatal error: portaudio.h: No such file):**
    这是因为缺少系统开发库。请确保运行了 `sudo apt-get install portaudio19-dev`。

*   **`ValueError: DeviceIndexOutOfRange`:**
    `mic_index` 或 `spk_index` 不存在。请重新运行 `list_audio_devices.py` 确认索引。

*   **摄像头无法打开:**
    *   检查是否缺少 OpenCV 依赖。
    *   如果设备性能不足，尝试在代码中降低 `video_width`, `video_height` 和 `video_fps`。
