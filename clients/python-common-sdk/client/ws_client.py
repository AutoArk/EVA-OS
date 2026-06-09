"""
Eva WebSocket Client
====================

Lightweight WebSocket transport client for the Eva platform. Intended for
embedded devices (ESP32, Raspberry Pi, IoT) and environments where a full
WebRTC stack is not available.

Protocol:
    Eva Binary Protocol V1
    - 9-byte big-endian header: version(u8) | media_type(u8) | stream_id(u8) | sequence(u16) | delta_ms(u32)
    - Opus audio frames (media_type=0x01) and JPEG video frames (media_type=0x02)
    - JSON text messages for control and events

Flow:
    1. POST /api/solution/chat-room  {transport_type: "websocket"}
    2. Connect WebSocket: attach_url?token=attach_token
    3. Send hello (JSON) with declared streams
    4. Receive hello response with selected_streams
    5. Publish microphone audio (Opus) + optional camera (JPEG)
    6. Receive audio (Opus) from the server, decode, play
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
import uuid
from typing import Optional, Callable

import numpy as np
import pyaudio
import requests
import websockets

from shared.audio import AudioOutputBuffer, find_audio_device_index, AudioConsumer
from shared.fsm import RTVITaskNegotiator
from shared.wake_word import WakeWordEngine
from shared.protocol import wrap_rtvi_envelope
from .base import BaseEvaClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger("EvaWSClient")

# --- Eva Binary Protocol V1 ---
HEADER_FORMAT = "!BBBHI"
HEADER_SIZE = 9
PROTOCOL_VERSION = 1
MEDIA_OPUS_AUDIO = 0x01
MEDIA_JPEG_VIDEO = 0x02

# Default stream IDs (overridden by hello negotiation)
UPLINK_AUDIO_STREAM_ID = 0
UPLINK_VIDEO_STREAM_ID = 1
DOWNLINK_AUDIO_STREAM_ID = 2


class EvaWebSocketClient(BaseEvaClient):
    """
    Eva platform WebSocket client.

    Uses Eva Binary Protocol V1 over a plain WebSocket connection.
    Suitable for embedded/IoT devices that cannot run a WebRTC stack.

    Args:
        api_key: Required. The Eva API key (Solution API Key).
        base_url: HTTP base URL of the Eva platform.
        mic_index: Microphone device index or name substring. Defaults to 0.
        spk_index: Speaker device index or name substring. Defaults to 0.
        sample_rate: Audio sample rate in Hz. Both mic and speaker use the same rate.
            Defaults to 16000 (server default for WebSocket transport).
        channels: Number of audio channels. Defaults to 1 (mono).
        frame_duration_ms: Duration of a single Opus frame in ms. Defaults to 60.
        camera_index: Camera device index, or None to disable video.
        video_width: Video capture width. Defaults to 640.
        video_height: Video capture height. Defaults to 480.
        video_fps: Video frame rate. Defaults to 2.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://eva.autoarkai.com",
        mic_index=0,
        spk_index=0,
        mic_sample_rate: int = 48000,
        spk_sample_rate: int = 48000,
        channels: int = 1,
        frame_duration_ms: int = 60,
        camera_index=None,
        video_width: int = 640,
        video_height: int = 480,
        video_fps: int = 2,
        echo_suppression: bool = True,
        echo_suppression_timeout_ms: int = 500,
        barge_in_multiplier: float = 1.5,
        barge_in_offset: int = 500,
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

        # Runtime state
        self.audio_buffer = AudioOutputBuffer()
        self.ws = None
        self.session_id = None
        self._connect_time_ms = 0.0
        self._sequence = 0
        self._bot_speaking = False  # True while bot audio is being received/played
        self._mic_muted = False     # True when mic is auto-muted during bot speech
        self._last_bot_audio_time = 0.0  # Timestamp of last bot audio frame
        self._loop = None           # Event loop reference (set in run())

        # Echo suppression config
        self._echo_suppression = echo_suppression
        self._echo_suppression_timeout_s = echo_suppression_timeout_ms / 1000.0

        # Volume-based barge-in (new)
        self._bot_volume_peak = 0  # Recent bot audio peak amplitude
        self._barge_in_multiplier = barge_in_multiplier  # User volume must be > bot * this
        self._barge_in_offset = barge_in_offset  # Plus this absolute threshold

        # Opus codec
        self._encoder = None
        self._decoder = None

        # PyAudio streams
        self.input_stream = None
        self.output_stream = None
        self.video_cap = None

        # Stream IDs (may be overridden by hello negotiation)
        self.uplink_audio_stream_id = UPLINK_AUDIO_STREAM_ID
        self.uplink_video_stream_id = UPLINK_VIDEO_STREAM_ID
        self.downlink_audio_stream_id = DOWNLINK_AUDIO_STREAM_ID

    def _send_command_async(self, command: dict):
        if getattr(self, '_loop', None) and self.ws:
            envelope = wrap_rtvi_envelope(command)
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps(envelope)), self._loop
            )
        else:
            logger.warning("[WakeWord] Cannot send command: ws or loop not available")

    # ------------------------------------------------------------------
    # Session creation (HTTP)
    # ------------------------------------------------------------------
    def get_ws_session(self) -> dict:
        """
        Request a WebSocket session from the Eva platform.

        Returns:
            dict with keys: session_id, attach_url, attach_token
        """
        url = f"{self.base_url}/api/solution/chat-room"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        body = {"transport_type": "websocket"}

        response = requests.post(url, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Handle both wrapped and unwrapped response shapes
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            data = data["data"]

        session_id = data.get("sessionId")
        attach_url = data.get("attachUrl")
        attach_token = data.get("attachToken")

        if not all([session_id, attach_url, attach_token]):
            raise ValueError(f"Invalid session response: {data}")

        self.session_id = session_id
        logger.info(f"Session created: {session_id}")
        return {
            "session_id": session_id,
            "attach_url": attach_url,
            "attach_token": attach_token,
        }

    # ------------------------------------------------------------------
    # Binary protocol helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _pack_header(
        media_type: int, stream_id: int, sequence: int, delta_ms: int
    ) -> bytes:
        return struct.pack(
            HEADER_FORMAT,
            PROTOCOL_VERSION,
            media_type,
            stream_id & 0xFF,
            sequence & 0xFFFF,
            delta_ms & 0xFFFFFFFF,
        )

    @staticmethod
    def _unpack_header(data: bytes):
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Data too short for header: {len(data)} < {HEADER_SIZE}")
        version, media_type, stream_id, sequence, delta_ms = struct.unpack(
            HEADER_FORMAT, data[:HEADER_SIZE]
        )
        return version, media_type, stream_id, sequence, delta_ms

    def _next_sequence(self) -> int:
        seq = self._sequence
        self._sequence = (self._sequence + 1) & 0xFFFF
        return seq

    def _delta_ms(self) -> int:
        return int(time.monotonic() * 1000 - self._connect_time_ms) & 0xFFFFFFFF

    # ------------------------------------------------------------------
    # Hello handshake
    # ------------------------------------------------------------------
    def _build_hello(self) -> dict:
        device_id = f"eva-ws-py-{uuid.uuid4().hex[:8]}"
        # Server expects 16kHz audio (we resample from device rate)
        server_sample_rate = 16000
        
        streams = [
            {
                "stream_id": self.uplink_audio_stream_id,
                "kind": "audio",
                "direction": "uplink",
                "source": "mic_main",
                "codec": "opus",
                "sample_rate": server_sample_rate,
                "channels": self.channels,
                "frame_duration_ms": self.frame_duration_ms,
            },
            {
                "stream_id": self.downlink_audio_stream_id,
                "kind": "audio",
                "direction": "downlink",
                "source": "tts_main",
                "codec": "opus",
                "sample_rate": server_sample_rate,
                "channels": self.channels,
                "frame_duration_ms": self.frame_duration_ms,
            },
        ]

        if self.camera_index is not None:
            streams.append(
                {
                    "stream_id": self.uplink_video_stream_id,
                    "kind": "video",
                    "direction": "uplink",
                    "source": "camera_front",
                    "codec": "jpeg",
                    "width": self.video_width,
                    "height": self.video_height,
                    "fps": self.video_fps,
                }
            )

        return {
            "type": "hello",
            "version": 1,
            "device_id": device_id,
            "transport": "websocket",
            "role": "primary",
            "streams": streams,
        }

    # ------------------------------------------------------------------
    # Opus codec setup
    # ------------------------------------------------------------------
    def _init_opus(self):
        import opuslib  # type: ignore

        # Server expects 16kHz audio, so encoder/decoder use 16kHz
        # Client resamples between device rate (e.g., 48kHz) and server rate (16kHz)
        server_sample_rate = 16000
        
        # Encoder: converts resampled PCM (16kHz) to Opus
        self._encoder = opuslib.Encoder(
            server_sample_rate, self.channels, opuslib.APPLICATION_VOIP
        )
        # Decoder: converts Opus to PCM at 16kHz, then resampled to device rate
        self._decoder = opuslib.Decoder(server_sample_rate, self.channels)
        logger.info(
            f"Opus codec initialized: server={server_sample_rate}Hz, "
            f"device_mic={self.mic_sample_rate}Hz, device_spk={self.spk_sample_rate}Hz, "
            f"{self.channels}ch, mic_frame={self.mic_frame_size}, spk_frame={self.spk_frame_size}"
        )

    # ------------------------------------------------------------------
    # Microphone input (PCM -> Opus -> WS)
    # ------------------------------------------------------------------
    async def _run_microphone(self, loop: asyncio.AbstractEventLoop):
        frames_per_buffer = self.mic_frame_size
        frames_sent = [0]
        last_log_time = [time.monotonic()]

        # Resample if device rate != server rate (server expects 16kHz)
        server_sample_rate = 16000
        need_resample = (self.mic_sample_rate != server_sample_rate)
        
        if need_resample:
            from scipy import signal
            logger.info(f"[Mic] Resampling from {self.mic_sample_rate}Hz to {server_sample_rate}Hz")

        def mic_callback(in_data, frame_count, time_info, status):
            if self._encoder is None or self.ws is None:
                return (None, pyaudio.paContinue)

            now = time.monotonic()

            # Detect bot stopped speaking (timeout since last audio frame)
            if self._echo_suppression and self._bot_speaking:
                if now - self._last_bot_audio_time > self._echo_suppression_timeout_s:
                    self._bot_speaking = False
                    self._bot_volume_peak = 0  # Reset bot volume when silent

            # Diagnostic: check if input is silence (all zeros or near-zeros)
            pcm = np.frombuffer(in_data, dtype=np.int16)
            mic_peak = int(np.max(np.abs(pcm))) if len(pcm) > 0 else 0

            # Feed audio to wake word detector (always, regardless of echo suppression)
            if self.wake_word_engine and isinstance(self.wake_word_engine, AudioConsumer):
                self.wake_word_engine.add_audio_frame(in_data, sample_rate=self.mic_sample_rate, channels=self.channels)

            # Echo suppression with volume-based barge-in
            should_send = True
            if self._echo_suppression and self._bot_speaking:
                # Calculate barge-in threshold
                barge_in_threshold = self._bot_volume_peak * self._barge_in_multiplier + self._barge_in_offset

                if mic_peak > barge_in_threshold:
                    # User is speaking louder than bot echo - allow barge-in
                    if self._mic_muted:
                        self._mic_muted = False
                        logger.info(f"Mic unmuted (barge-in: mic={mic_peak} > threshold={int(barge_in_threshold)})")
                    should_send = True
                else:
                    # Bot is louder - suppress mic
                    if not self._mic_muted:
                        self._mic_muted = True
                        logger.info("Mic auto-muted (bot speaking)")
                    should_send = False
            else:
                # Bot not speaking - always send
                if self._mic_muted:
                    self._mic_muted = False
                    logger.info("Mic unmuted (bot stopped)")

            if should_send:
                try:
                    # Resample if needed (device rate -> server rate)
                    if need_resample:
                        # Convert to float for resampling
                        pcm_float = pcm.astype(np.float32) / 32768.0
                        # Calculate target length
                        target_length = int(len(pcm_float) * server_sample_rate / self.mic_sample_rate)
                        # Resample
                        pcm_resampled = signal.resample(pcm_float, target_length)
                        # Convert back to int16
                        pcm_to_encode = (pcm_resampled * 32768.0).astype(np.int16)
                        frame_size_for_encode = target_length
                    else:
                        pcm_to_encode = pcm
                        frame_size_for_encode = self.mic_frame_size

                    # opuslib.encode expects raw int16 bytes, NOT a Python list
                    opus_bytes = self._encoder.encode(pcm_to_encode.tobytes(), frame_size_for_encode)

                    header = self._pack_header(
                        MEDIA_OPUS_AUDIO,
                        self.uplink_audio_stream_id,
                        self._next_sequence(),
                        self._delta_ms(),
                    )
                    asyncio.run_coroutine_threadsafe(
                        self.ws.send(header + opus_bytes), loop
                    )
                    frames_sent[0] += 1
                except Exception as e:
                    logger.error(f"Mic encode error: {e}")

            # Log every 5 seconds
            if now - last_log_time[0] >= 5.0:
                if self._mic_muted:
                    mute_status = " [MUTED]"
                else:
                    mute_status = ""
                logger.info(
                    f"Mic: sent {frames_sent[0]} frames in last 5s, "
                    f"peak amplitude={mic_peak}, bot_peak={self._bot_volume_peak}{mute_status}"
                )
                frames_sent[0] = 0
                last_log_time[0] = now

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
            logger.info(
                f"Mic started: rate={self.mic_sample_rate}, index={self.mic_index}, "
                f"frame={self.frame_duration_ms}ms"
            )
        except Exception as e:
            logger.error(f"Failed to start mic: {e}")
            return

        while not self._shutdown_event.is_set():
            await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Camera input (BGR -> JPEG -> WS)
    # ------------------------------------------------------------------
    async def _run_camera(self):
        try:
            import cv2  # type: ignore
        except ImportError:
            logger.error("opencv-python is required for video. Install with: pip install opencv-python")
            return

        self.video_cap = cv2.VideoCapture(self.camera_index)
        if not self.video_cap.isOpened():
            logger.error(f"Could not open camera {self.camera_index}")
            return

        self.video_cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.video_width)
        self.video_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.video_height)

        interval = 1.0 / max(self.video_fps, 1)
        logger.info(
            f"Camera started: {self.video_width}x{self.video_height}@{self.video_fps}fps, "
            f"index={self.camera_index}"
        )

        try:
            while not self._shutdown_event.is_set():
                ret, frame = self.video_cap.read()
                if not ret:
                    await asyncio.sleep(0.1)
                    continue

                # Encode BGR -> JPEG bytes
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if not ok:
                    continue

                header = self._pack_header(
                    MEDIA_JPEG_VIDEO,
                    self.uplink_video_stream_id,
                    self._next_sequence(),
                    self._delta_ms(),
                )

                if self.ws is not None:
                    await self.ws.send(header + buf.tobytes())

                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        finally:
            if self.video_cap is not None and self.video_cap.isOpened():
                self.video_cap.release()

    # ------------------------------------------------------------------
    # Speaker output (WS -> Opus decode -> PCM)
    # ------------------------------------------------------------------
    async def _run_speaker(self, loop: asyncio.AbstractEventLoop):
        frames_per_buffer = self.spk_frame_size

        def spk_callback(in_data, frame_count, time_info, status):
            data = self.audio_buffer.get_chunk(frame_count * self.channels)
            return (data, pyaudio.paContinue)

        # Try the configured device first; if it fails (e.g. "Invalid number
        # of channels"), fall back to the system default (index=None).
        for device_index in (self.spk_index, None):
            try:
                self.output_stream = self.pa.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.spk_sample_rate,
                    output=True,
                    output_device_index=device_index,
                    frames_per_buffer=frames_per_buffer,
                    stream_callback=spk_callback,
                )
                self.output_stream.start_stream()
                logger.info(
                    f"Speaker started: rate={self.spk_sample_rate}, "
                    f"index={device_index}"
                )
                break
            except Exception as e:
                if device_index is None:
                    logger.error(f"Failed to start speaker (default): {e}")
                    return
                logger.warning(
                    f"Speaker index={device_index} failed ({e}), "
                    f"retrying with system default..."
                )

        while not self._shutdown_event.is_set():
            await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Message receive loop
    # ------------------------------------------------------------------
    async def _run_receiver(self):
        # Diagnostics: count received frames over time
        frames_received = [0]
        last_log_time = [time.monotonic()]

        try:
            async for msg in self.ws:
                if isinstance(msg, bytes):
                    self._handle_binary(msg, frames_received)
                elif isinstance(msg, str):
                    # _handle_text may return a message to send back (e.g., commit)
                    reply = self._handle_text(msg)
                    if reply and self.ws:
                        # Wrap TaskIR messages in RTVI envelope
                        if reply.get("type") in ("task.switch.commit", "task.switch.command"):
                            reply = wrap_rtvi_envelope(reply)
                        await self.ws.send(json.dumps(reply))

                # Periodic log
                now = time.monotonic()
                if now - last_log_time[0] >= 5.0:
                    logger.info(
                        f"Recv: {frames_received[0]} audio frames in last 5s"
                    )
                    frames_received[0] = 0
                    last_log_time[0] = now
        except websockets.ConnectionClosed as e:
            logger.info(f"WebSocket closed: code={e.code}, reason={e.reason}")
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Receiver error: {e}")
        finally:
            self._shutdown_event.set()

    def _handle_binary(self, data: bytes, frames_received=None):
        if len(data) < HEADER_SIZE:
            return
        try:
            _version, media_type, stream_id, _sequence, _delta_ms = self._unpack_header(data)
        except ValueError as e:
            logger.error(f"Failed to unpack binary header: {e}")
            return

        payload = data[HEADER_SIZE:]
        if media_type == MEDIA_OPUS_AUDIO and self._decoder is not None:
            if stream_id != self.downlink_audio_stream_id:
                return
            try:
                # Server sends 16kHz audio, decode it
                server_sample_rate = 16000
                server_frame_size = int(server_sample_rate * self.frame_duration_ms / 1000)
                pcm = self._decoder.decode(payload, server_frame_size)
                
                # Resample if device rate != server rate
                if self.spk_sample_rate != server_sample_rate:
                    from scipy import signal
                    pcm_array = np.frombuffer(pcm, dtype=np.int16)
                    target_length = int(len(pcm_array) * self.spk_sample_rate / server_sample_rate)
                    pcm_resampled = signal.resample(pcm_array.astype(np.float32), target_length)
                    pcm = pcm_resampled.astype(np.int16).tobytes()
                
                self.audio_buffer.put(pcm)
                if frames_received is not None:
                    frames_received[0] += 1
                # Mark bot as speaking for echo suppression
                self._bot_speaking = True
                self._last_bot_audio_time = time.monotonic()
                # Track bot volume peak for barge-in detection
                pcm_array = np.frombuffer(pcm, dtype=np.int16)
                if len(pcm_array) > 0:
                    self._bot_volume_peak = int(np.max(np.abs(pcm_array)))
            except Exception as e:
                logger.error(f"Opus decode error: {e}")
        elif media_type == MEDIA_JPEG_VIDEO:
            logger.debug(f"Received JPEG frame: {len(payload)} bytes")

    def _handle_text(self, text: str) -> Optional[dict]:
        """
        Handle incoming text message.
        
        Returns:
            Message dict to send back (e.g., task.switch.commit), or None
        """
        try:
            msg = json.loads(text)
            msg_type = msg.get("type")
            if msg_type == "hello":
                logger.info(f"Server hello: version={msg.get('version')}")
                self._apply_selected_streams(msg.get("selected_streams"))
                return None
            
            # Pass to TaskFSM for task state coordination
            if msg_type in ("task.switch.advice", "task.switch.result", "system_config") or \
               "approved" in msg or "suggested_task" in msg:
                commit_msg = self.task_negotiator.handle_message(msg)
                if commit_msg:
                    return commit_msg
                return None
            
            logger.debug(f"Text message: {msg_type}")
            return None
        except Exception as e:
            logger.error(f"Text parse error: {e}")
            return None

    def _apply_selected_streams(self, selected_streams):
        if not isinstance(selected_streams, list):
            return
        for s in selected_streams:
            kind = s.get("kind")
            direction = s.get("direction")
            stream_id = s.get("stream_id")
            if stream_id is None:
                continue
            if kind == "audio" and direction == "uplink":
                self.uplink_audio_stream_id = stream_id
            elif kind == "video" and direction == "uplink":
                self.uplink_video_stream_id = stream_id
            elif kind == "audio" and direction == "downlink":
                self.downlink_audio_stream_id = stream_id

    # ------------------------------------------------------------------
    # Disconnect (HTTP cleanup)
    # ------------------------------------------------------------------
    def disconnect_ws_session(self):
        """Notify the server to clean up the WebSocket session."""
        if not self.session_id:
            return
        url = f"{self.base_url}/api/solution/chat-room-ws"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            r = requests.delete(
                url, headers=headers, json={"session_id": self.session_id}, timeout=10
            )
            if r.ok:
                logger.info(f"Session {self.session_id} disconnected on server")
            else:
                logger.warning(f"Server disconnect failed: {r.status_code}")
        except Exception as e:
            logger.error(f"Failed to notify server disconnect: {e}")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    async def run(self):
        """Connect and run the client until stopped or disconnected."""
        # 1. Create session
        try:
            session = self.get_ws_session()
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return

        # 2. Connect WebSocket
        ws_url = f"{session['attach_url']}?token={session['attach_token']}"
        logger.info(f"Connecting to {session['attach_url']}")

        try:
            async with websockets.connect(ws_url) as ws:
                self.ws = ws
                self._connect_time_ms = time.monotonic() * 1000

                # 3. Hello handshake
                import json

                hello = self._build_hello()
                await ws.send(json.dumps(hello))
                logger.info("Hello sent, waiting for response...")

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    if isinstance(raw, str):
                        resp = json.loads(raw)
                        if resp.get("type") == "hello":
                            logger.info(f"Handshake OK: version={resp.get('version')}")
                            self._apply_selected_streams(resp.get("selected_streams"))
                        else:
                            logger.warning(f"Expected hello response, got: {resp.get('type')}")
                    else:
                        logger.warning("Expected text hello response, got binary")
                except asyncio.TimeoutError:
                    logger.error("Hello handshake timeout")
                    return
                except Exception as e:
                    logger.error(f"Hello handshake failed: {e}")
                    return

                # 4. Init Opus codec
                self._init_opus()

                # 5. Launch media tasks
                self._loop = asyncio.get_running_loop()
                tasks = [
                    asyncio.create_task(self._run_microphone(self._loop)),
                    asyncio.create_task(self._run_speaker(self._loop)),
                    asyncio.create_task(self._run_receiver()),
                ]
                if self.camera_index is not None:
                    tasks.append(asyncio.create_task(self._run_camera()))

                # Start wake word detection if configured
                if self.wake_word_engine:
                    self.wake_word_engine.start()
                    logger.info("[WakeWord] Detection started")

                # Wait for shutdown signal
                await self._shutdown_event.wait()

                # Cancel remaining tasks
                for t in tasks:
                    t.cancel()
                for t in tasks:
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
        except websockets.ConnectionClosed as e:
            logger.info(f"Connection closed: code={e.code}, reason={e.reason}")
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            self._cleanup()

    def _cleanup(self):
        # Stop wake word detection
        if self.wake_word_engine:
            self.wake_word_engine.stop()
            logger.info("[WakeWord] Detection stopped")

        if self.input_stream is not None:
            try:
                self.input_stream.stop_stream()
                self.input_stream.close()
            except Exception as e:
                logger.error(f"Error during input stream cleanup: {e}")
            self.input_stream = None

        if self.output_stream is not None:
            try:
                self.output_stream.stop_stream()
                self.output_stream.close()
            except Exception as e:
                logger.error(f"Error during output stream cleanup: {e}")
            self.output_stream = None

        if self.video_cap is not None:
            try:
                if self.video_cap.isOpened():
                    self.video_cap.release()
            except Exception as e:
                logger.error(f"Error during video capture cleanup: {e}")
            self.video_cap = None

        try:
            self.pa.terminate()
        except Exception as e:
            logger.error(f"Error terminating PyAudio: {e}")

        # Best-effort server-side cleanup
        try:
            self.disconnect_ws_session()
        except Exception as e:
            logger.error(f"Error disconnecting websocket session: {e}")

        logger.info("Client cleaned up")

    def stop(self):
        """Signal the client to shut down gracefully."""
        self._shutdown_event.set()
