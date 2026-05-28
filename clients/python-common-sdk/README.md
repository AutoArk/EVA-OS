# EVA OS Python Client SDK

This project is the official Python reference implementation for connecting hardware devices to the **EVA OS Real-Time Multimodal AI Service**. It demonstrates how to authenticate, establish low-latency connections, and handle real-time bidirectional audio/video streams.

More importantly, this SDK serves as a definitive guide on how to integrate your custom hardware (from PCs to low-power IoT devices) into the EVA OS V2 **Edge-Cloud Synergy** architecture.

---

## 🏗 Architectural Philosophy: Edge-Cloud Synergy & Edge State Sovereignty

Before using this SDK, it is highly recommended to understand the design principles of EVA OS V2. We adopt an architecture called **"Edge State Sovereignty"**.

### The Division of Labor

**The Edge (Your Hardware & this SDK)**
Hardware resources are limited, so the edge should be highly focused. The SDK is only responsible for:
1. **Media Streaming:** Continuously pushing microphone audio and pulling speaker audio.
2. **Local Wake Word Detection:** Running a lightweight VOSK model locally to catch wake words (e.g., "Hello Ark") with zero latency.
3. **State Requests:** The edge **NEVER** processes VAD (Voice Activity Detection) or intent classification. When a wake word is detected, the SDK simply sends a `TaskSwitchAdvice` signal to the cloud, requesting an intent switch.

**The Cloud (EVA OS / Pipecat Engine)**
The cloud acts as the central brain. It continuously receives audio and handles:
1. **VAD & ASR:** Determining when the user stops speaking and converting speech to text.
2. **LLM Intent Understanding & Business Logic:** Executing complex workflows based on the user's intent.
3. **Task Orchestration:** The cloud is the final decision-maker. It evaluates the edge's `TaskSwitchAdvice`. Only when the cloud replies with a `TaskSwitchResult (approved=True)` will the edge truly transition to the new interaction task.

This ensures that the state of your hardware device and the cloud engine are always perfectly synchronized via the RTVI control protocol.

---

## 🚀 Quick Start

### 1. System Dependencies
This project depends on the `PortAudio` library. You **must** install the system-level development headers before installing the Python dependencies.

*   **Ubuntu / Debian (and embedded systems like Raspberry Pi):**
    ```bash
    sudo apt-get update
    sudo apt-get install libportaudio2 portaudio19-dev
    ```
*   **macOS:**
    ```bash
    brew install portaudio
    ```

### 2. Environment Setup
Clone the repository and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate  
pip install -r requirements.txt
# Optional: Install OpenCV if you need video capture
pip install opencv-python
```

Create a `.env` file in the project root:
```ini
# Your API Key generated from the EVA OS Dashboard
EVA_API_KEY=sk-your-api-key-here
```

### 3. Finding Your Audio Devices (Crucial!)
`PyAudio` is extremely sensitive to channel misconfigurations (e.g., trying to record from a speaker will result in an `Invalid number of channels` error). 
Run our helper script to find the correct `Index`:
```bash
python list_audio_devices.py
```
Note down the `Index` for your microphone and speaker, and use them to configure `mic_index` and `spk_index` in the example scripts.

### 4. Run the Client
```bash
python python_example.py
```

---

## 🛠 Advanced Scenarios & Best Practices

### Scenario A: Choosing the Right Transport Protocol
This SDK provides two reference implementations depending on your hardware's capabilities:

1. **`eva_client.py` (LiveKit / WebRTC):**
   *   **Use case:** PCs, Raspberry Pi 4+, or any device that can run a full WebRTC stack.
   *   **Pros:** Ultra-low latency, adaptive UDP bitrate, built-in network recovery. This is the **strongly recommended** protocol.
2. **`eva_ws_client.py` (Raw WebSocket):**
   *   **Use case:** Low-power MCUs (ESP32) or constrained environments where WebRTC is too heavy.
   *   **Pros:** Sends raw Opus frames over standard WebSocket. Easy to port to C/C++.

Both protocols share the exact same RTVI control plane. Your business logic doesn't need to change if you switch transports.

### Scenario B: Wake Word & Seamless Intent Handoff
EVA OS V2 uses **VOSK** as the unified local wake word engine (supports Chinese/English natively with low CPU footprint).

In `python_example.py`:
```python
client = EvaClient(
    # ...
    wake_word="你好方舟",                 # The wake word to listen for
    wake_word_target_task="intent_task",  # Request cloud to switch to this task
    on_task_change=on_task_change,        # Callback when cloud approves the switch
)
```
**Best Practice:** Do NOT attempt to mute the microphone after a wake word is detected. Speak naturally ("Hello Ark, play some music"). The local VOSK engine will flag the wake word and request a task switch silently in the background. The cloud service has excellent fault-tolerance and is designed to process continuous speech, intelligently understanding your intent. You simply need to listen for the `on_task_change` callback.

### Scenario C: Echo Suppression & Voice Barge-in (Full Duplex)
If your hardware lacks hardware-level AEC (Acoustic Echo Cancellation), the SDK provides a volume-based software suppression mechanism.

```python
    echo_suppression=True,
    barge_in_multiplier=1.5,
    barge_in_offset=500,
```
When the bot is speaking through the speaker, the microphone is normally suppressed to prevent echo loops. However, if the user speaks loudly enough (Mic Volume > Bot Volume * 1.5 + 500), the SDK triggers a **Barge-in**, allowing the user to forcefully interrupt the AI's playback.

---

## 📚 API Reference

### EvaClient & EvaWebSocketClient Parameters

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :---: | :--- | :--- |
| **api_key** | `str` | **Yes** | None | Your EVA OS Solution API Key. |
| **mic_index** | `int` | No | `0` | Microphone device ID (from `list_audio_devices.py`). |
| **spk_index** | `int` | No | `0` | Speaker device ID. |
| **mic_sample_rate**| `int` | No | `48000` | Native mic sample rate. Cloud expects 16kHz, SDK automatically resamples. |
| **spk_sample_rate**| `int` | No | `48000` | Native speaker sample rate. |
| **channels** | `int` | No | `1` | Audio channels (1=Mono, 2=Stereo). |
| **frame_duration_ms**| `int`| No | `60` | Opus audio frame duration. |
| **wake_word** | `str` | No | `None` | Local wake word to trigger VOSK background detection. |
| **wake_word_model_path**| `str` | No | `None` | Path to custom VOSK model. If None, auto-downloads a lightweight Chinese model. |
| **wake_word_target_task**| `str`| No | `None` | The task to request from the cloud when wake word hits. |
| **on_task_change**| `callable`| No| `None` | Hook triggered when the cloud approves a task switch. |

### WebSocket Disconnection Flow
If using the WebSocket transport (`eva_ws_client.py`), you must explicitly terminate the session to release cloud resources.
The SDK automatically sends a `DELETE /api/solution/chat-room-ws` request with your `{session_id}` upon graceful shutdown.
