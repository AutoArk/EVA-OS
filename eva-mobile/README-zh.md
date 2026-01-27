<div align="center">
  <a href="./README.md">
    <img src="https://img.shields.io/badge/🇺🇸_English-2980b9" alt="English">
  </a>
  &nbsp;
  <a href="./README-zh.md">
    <img src="https://img.shields.io/badge/🇨🇳_简体中文-d35400" alt="简体中文">
  </a>
</div>


# EVA Mobile - EVA OS 多模态大模型手机端示例

[![React Native](https://img.shields.io/badge/React_Native-0.81.4-blue.svg)](https://reactnative.dev/)
[![Expo](https://img.shields.io/badge/Expo-54-black.svg)](https://expo.dev/)
[![EVA OS](https://img.shields.io/badge/Powered_by-EVA_OS-purple.svg)](https://github.com/autoark)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**EVA Mobile** 是 **EVA OS** 的官方移动端开源示例应用，专为展示 EVA OS 强大的**实时多模态大模型**能力而构建。

作为一个开源参考实现，本项目展示了如何将移动端应用（基于 React Native）无缝接入 EVA OS 服务，实现低延迟、高互动的 AI 体验。

## 🔌 连接流程详解

EVA OS通过WebRTC提供流式多模态AI服务。本项目演示了客户端如何与 **LiveKit** 实时音视频服务对接。以下是标准的对接流程说明：

### 1. 获取服务凭证 (API Key & Token)

在连接 LiveKit 之前，你需要完成身份认证流程：

1.  **获取 API Key**:
    前往 [EVA Console](https://eva.autoarkai.com) 创建一个 **Solution**，在 Solution 详情页中你将获得 API Key。

2.  **请求房间 Token**:
    客户端不能直接使用 API Key 连接。你需要向EVA服务器发起请求（调用 EVA 服务 API，使用上面获取的API KEY），得到一个**有时效性的房间 Token**（Room Token）。

### 2. 标准连接时序

客户端与 LiveKit 的连接遵循标准的 Token 认证机制。无论你使用何种客户端框架，流程均一致：

1.  **请求 Token**：
    客户端 -> EVA OS (EVA API) -> 返回 Room Token。

2.  **建立连接**：
    客户端使用获取到的 `Room Token` 和 LiveKit 服务器地址 (`WebSocket URL`) 初始化连接对象。
    
    *   **WebSocket URL**: 你的 LiveKit 实例地址（如 `wss://rtc.autoarkai.com`）。
    *   **Token**: 从步骤 1 获取的 JWT 字符串。

3.  **发布与订阅**：
    连接成功后，客户端即可加入房间（Room），发布本地的麦克风/摄像头流（Publish），并订阅 AI 模型的音视频流（Subscribe）。

### 3. 参考代码实现

我们提供了一个 `EvaClient` 工具类（位于 `lib/eva-client.ts`），用于简化 Token 的获取。以下展示了核心逻辑：

```typescript
// lib/eva-client.ts
import axios from 'axios';

export class EvaClient {
  constructor(
    public baseUrl: string, // should be https://eva.autoarkai.com
    public wssUrl: string, // should be wss://rtc.autoarkai.com
    public apiKey: string
  ) {}

  // 使用 API Key 获取 Room Token
  async getRoom() {
    const response = await axios.post(`${this.baseUrl}/api/solution/chat-room`, {}, {
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
      },
    });
    return response.data.data; // 返回 { roomId, roomToken }
  }
}
```

在 React 组件中使用：

```tsx
import { LiveKitRoom } from '@livekit/react-native';
import { EvaClient } from './lib/eva-client';
import { useState, useEffect } from 'react';

export default function RoomConnect() {
  const [token, setToken] = useState("");
  
  // 示例配置 (实际请使用环境变量)
  const client = new EvaClient(
    "https://eva.autoarkai.com",
    "wss://rtc.autoarkai.com",
    "YOUR_API_KEY"
  );

  useEffect(() => {
    const connect = async () => {
      const roomData = await client.getRoom();
      setToken(roomData.roomToken);
    };
    connect();
  }, []);

  if (!token) return null;

  return (
    <LiveKitRoom
      serverUrl={client.wssUrl}
      token={token}
      connect={true}
      audio={true}
      video={true}
    >
      <MyRoomView />
    </LiveKitRoom>
  );
}
```

## 🚀 快速开始

### 1. 环境准备

确保你的开发环境已安装：
- [Node.js](https://nodejs.org/) & [pnpm](https://pnpm.io/)
- **iOS**: Xcode (仅限 macOS)
- **Android**: Android Studio

> 💡 详细的环境配置步骤（如 Android SDK、CocoaPods 等），请参考 React Native 官方文档：[Setting up the development environment](https://reactnative.dev/docs/environment-setup)。

### 2. 获取代码与安装
```bash
git clone https://github.com/AutoArk/EVA-OS.git
cd eva-mobile
pnpm install
```

### 3. 配置环境变量

在项目根目录(./eva-mobile)下创建 `.env` 文件：

```bash
# .env

# 必填：你的 EVA 服务 API 地址
# 客户端将向此地址请求 Token
EXPO_PUBLIC_BASE_URL=https://eva.autoarkai.com

# 必填：LiveKit WebSocket 地址
# 请确保与 EVA 服务端配置的 LiveKit 实例一致
EXPO_PUBLIC_WSS_URL=wss://rtc.autoarkai.com
```

### 4. 运行应用

由于本项目依赖 Native Modules (WebRTC, Audio, Camera)，**必须构建 Development Build**，无法使用 Expo Go。

#### iOS 运行
```bash
# 启动 iOS 模拟器或真机
pnpm ios
```

#### Android 运行
```bash
# 先生成 debug keystore 文件, 放到 /android/app 下
keytool -genkey -v -keystore debug.keystore -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000

# 启动 Android 模拟器或真机
pnpm android
```

##### 生成 Keystore 签名文件 (可选)
如果你需要构建发布版本 (Release Build)，需生成 `.keystore` 签名文件。详细步骤请参考官方文档：[React Native - Signed APK Android](https://reactnative.dev/docs/signed-apk-android)。

生成密钥命令示例：

```bash
# macOS
sudo keytool -genkey -v -keystore my-upload-key.keystore -alias my-key-alias -keyalg RSA -keysize 2048 -validity 10000

# Windows
keytool -genkeypair -v -storetype PKCS12 -keystore my-upload-key.keystore -alias my-key-alias -keyalg RSA -keysize 2048 -validity 10000
```

## 🛠 技术栈

- **框架**: [React Native](https://reactnative.dev/) + [Expo](https://expo.dev/)
- **实时通信**: WebRTC / [LiveKit](https://livekit.io/)
- **UI**: [NativeWind](https://www.nativewind.dev/) / [react-native-reusables](https://reactnativereusables.com/)

## 🤝 贡献与支持

欢迎提交 Issue 或 Pull Request。如需获取 EVA 服务 API Key 或商业支持，请访问我们的官网或联系EVA团队。

## 📄 许可证
EVA OS is released under the MIT License.

This means you are free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software, as long as you include the original copyright and permission notice in any copies or substantial portions.
