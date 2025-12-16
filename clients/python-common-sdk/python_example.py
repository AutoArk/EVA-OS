import asyncio
import os
import signal
from dotenv import load_dotenv
from eva_client import EvaClient

load_dotenv()

async def main():
    # Please adjust the microphone/speaker/camera index according to your actual situation.
    client = EvaClient(
        api_key=os.getenv("EVA_API_KEY"),
        mic_index=1,
        spk_index=6,
        mic_sample_rate=16000,
        spk_sample_rate=48000,
        camera_index=11,
        video_width=640,
        video_height=480,
        video_fps=20,
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
    