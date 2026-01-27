<div align="center">
  <a href="./README.md">
    <img src="https://img.shields.io/badge/🇺🇸_English-2980b9" alt="English">
  </a>
  &nbsp;
  <a href="./README-zh.md">
    <img src="https://img.shields.io/badge/🇨🇳_简体中文-d35400" alt="简体中文">
  </a>
</div>


# EVA Mobile - Example App for EVA OS mobile appliation 

[![React Native](https://img.shields.io/badge/React_Native-0.81.4-blue.svg)](https://reactnative.dev/)
[![Expo](https://img.shields.io/badge/Expo-54-black.svg)](https://expo.dev/)
[![EVA OS](https://img.shields.io/badge/Powered_by-EVA_OS-purple.svg)](https://github.com/autoark)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**EVA Mobile** is the official open-source mobile client example for **EVA OS**, designed to demonstrate the powerful **real-time multimodal LM** AI capabilities of EVA OS.

As an open source implementation, this project shows how to effortlessly integrate a mobile application (built with React Native) with EVA OS to provide a low-latency, highly interactive AI experience.

---

## 🔌 Usage Overview

This project demonstrates how the client integrates with **LiveKit**, the real-time audio/video service used by EVA OS.  
Below is the standard usage flow:

### 1. Obtain Service Credentials (API Key & Token)

Before connecting to LiveKit, complete the authentication flow:

1. **Get your API Key**  
   Go to [EVA Console](https://eva.autoarkai.com), create a **Solution**, and obtain the API Key from its detail page.

2. **Request a Room Token**  
   Clients **cannot** connect directly with the API Key.  
   You must send a request to EVA OS server, by using the EVA API key obtained before. Then you will get a **time-limited Room Token**.

---

### 2. Standard Connection Sequence

LiveKit clients follow a token-based authentication pattern.  
Regardless of your client framework, the flow remains the same:

1. **Request Token**  
   Client → EVA OS (EVA API) → returns Room Token.

2. **Establish Connection**  
   Client initializes a connection using:
   - **WebSocket URL** (e.g., `wss://rtc.autoarkai.com`)
   - **Room Token** (JWT from step 1)

3. **Publish & Subscribe**  
   Once connected, the client joins the room, publishes local mic/camera streams, and subscribes to the AI model’s audio/video interactive streams.

---

### 3. Reference Implementation

We provide a utility class `EvaClient` (in `lib/eva-client.ts`) that simplifies token retrieval.  
Below is the core logic:

```typescript
// lib/eva-client.ts 
import axios from 'axios';

export class EvaClient {
  constructor(
    public baseUrl: string, // should be https://eva.autoarkai.com`
    public wssUrl: string, // should be wss://rtc.autoarkai.com
    public apiKey: string
  ) {}

  // Exchange API Key for Room Token
  async getRoom() {
    const response = await axios.post(`${this.baseUrl}/api/solution/chat-room`, {}, {
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
      },
    });
    return response.data.data; // returns { roomId, roomToken }
  }
}
```

Usage in a React component:

```tsx
import { LiveKitRoom } from '@livekit/react-native';
import { EvaClient } from './lib/eva-client';
import { useState, useEffect } from 'react';

export default function RoomConnect() {
  const [token, setToken] = useState("");
  
  // demo config
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

## 🚀 Getting Started

### 1. Prerequisites

Ensure your development environment includes:
	- [Node.js](https://nodejs.org/) & [pnpm](https://pnpm.io/)
  - **iOS**: Xcode (macOS only)
	- **Android**: Android Studio

💡 For detailed setup steps (Android SDK, CocoaPods, device configs), see the React Native docs:
https://reactnative.dev/docs/environment-setup

⸻

### 2. Clone & Install
```bash
git clone https://github.com/AutoArk/EVA-OS.git
cd eva-mobile
pnpm install
```

### 3. Environment Variables
Create a .env file at the project root (./eva-mobile):
```bash
# .env

# Required: EVA service API base URL
EXPO_PUBLIC_BASE_URL=https://eva.autoarkai.com

# Required: LiveKit WebSocket URL
EXPO_PUBLIC_WSS_URL=wss://rtc.autoarkai.com
```

### 4. Run the App

Because this project uses native modules (WebRTC, Audio, Camera),
you must build an Expo Development Build — Expo Go will NOT work.

#### iOS
```bash
pnpm ios
```

#### Android
```bash
# First, generate the debug keystore file and place it in /android/app
keytool -genkey -v -keystore debug.keystore -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000

# Start Android emulator or real device
pnpm android
```

##### Generate Keystore Signing File (Optional)

If you need to build a release version, you need to generate a `.keystore` signing file. For detailed steps, please refer to the official documentation: [React Native - Signed APK Android](https://reactnative.dev/docs/signed-apk-android).

Example to generate a key:

```bash
# macOS
sudo keytool -genkey -v -keystore my-upload-key.keystore -alias my-key-alias -keyalg RSA -keysize 2048 -validity 10000

# Windows
keytool -genkeypair -v -storetype PKCS12 -keystore my-upload-key.keystore -alias my-key-alias -keyalg RSA -keysize 2048 -validity 10000
```

## Tech Stack
- **Framework**: [React Native](https://reactnative.dev/) + [Expo](https://expo.dev/)
- **Real-time Communication**: WebRTC / [LiveKit](https://livekit.io/)
- **UI**: [NativeWind](https://www.nativewind.dev/) / [react-native-reusables](https://reactnativereusables.com/)

⸻

## 🤝 Contributing & Support

Issues and Pull Requests are welcome.
To obtain an EVA service API Key or for commercial inquiries, visit our website or contact the EVA team.

⸻

## 📄 License
EVA OS is released under the MIT License.

This means you are free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software, as long as you include the original copyright and permission notice in any copies or substantial portions.