<div align="center">
  <br>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/SDK-TypeScript%20%7C%20Python-lightgrey?style=flat-square" alt="SDK">
  <img src="https://img.shields.io/badge/platform-Mobile%20%7C%20IoT%20%7C%20Embedded-lightgrey?style=flat-square" alt="Platform">
  <a href="https://github.com/AutoArk/EVA-OS/stargazers"><img src="https://img.shields.io/github/stars/AutoArk/EVA-OS?style=social" alt="Stars"></a>
</div>

# **EVA Platform - 实时多模态应用与硬件开发 AIOS**
<div align="center">
  <a href="https://eva.autoarkai.com">
    <img src="https://img.shields.io/badge/官方网站-访问_EVA_Platform-2980b9?style=flat-square" alt="EVA Platform 官方网站">
  </a>
  <br>
</div>

> Agent Skills · Device SDK · EVA CLI · Model Gateway · Edge AI
>
> 从一句需求到一个可运行的实时多模态应用，让 AI Agent 参与开发、管理云端资源，并将智能带到每一台设备。

![EVA Platform](https://github.com/user-attachments/assets/bae2c5f6-cc00-4c0a-a1a3-3ad875c726c0)

## **EVA Platform 全新上线**

**2026 年 7 月 30 日，EVA Platform 全新发布。**

EVA Platform 面向 AI 应用与智能硬件开发者，提供从 AI Native 开发、实时多模态交互、模型接入到项目管理的一体化开发体验。

在 EVA Platform，你可以：

- 借助eva skill，Vibe Coding 一句话开发音视频AI应用
- 使用模板和 Demo 快速启动项目，将想法更快变成可运行的产品
- 使用EVA SDK，轻松接入全双工音视频、情绪识别与设备指令下发等AI能力
- 使用 **EVA CLI** 管理项目、API Key 与云端资源
- 通过统一 **Model Gateway** 自由切换 ASR、TTS 与 LLM 模型
- 在一个平台内完成项目创建、用量管理、套餐升级和硬件接入

---

## **为什么选择 EVA Platform**

AI 正在改变应用的使用方式，也正在改变应用的开发方式。

我们希望开发者不再把时间消耗在重复搭建音视频链路、适配模型接口和管理分散的云端资源上，而是专注于产品体验本身。EVA Platform 将 Agent 开发能力、端侧运行时、模型服务与项目基础设施组合成一套统一平台，让开发者用更少的代码构建真正可交互、可执行、可部署的 AI 应用。

## **核心能力**

### **1. AI Native：让 Agent 成为你的开发搭档**

EVA Platform 为 AI 编程工具提供专用 **Agent Skills**。安装后，开发者可以直接用自然语言描述产品需求，让 Agent 理解 EVA 的能力、开发流程与最佳实践，并参与项目创建、代码开发和接入调试。

- 适配主流 Vibe Coding 工作流
- 提供开箱即用的 Agent Skills
- 提供多种 Demo 与项目模板
- 支持从模板开始开发，也支持将 EVA 能力接入现有项目
- 减少查阅文档、拼接接口和重复配置的成本

从一句需求开始，让 Agent 帮你完成从项目脚手架到设备接入的完整开发流程。

### **2. EVA SDK：为实时多模态交互而生**

EVA SDK 面向 App、IoT 与嵌入式设备提供统一的端侧开发能力。目前提供 **TypeScript** 与 **Python** 版本，后续将逐步更新诸如flutter、esp32、地瓜芯片等平台。

- **全双工音视频交互**：支持低延迟实时通信、自然插话与即时打断
- **情绪识别**：识别交互中的情绪状态，为应用提供更自然的反馈依据
- **设备指令下发**：将模型理解转化为端侧动作，连接 AI 与真实设备
- **统一接入体验**：使用统一的项目与鉴权体系，连接 EVA Platform
- **跨平台演进**：Flutter、ESP32、地瓜芯片等平台支持正在推进

相关项目：

- [SDK 与示例](https://github.com/AutoArk/eva-sdk-examples)

### **3. 端侧推理：真正实现 Token 自由**

> 让算力运行在你的设备上，真正实现 Token 自由。

EVA 商用版集成自研端侧 ASR、TTS 等模型在端侧推理。利用设备本地算力完成推理，降低对云端服务的依赖和持续调用成本，同时让AI不再依赖网络环境和推理服务商。

截至 EVA Platform 发布时，自研 ASR 模型（开源版）位列 [Hugging Face Open ASR Leaderboard](https://huggingface.co/datasets/hf-audio/open-asr-leaderboard?leaderboard_base_model=true) 全尺寸模型榜单第一。

![Image 1](docs/images/model_sota_rank.jpeg)


### **4. EVA CLI：让 Agent 自由操作平台资源**

EVA CLI 将 EVA Platform 的核心操作带到终端，也为 AI Agent 提供可执行的标准工具链。

- 创建和管理项目
- 申请与管理 API Key
- 查看资源与用量
- 管理应用配置和开发环境
- 支持 Agent 在授权范围内操作云端资产

无论是开发者手动操作，还是 Agent 自动执行，项目上下文与平台资源都可以在同一套工作流中保持一致。

### **5. Model Gateway：一次接入，自由选择模型**

EVA Model Gateway 为 ASR、TTS 与 LLM 提供统一接口。除集成 EVA 自研语音模型外，还统一适配主流模型服务商，帮助开发者避免被不同供应商的接口、鉴权方式和数据格式反复牵制。

- 统一接入主流 ASR、TTS 与 LLM Provider
- EVA 自研 ASR / TTS 提供更具竞争力的效果与价格
- 通过一个参数切换模型，无需改动其他业务代码
- 使用统一的鉴权、调用和用量管理方式
- 根据效果、延迟、成本与部署需求灵活选型

```text
你的应用 -> EVA Model Gateway -> EVA / 主流模型 Provider
                                  ASR / TTS / LLM
```

模型可以变化，你的应用架构不必随之重写。

### **6. 项目与用量管理：从开发到商用的一站式控制台**

EVA Platform 为每个应用和硬件项目提供独立、清晰的资源边界。

- 创建和管理多个 Project
- 为项目申请、查看和管理 API Key
- 查看调用量、额度与资源使用情况
- 每月提供免费使用额度
- 可按实际需求升级套餐
- 使用统一凭证接入 App、IoT 与嵌入式设备

访问 [EVA Platform](https://eva.autoarkai.com)，即可开始创建你的第一个项目。

---

## **适合构建什么**

- **AI 陪伴硬件**：智能玩具、桌面机器人、陪伴机器人
- **语音交互设备**：智能音箱、车载助手、穿戴设备
- **实时 AI 应用**：口语练习、会议助手、智能客服、互动内容
- **IoT 与具身智能**：家居设备、机器人、行业终端
- **端侧 AI 产品**：需要本地 ASR、TTS 与低延迟推理的设备

## **快速开始**

### **方式一：使用 AI Native 工作流**

1. 访问 [EVA Platform](https://eva.autoarkai.com)，注册登录。
2. 获取 EVA Agent Skill，并安装到你使用的 AI 编程工具
3. 选择一个 Demo 或项目模板
4. 用自然语言描述你希望构建的应用
5. 让 Agent 完成项目初始化、SDK 接入与配置

### **方式二：直接使用 EVA SDK**

1. 在 [EVA Platform](https://eva.autoarkai.com) 使用默认project或创建新的project。
2. 申请项目 API Key
3. 根据开发环境选择 SDK：
4. 运行示例并连接你的应用或设备
5. 按需配置 ASR、TTS 与 LLM Provider

## **Roadmap**

### **现已提供**

- EVA skill、EVA CLI、EVA SDK
- EVA Platform 项目与 API Key 管理
- Agent Skills 驱动的 AI Native 开发流程
- 全双工实时音视频交互
- 情绪识别与设备指令下发
- 商用版端侧 ASR / TTS 模型
- ASR / TTS / LLM Model Gateway
- 免费额度与多档套餐

### **持续推进**

- Flutter SDK
- ESP32 平台支持
- 地瓜芯片平台支持
- 更多嵌入式平台与参考设计
- 更多 Agent Skills、Demo 与项目模板
- 端侧与云端一致的多模态开发体验

---

## **加入 EVA 开源生态**

EVA 希望让每一位开发者都能更简单地构建实时多模态应用，让每一台设备都能拥有自然交互、环境感知与任务执行能力。

欢迎以下开发者加入：

- App 与全栈开发者
- AI Native 应用开发者
- IoT、智能玩具、智能家居与机器人团队
- ESP32、RK、STM32 等嵌入式开发者
- AI 模型与工具开发者
- 开源贡献者与 DIY 爱好者

你可以贡献：

- SDK 与跨平台适配
- Agent Skills
- Demo 与项目模板
- 硬件接入示例
- 教程与文档
- Issue、功能建议与 Pull Request

**让 AI 参与开发，让实时多模态能力运行在每一台设备上。**

## **License**

EVA OS is released under the MIT License.

You are free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software, provided that the original copyright and permission notice is included in all copies or substantial portions of the software.

## **Powered by**

![Powered by](docs/images/power_by_aliCloud.png)

## **Star History**

<a href="https://www.star-history.com/?repos=AutoArk%2FEVA-OS&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=AutoArk/EVA-OS&type=date&theme=dark&legend=top-left&sealed_token=RcFQqr7cjAtw7-Ur4L7mTj6kUK5S3IVUJby415R71QF3HBTLjCr1cjK5KAS75FIE3U8I5UWz5OF336XW0S1rilpPl6Hzj_ZaP5frRCgyutF3HeIaz2itbnBdwrjtHGrF_mXPUtwwqQFRQVlVy4LY4qtnO0QptfCIVCIWZBq6tWPnyfIIHzbf4Y9bVm13" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=AutoArk/EVA-OS&type=date&legend=top-left&sealed_token=RcFQqr7cjAtw7-Ur4L7mTj6kUK5S3IVUJby415R71QF3HBTLjCr1cjK5KAS75FIE3U8I5UWz5OF336XW0S1rilpPl6Hzj_ZaP5frRCgyutF3HeIaz2itbnBdwrjtHGrF_mXPUtwwqQFRQVlVy4LY4qtnO0QptfCIVCIWZBq6tWPnyfIIHzbf4Y9bVm13" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=AutoArk/EVA-OS&type=date&legend=top-left&sealed_token=RcFQqr7cjAtw7-Ur4L7mTj6kUK5S3IVUJby415R71QF3HBTLjCr1cjK5KAS75FIE3U8I5UWz5OF336XW0S1rilpPl6Hzj_ZaP5frRCgyutF3HeIaz2itbnBdwrjtHGrF_mXPUtwwqQFRQVlVy4LY4qtnO0QptfCIVCIWZBq6tWPnyfIIHzbf4Y9bVm13" />
 </picture>
</a>
