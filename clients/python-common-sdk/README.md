# EVA OS Python Client

This project is the official Python reference implementation for connecting to the EVA OS Real-Time Multimodal AI Service. It demonstrates how to authenticate via API, establish a WebRTC connection using LiveKit, and handle real-time bidirectional audio and video streams.

## Prerequisites

### System Dependencies
This project depends on the `PortAudio` library. You **must** install the system-level development headers before installing the Python `PyAudio` library.

*   **Ubuntu / Debian (and embedded systems like Rockchip/Raspberry Pi):**
    ```bash
    sudo apt-get update
    sudo apt-get install libportaudio2 portaudio19-dev
    ```

*   **macOS:**
    ```bash
    brew install portaudio
    ```

*   **Windows:**
    Typically, `pip` will automatically install pre-compiled binaries (Wheels).

### Python Environment
*   Python 3.11 or higher is required.

## Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone git@github.com:AutoArk/EVA-OS.git
    cd EVA-OS/clients/python-common-sdk
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install livekit requests pyaudio numpy python-dotenv opencv-python
    ```

## Configuration

Create a `.env` file in the project root directory.

```ini
# .env file
# Required: API Key
EVA_API_KEY=YOUR_ACTUAL_API_KEY_HERE
```

### EvaClient Parameter Details

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :---: | :--- | :--- |
| **api_key** | `str` | **Yes** | None | **Authentication Key**.<br>Credential used to access Eva API services. |
| **mic_index** | `int` | No | `0` | **Microphone Device Index**.<br>ID of the input device used for recording. `0` usually represents the system default microphone. |
| **spk_index** | `int` | No | `0` | **Speaker Device Index**.<br>ID of the output device used for playback. `0` usually represents the system default speaker. |
| **mic_sample_rate** | `int` | No | `48000` | **Microphone Sample Rate (Hz)**.<br>Sampling frequency for recording. Defaults to 48kHz. |
| **spk_sample_rate** | `int` | No | `48000` | **Speaker Sample Rate (Hz)**.<br>Sampling frequency for playback. Defaults to 48kHz. |
| **mic_channels** | `int` | No | `1` | **Microphone Channels**.<br>`1` for Mono, `2` for Stereo. |
| **spk_channels** | `int` | No | `1` | **Speaker Channels**.<br>`1` for Mono, `2` for Stereo. |
| **frame_size_ms** | `int` | No | `60` | **Audio Frame Duration (ms)**.<br>Time length of audio data blocks processed or transmitted per cycle. Affects latency and packet size. |
| **camera_index** | `int` | No | `0` | **Camera Device Index**.<br>Usually `0` represents the system default cameras. If multiple cameras exist, try sequentially. |
| **video_width** | `int` | No | `640` | **Video Width**.<br>Horizontal pixel count for camera capture. It is recommended not to set this too high on ARM devices. |
| **video_height** | `int` | No | `480` | **Video Height**.<br>Vertical pixel count for camera capture. |
| **video_fps** | `int` | No | `30` | **Video Frame Rate**.<br>Frames per second (FPS). Recommended to set to 15 or 20 on low-performance devices to reduce load. |
| **base_url** | `str` | No | `...` | **Eva API Address**.<br>Defaults to `https://eva.autoarkai.com`, used for standard HTTP requests. |
| **wss_url** | `str` | No | `...` | **WebSocket Address**.<br>Defaults to `wss://rtc.autoarkai.com`, used for real-time audio stream transmission. |

---

### How to Get Audio Device Indices
Since `PyAudio` is very sensitive to device indices, we provide a helper script to list currently available devices.

1.  Run the script:
    ```bash
    python list_audio_devices.py
    ```
2.  Find the corresponding `Index` number and pass it as an argument to `EvaClient`.

## Usage Guide

Run the main program:

```bash
python python_example.py
```

### Expected Behavior
1.  The client starts and initializes the audio system and camera.
2.  Requests an authentication Token and connects to the WebRTC room.
3.  Activates the specified microphone device and starts publishing the audio stream.
4.  Activates the specified camera device and starts publishing the video stream.
5.  Subscribes to audio streams in the room and plays them through the specified speaker device.

## Troubleshooting

*   **Installation of `pyaudio` failed (fatal error: portaudio.h: No such file):**
    This is due to missing system development libraries. Ensure you have run `sudo apt-get install portaudio19-dev`.

*   **`ValueError: DeviceIndexOutOfRange`:**
    The `mic_index` or `spk_index` does not exist. Please re-run `list_audio_devices.py` to confirm the index.

*   **Camera fails to open:**
    *   Check if OpenCV dependencies are missing.
    *   If device performance is insufficient, try lowering `video_width`, `video_height`, and `video_fps` in the code.
