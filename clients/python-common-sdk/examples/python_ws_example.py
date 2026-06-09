"""
Eva WebSocket Client Example
============================

Demonstrates using the WebSocket transport (instead of LiveKit/WebRTC) to
connect to the Eva platform. Suitable for embedded devices and environments
where a WebRTC stack is not available.

Usage:
    1. Set EVA_API_KEY in your environment or .env file
    2. Adjust mic_index / spk_index / camera_index for your hardware
    3. Run:  python python_ws_example.py

Use `list_audio_devices.py` to discover available audio device indices.
"""

import asyncio
import os
import signal
import threading

from dotenv import load_dotenv
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.ws_client import EvaWebSocketClient
from shared.wake_word import VoskWakeWordEngine

load_dotenv()


def on_task_change(old_task: str, new_task: str):
    """Callback when task changes (e.g., after wake word detection)"""
    print(f"[App] Task changed: {old_task} -> {new_task}")


async def main():
    client = EvaWebSocketClient(
        api_key=os.getenv("EVA_API_KEY"),
        base_url=os.getenv("EVA_BASE_URL", "https://eva.autoarkai.com"),
        # Adjust these indices for your hardware (use list_audio_devices.py)
        mic_index=None,
        spk_index=None,  # MacBook Air Speakers
        # Use device's native sample rate (MacBook Air: 48kHz)
        # VOSK and Opus will handle resampling internally
        mic_sample_rate=48000,
        spk_sample_rate=48000,
        channels=1,
        frame_duration_ms=60,
        # Set camera_index=None to disable video
        camera_index=None,
        video_width=640,
        video_height=480,
        video_fps=2,
        # Echo suppression: auto-mute mic while bot is speaking
        echo_suppression=True,
        echo_suppression_timeout_ms=500,
        # Volume-based barge-in: allow interruption when user speaks loudly
        # User mic peak must exceed: bot_peak * multiplier + offset
        # Increase multiplier/offset to make barge-in harder (less sensitive)
        # Decrease to make it easier (more sensitive)
        barge_in_multiplier=1.5,
        barge_in_offset=500,
        # Wake word detection (optional)
        # VOSK engine: supports Chinese, auto-downloads small model
        #   wake_word_engine=VoskWakeWordEngine(wake_word="你好方舟")
        # Set wake_word_engine=None to disable
        wake_word_engine=VoskWakeWordEngine(wake_word="你好方舟"),
        wake_word_target_task="intent_task",
        # Task change callback (called when task switches, e.g., after wake word)
        on_task_change=on_task_change,
    )

    def signal_handler():
        print("\nShutdown requested.")
        client.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    def command_listener():
        print("\n[Manual Test] You can now type a task ID (e.g. 'intent_task') and press Enter to test edge hard-switch!")
        while True:
            try:
                cmd = input().strip()
                if cmd == "quit" or cmd == "exit":
                    client.stop()
                    break
                if cmd:
                    client.switch_task(cmd)
            except EOFError:
                break
            except Exception as e:
                print(f"Error in command listener: {e}")

    threading.Thread(target=command_listener, daemon=True).start()

    await client.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
