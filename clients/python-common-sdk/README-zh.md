# EVA OS Python 客户端 SDK 接入指南

本项目是连接硬件设备与 **EVA OS 实时多模态 AI 服务** 的官方 Python 参考实现。它展示了如何进行接口鉴权、建立超低延迟的长连接，并处理实时的双向音视频流。

更重要的是，这份说明书将引导你如何将定制硬件（无论是 PC 还是低功耗 IoT 设备）完美契合进 EVA OS V2 的**“云边协同 (Edge-Cloud Synergy)”**架构之中。

---

## 🏗 架构理念：云边协同与边端状态主权

在接入 SDK 之前，强烈建议您了解 EVA OS V2 的设计原则，我们称之为**“边端状态主权”**。

### 职责划分

**边端（您的硬件与本 SDK）**
硬件算力珍贵，因此边端必须保持专注和轻量。SDK 仅负责：
1. **流媒体传输：** 持续不断地推送麦克风阵列数据，并拉取扬声器音频。
2. **本地唤醒检测：** 在后台运行极低内存占用的 VOSK 模型，实现零延迟的唤醒词检测（如“你好方舟”）。
3. **状态请求：** 边端**绝对不做** VAD（静音断句检测）和意图分类。当捕获到唤醒词时，SDK 只是通过控制平面向云端发送一个 `TaskSwitchAdvice`（任务切换建议）信令。

**云端（EVA OS / Pipecat 引擎）**
云端作为中央大脑，拥有充足的算力，它持续接收音视频流并统筹复杂的业务逻辑：
1. **全局 VAD 与 ASR：** 判断用户何时说话结束，并将音频转为文本。
2. **意图理解与业务流转：** 执行复杂的工作流并响应用户请求。
3. **任务调度大权：** 云端是状态流转的最终决策者。它评估边端发来的切换建议，只有当云端根据上下文下发了 `TaskSwitchResult (approved=True)` 时，边端才会真正切入新的交互任务。

这种握手机制确保了您的物理设备与云端数字大脑的状态（通过 RTVI 协议）永远保持绝对同步。

---

## 🚀 快速入门

### 1. 安装系统依赖
本项目底层依赖 `PortAudio`。在安装 Python 依赖前，**必须**先安装系统级的开发库。

*   **Ubuntu / Debian (及树莓派/开发板等):**
    ```bash
    sudo apt-get update
    sudo apt-get install libportaudio2 portaudio19-dev
    ```
*   **macOS:**
    ```bash
    brew install portaudio
    ```

### 2. 配置环境
克隆代码并安装依赖：
```bash
python3 -m venv venv
source venv/bin/activate  
pip install -r requirements.txt
# 可选：如果需要摄像头画面，需安装 opencv
pip install opencv-python
```

在项目根目录创建 `.env` 文件：
```ini
# 从 EVA OS 后台创建应用获取的 Solution API Key
EVA_API_KEY=sk-your-api-key-here
```

### 3. 获取音频设备索引（极其重要！）
`PyAudio` 对音频通道极其敏感（例如尝试用音箱作为输入录音会导致 `Invalid number of channels` 报错）。
请务必运行设备扫描脚本：
```bash
python list_audio_devices.py
```
记下你真实麦克风和扬声器对应的 `Index` 数字，填入示例代码的 `mic_index` 和 `spk_index` 中。

### 4. 启动客户端
```bash
python python_example.py
```

---

## 🛠 高级场景与最佳实践

### 场景 A：选择合适的传输协议
SDK 提供了两套平行的参考实现，请根据您的硬件算力进行选择：

1. **`eva_client.py` (LiveKit / WebRTC):**
   *   **适用场景：** PC、Mac、树莓派 4 及以上等能跑完整 WebRTC 协议栈的设备。
   *   **优势：** 极致的低延迟、自适应 UDP 拥塞控制、抗弱网。这是**强烈推荐**的首选协议。
2. **`eva_ws_client.py` (原生 WebSocket):**
   *   **适用场景：** ESP32、MCU 等算力薄弱，跑不动 WebRTC 的低功耗设备。
   *   **优势：** 使用最基础的 WebSocket 裸传 Opus 数据包，极易用 C/C++ 移植到单片机上。

这两种协议底层共享同一套 RTVI 状态机控制平面，业务代码无需修改即可无缝切换。

### 场景 B：本地唤醒与意图无缝衔接
EVA OS V2 统一使用 **VOSK** 作为本地唤醒引擎（原生支持中英文，低 CPU 开销）。

在 `python_example.py` 中配置：
```python
client = EvaClient(
    # ...
    wake_word="你好方舟",                 # 要监听的唤醒词
    wake_word_target_task="intent_task",  # 唤醒后向云端请求切换到的任务分支
    on_task_change=on_task_change,        # 云端审批通过后的回调
)
```
**最佳实践：** 唤醒后**不要**在本地做任何麦克风静音或截断！请让用户自然、连贯地说话（例如：“你好方舟，播放儿歌”）。SDK 在后台捕获到唤醒词后会自动发起切换请求，而云端服务具备极强的容错理解能力，能够智能处理带有唤醒前缀的连续语音，您只需监听 `on_task_change` 事件即可。

### 场景 C：回声抑制与全双工打断 (Barge-in)
如果您的硬件没有内置硬件级的 AEC（声学回声消除）芯片，SDK 提供了基于音量的纯软件双工打断机制。

```python
    echo_suppression=True,
    barge_in_multiplier=1.5,
    barge_in_offset=500,
```
在常规情况下，当云端 AI 正在说话时，SDK 会抑制麦克风的上传以防止回声死循环。但如果用户大声说话（麦克风峰值 > AI音量峰值 * 1.5 + 500），SDK 将触发**强行打断 (Barge-in)**，允许用户在 AI 播报中途直接插话。

---

## 📚 接口参考字典

### EvaClient 与 EvaWebSocketClient 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :---: | :--- | :--- |
| **api_key** | `str` | **是** | 无 | EVA OS 颁发的 Solution API Key。 |
| **mic_index** | `int` | 否 | `0` | 麦克风的设备索引（通过扫描脚本获取）。 |
| **spk_index** | `int` | 否 | `0` | 扬声器的设备索引。 |
| **mic_sample_rate**| `int` | 否 | `48000` | 麦克风原生采样率。云端要求16kHz，SDK内部会自动做重采样。 |
| **spk_sample_rate**| `int` | 否 | `48000` | 扬声器原生采样率。 |
| **channels** | `int` | 否 | `1` | 通道数（1代表单声道）。 |
| **frame_duration_ms**| `int`| 否 | `60` | 每次打包发送的 Opus 音频帧长（毫秒）。 |
| **wake_word** | `str` | 否 | `None` | 要在后台监听的本地唤醒词。 |
| **wake_word_model_path**| `str` | 否 | `None` | 自定义 VOSK 模型路径。为 None 时会自动下载轻量级中文模型。 |
| **wake_word_target_task**| `str`| 否 | `None` | 命中唤醒词后，向云端申请切入的任务分支 ID。 |
| **on_task_change**| `callable`| 否| `None` | 当云端批准状态切换并下发确认后的回调函数。 |

### WebSocket 资源回收说明
如果您使用轻量级的 WebSocket 协议 (`eva_ws_client.py`)，在程序退出时必须通知云端释放资源。
SDK 内部已封装该逻辑，在优雅退出时会自动发起 `DELETE /api/solution/chat-room-ws` 请求（携带 `{session_id}`）断开连接。
