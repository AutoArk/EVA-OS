import abc
import asyncio
import logging
from typing import Optional, Callable
import pyaudio

from shared.fsm import RTVITaskNegotiator
from shared.wake_word import WakeWordEngine, WakeWordEvent
from shared.audio import find_audio_device_index

logger = logging.getLogger("BaseEvaClient")

class BaseEvaClient(abc.ABC):
    """
    Base class for Eva Clients, encapsulating common properties and logic.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://eva.autoarkai.com",
        mic_index: Optional[int] = 0,
        spk_index: Optional[int] = 0,
        mic_sample_rate: int = 48000,
        spk_sample_rate: int = 48000,
        channels: int = 1,
        frame_duration_ms: int = 60,
        camera_index: Optional[int] = 0,
        video_width: int = 640,
        video_height: int = 480,
        video_fps: int = 30,
        wake_word_engine: Optional[WakeWordEngine] = None,
        wake_word_target_task: Optional[str] = None,
        on_task_change: Optional[Callable[[str, str], None]] = None,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        if not base_url:
            raise ValueError("base_url is required")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

        # Audio Config
        self.mic_sample_rate = mic_sample_rate
        self.spk_sample_rate = spk_sample_rate
        self.channels = channels
        self.frame_duration_ms = frame_duration_ms
        self.mic_frame_size = int(mic_sample_rate * frame_duration_ms / 1000)
        self.spk_frame_size = int(spk_sample_rate * frame_duration_ms / 1000)

        # Video Config
        self.camera_index = camera_index
        self.video_width = video_width
        self.video_height = video_height
        self.video_fps = video_fps

        self.pa = pyaudio.PyAudio()
        self.mic_index = find_audio_device_index(self.pa, mic_index, is_input=True)
        self.spk_index = find_audio_device_index(self.pa, spk_index, is_input=False)

        self._shutdown_event = asyncio.Event()

        # Task FSM
        self.task_negotiator = RTVITaskNegotiator(on_task_change=on_task_change)
        
        # Wake Word
        self.wake_word_engine = wake_word_engine
        self._wake_word_target_task = wake_word_target_task
        if self.wake_word_engine:
            self.wake_word_engine.set_callback(self._on_wake_word_detected)

    def _on_wake_word_detected(self, event: WakeWordEvent):
        if self._wake_word_target_task:
            logger.info(f"Wake word '{event.keyword}' detected (confidence: {event.confidence}), requesting task switch to {self._wake_word_target_task}")
            self.switch_task(
                target_task=self._wake_word_target_task,
                reason=f"wake_word_detected:{event.keyword}"
            )

    def switch_task(self, target_task: str, reason: str = "manual_request"):
        """Manually trigger a hard task switch from the edge."""
        command = self.task_negotiator.request_switch(
            target_task=target_task,
            reason=reason
        )
        if command:
            self._send_command_async(command)
            logger.info(f"Sent task.switch.command to cloud for {target_task}")

    @abc.abstractmethod
    def _send_command_async(self, command: dict):
        """Send command to server asynchronously."""
        pass

    @abc.abstractmethod
    async def run(self):
        """Run the client."""
        pass

    def stop(self):
        """Stop the client."""
        self._shutdown_event.set()
        if self.wake_word_engine:
            self.wake_word_engine.stop()
