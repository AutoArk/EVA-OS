from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Optional, Callable

import numpy as np
import pyaudio
import requests

try:
    from livekit import rtc
except ImportError:
    rtc = None

from shared.audio import AudioOutputBuffer, find_audio_device_index, AudioConsumer
from shared.fsm import RTVITaskNegotiator
from shared.wake_word import WakeWordEngine
from shared.protocol import wrap_rtvi_envelope
from .base import BaseEvaClient

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger("EvaLiveKitClient")


class EvaLiveKitClient(BaseEvaClient):
    """
    Initializes the Eva LiveKit client.

    Args:
        api_key (str):
            Required. The Eva API key.
        mic_index (int, optional):
            Index of the microphone device. Defaults to 0.
        spk_index (int, optional):
            Index of the speaker device. Defaults to 0.
        mic_sample_rate (int, optional):
            Microphone input sample rate in Hz. Defaults to 48000.
        spk_sample_rate (int, optional):
            Speaker output sample rate in Hz. Defaults to 48000.
        channels (int, optional):
            Number of audio channels. Defaults to 1.
        frame_duration_ms (int, optional):
            Duration of a single audio frame in milliseconds. Defaults to 60ms.
        camera_index (int, optional):
            Index of the camera device. Defaults to 0.
        video_width (int, optional):
            Video capture width. Defaults to 640.
        video_height (int, optional):
            Video capture height. Defaults to 480.
        video_fps (int, optional):
            Video frame rate (FPS). Defaults to 30.
        base_url (str, optional):
            Base URL for the HTTP API service.
        wss_url (str, optional):
            WebSocket URL for RTC.
        wake_word_engine (WakeWordEngine, optional):
            Wake word engine for voice activation.
        wake_word_target_task (str, optional):
            Target task to switch to when wake word is detected.
        on_task_change (callable, optional):
            Callback function(old_task, new_task) when task changes.
    """
    def __init__(
        self,
        api_key,
        mic_index=0,
        spk_index=0,
        mic_sample_rate=48000,
        spk_sample_rate=48000,
        channels=1,
        frame_duration_ms=60,
        camera_index=0,
        video_width=640,
        video_height=480,
        video_fps=30,
        base_url="https://eva.autoarkai.com",
        wss_url="wss://rtc.autoarkai.com",
        wake_word_engine: Optional[WakeWordEngine] = None,
        wake_word_target_task: Optional[str] = None,
        on_task_change: Optional[Callable[[str, str], None]] = None,
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            mic_index=mic_index,
            spk_index=spk_index,
            mic_sample_rate=mic_sample_rate,
            spk_sample_rate=spk_sample_rate,
            channels=channels,
            frame_duration_ms=frame_duration_ms,
            camera_index=camera_index,
            video_width=video_width,
            video_height=video_height,
            video_fps=video_fps,
            wake_word_engine=wake_word_engine,
            wake_word_target_task=wake_word_target_task,
            on_task_change=on_task_change,
        )

        if rtc is None:
            raise ImportError(
                "livekit is not installed. Please install it using: "
                "pip install livekit livekit-api"
            )

        self.wss_url = wss_url

        if not self.wss_url:
            raise ValueError("Missing required environment variables.")

        self.audio_buffer = AudioOutputBuffer()
        self.room = None

        # Sources & Tracks
        self.mic_source = None
        self.video_source = None
        self.video_cap = None

        # PyAudio streams
        self.input_stream = None
        self.output_stream = None
        self._loop = None

        # RTVI data channel for task state coordination
        self._rtvi_topic = "task-ir-control"

    def _send_command_async(self, command: dict):
        if getattr(self, '_loop', None):
            asyncio.run_coroutine_threadsafe(
                self._send_rtvi_message(command), self._loop
            )
        else:
            logger.error("No event loop found to send RTVI message")

    async def _send_rtvi_message(self, message: dict):
        """Send RTVI message via LiveKit data channel."""
        if not self.room:
            return
        
        envelope = wrap_rtvi_envelope(message, self._rtvi_topic)
        payload = json.dumps(envelope).encode("utf-8")
        
        # Send via data channel
        await self.room.local_participant.publish_data(
            payload,
            reliable=True,
            topic=self._rtvi_topic,
        )

    def get_room_token(self) -> str:
        url = f"{self.base_url}/api/solution/chat-room"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = requests.post(url, headers=headers, json={})
            response.raise_for_status()
            data = response.json()
            if "data" in data and "roomToken" in data["data"]:
                return data["data"]["roomToken"]
            elif "roomToken" in data:
                return data["roomToken"]
            else:
                raise ValueError("Invalid response structure.")
        except Exception as e:
            logger.error(f"Token error: {e}")
            raise

    async def run(self):
        self._loop = asyncio.get_running_loop()
        try:
            token = self.get_room_token()
        except Exception as e:
            logger.error(f"Failed to get room token: {e}")
            return

        self.room = rtc.Room()

        @self.room.on("track_subscribed")
        def on_track_subscribed(
            track: rtc.RemoteTrack,
            publication: rtc.RemoteTrackPublication,
            participant: rtc.RemoteParticipant,
        ):
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info(f"Subscribed to audio track: {publication.sid}")
                asyncio.create_task(self.handle_audio_output(track))
            elif track.kind == rtc.TrackKind.KIND_VIDEO:
                logger.info(f"Subscribed to video track: {publication.sid} (Rendering not implemented)")

        @self.room.on("disconnected")
        def on_disconnected():
            logger.info("Disconnected.")
            self._shutdown_event.set()

        @self.room.on("data_received")
        def on_data_received(data_packet: rtc.DataPacket):
            data = data_packet.data
            
            try:
                msg_dict = json.loads(data.decode("utf-8"))
                
                # FSM handles unwrapping the RTVI envelope
                response = self.task_negotiator.handle_message(msg_dict)
                if response:
                    if getattr(self, '_loop', None):
                        asyncio.run_coroutine_threadsafe(
                            self._send_rtvi_message(response), self._loop
                        )
                    else:
                        logger.error("No event loop found to send RTVI message")
            except Exception as e:
                # 忽略解析非 JSON 或者不相关的数据包
                logger.error(f"Failed to parse or handle message (ignoring): {e}")

        logger.info(f"Connecting to {self.wss_url}")
        try:
            await self.room.connect(self.wss_url, token)
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return

        # Start Media Tasks
        mic_task = asyncio.create_task(self.publish_microphone())
        video_task = asyncio.create_task(self.publish_camera())

        # Start wake word detection if configured
        if self.wake_word_engine:
            self.wake_word_engine.start()

        await self._shutdown_event.wait()

        # Stop wake word detection
        if self.wake_word_engine:
            self.wake_word_engine.stop()

        # Cleanup Tasks
        if mic_task:
            mic_task.cancel()
        if video_task:
            video_task.cancel()

        # Close Video Capture
        if self.video_cap and self.video_cap.isOpened():
            self.video_cap.release()
            logger.info("Camera released.")

        # Close PyAudio streams
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()

        self.pa.terminate()

        if self.room.isconnected():
            await self.room.disconnect()

    async def publish_microphone(self):
        self.mic_source = rtc.AudioSource(self.mic_sample_rate, self.channels)
        track = rtc.LocalAudioTrack.create_audio_track("mic_track", self.mic_source)
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_MICROPHONE

        try:
            await self.room.local_participant.publish_track(track, options)
            logger.info(
                f"Mic published. Rate: {self.mic_sample_rate}, Index: {self.mic_index}"
            )
        except Exception as e:
            logger.error(f"Failed to publish microphone: {e}")
            return

        frames_per_buffer = int(self.mic_sample_rate * self.frame_duration_ms / 1000)
        loop = asyncio.get_running_loop()

        # PyAudio Callback
        def mic_callback(in_data, frame_count, time_info, status):
            # Feed audio to wake word runner if enabled
            if self.wake_word_engine and isinstance(self.wake_word_engine, AudioConsumer):
                # in_data comes as bytes
                self.wake_word_engine.add_audio_frame(in_data, sample_rate=self.mic_sample_rate, channels=self.channels)
            
            # in_data comes as bytes
            audio_frame = rtc.AudioFrame(
                data=in_data,
                sample_rate=self.mic_sample_rate,
                num_channels=self.channels,
                samples_per_channel=frame_count,
            )
            asyncio.run_coroutine_threadsafe(
                self.mic_source.capture_frame(audio_frame), loop
            )
            return (None, pyaudio.paContinue)

        try:
            self.input_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.mic_sample_rate,
                input=True,
                input_device_index=self.mic_index,
                frames_per_buffer=frames_per_buffer,
                stream_callback=mic_callback,
            )
            self.input_stream.start_stream()
        except Exception as e:
            logger.error(f"Failed to open input stream: {e}")
            return

        # Keep the task alive
        while not self._shutdown_event.is_set():
            await asyncio.sleep(1)

    async def publish_camera(self):
        """
        Captures video from the camera using OpenCV and publishes it to the room.
        """
        try:
            import cv2
        except ImportError:
            logger.error("opencv-python is required for video. Install with: pip install opencv-python")
            return

        logger.info(f"Opening camera index {self.camera_index}...")
        
        # Initialize OpenCV VideoCapture
        self.video_cap = cv2.VideoCapture(self.camera_index)
        
        if not self.video_cap.isOpened():
            logger.error(f"Could not open video device {self.camera_index}")
            return

        # Set Resolution
        self.video_cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.video_width)
        self.video_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.video_height)
        
        # Create LiveKit Video Source and Track
        self.video_source = rtc.VideoSource(self.video_width, self.video_height)
        track = rtc.LocalVideoTrack.create_video_track("camera_track", self.video_source)
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_CAMERA
        
        try:
            await self.room.local_participant.publish_track(track, options)
            logger.info(f"Camera published. Res: {self.video_width}x{self.video_height}, FPS: {self.video_fps}")
        except Exception as e:
            logger.error(f"Failed to publish camera track: {e}")
            self.video_cap.release()
            return

        # Calculate sleep interval
        interval = 1.0 / self.video_fps

        while not self._shutdown_event.is_set():
            # Read frame from OpenCV
            ret, frame = self.video_cap.read()
            if not ret:
                logger.warning("Failed to read frame from camera")
                await asyncio.sleep(0.1)
                continue

            # Convert BGR (OpenCV default) to RGBA (LiveKit expected)
            # Note: OpenCV operations are blocking, but fast enough for low resolutions.
            rgba_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            
            # Create LiveKit VideoFrame
            # Format: width, height, type, data
            lk_frame = rtc.VideoFrame(
                self.video_width,
                self.video_height,
                rtc.VideoBufferType.RGBA,
                rgba_frame.tobytes()
            )

            # Capture frame
            self.video_source.capture_frame(lk_frame)

            # Control framerate
            await asyncio.sleep(interval)

    async def handle_audio_output(self, track: rtc.RemoteAudioTrack):
        audio_stream = rtc.AudioStream(
            track, sample_rate=self.spk_sample_rate, num_channels=self.channels
        )
        logger.info(
            f"Speaker stream started. Rate: {self.spk_sample_rate}, Index: {self.spk_index}"
        )

        frames_per_buffer = int(self.spk_sample_rate * self.frame_duration_ms / 1000)

        # PyAudio Output Callback
        def spk_callback(in_data, frame_count, time_info, status):
            # Retrieve the exact number of bytes needed from the buffer
            data = self.audio_buffer.get_chunk(frame_count * self.channels)
            return (data, pyaudio.paContinue)

        try:
            self.output_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.spk_sample_rate,
                output=True,
                output_device_index=self.spk_index,
                frames_per_buffer=frames_per_buffer,
                stream_callback=spk_callback,
            )
            self.output_stream.start_stream()
        except Exception as e:
            logger.error(f"Failed to open output stream: {e}")
            return

        try:
            async for event in audio_stream:
                # LiveKit event.frame.data is typically a memoryview or buffer
                # Convert to bytes to ensure compatibility before queuing
                data_bytes = bytes(event.frame.data)
                self.audio_buffer.put(data_bytes)

        except Exception as e:
            logger.error(f"Audio output error: {e}")

    def stop(self):
        self._shutdown_event.set()