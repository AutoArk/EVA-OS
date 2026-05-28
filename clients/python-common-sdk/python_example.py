import asyncio
import os
import signal
from dotenv import load_dotenv
from eva_client import EvaClient

load_dotenv()

def on_task_change(old_task: str, new_task: str):
    """Callback when task changes (e.g., after wake word detection)"""
    print(f"[App] Task changed: {old_task} -> {new_task}")

async def main():
    # Please adjust the microphone/speaker/camera index according to your actual situation.
    client = EvaClient(
        api_key=os.getenv("EVA_API_KEY"),
        base_url=os.getenv("EVA_BASE_URL", "https://eva.autoarkai.com"),
        wss_url=os.getenv("EVA_WSS_URL", "wss://rtc.autoarkai.com"),
        mic_index=None,          # MacBook Air Microphone
        spk_index=None,          # MacBook Air Speakers
        mic_sample_rate=48000,
        spk_sample_rate=48000,
        camera_index=None,  # Set to an integer to enable video
        video_width=640,
        video_height=480,
        video_fps=20,
        
        # Wake word detection (optional)
        wake_word="你好方舟",
        wake_word_target_task="intent_task",
        
        # Task change callback (called when task switches, e.g., after wake word)
        on_task_change=on_task_change,
    )

    def signal_handler():
        print("\nShutdown.")
        client.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    await client.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    