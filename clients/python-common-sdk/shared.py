"""
Shared components for Eva clients (WebSocket and LiveKit).

This module contains reusable components that are shared between
different Eva client implementations.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Callable, List

import numpy as np
import pyaudio
import queue

logger = logging.getLogger("EvaShared")


class AudioOutputBuffer:
    """
    Streaming buffer designed to handle the impedance mismatch between
    fixed-size network packets and variable-size hardware callback requests.
    """

    def __init__(self, maxsize: int = 200):
        self.queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=maxsize)
        self.remainder = None

    def put(self, data: bytes):
        np_data = np.frombuffer(data, dtype=np.int16)
        try:
            self.queue.put_nowait(np_data)
        except queue.Full:
            # Drop oldest to prevent unbounded growth when speaker is slow
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait(np_data)
            except queue.Full:
                pass

    def get_chunk(self, frames_needed: int) -> bytes:
        out_list = []
        frames_collected = 0

        if self.remainder is not None:
            n = len(self.remainder)
            if n > frames_needed:
                out_list.append(self.remainder[:frames_needed])
                self.remainder = self.remainder[frames_needed:]
                return np.concatenate(out_list).tobytes()
            else:
                out_list.append(self.remainder)
                frames_collected += n
                self.remainder = None

        while frames_collected < frames_needed:
            try:
                new_packet = self.queue.get_nowait()
                packet_len = len(new_packet)
                needed = frames_needed - frames_collected

                if packet_len > needed:
                    out_list.append(new_packet[:needed])
                    self.remainder = new_packet[needed:]
                    frames_collected += needed
                else:
                    out_list.append(new_packet)
                    frames_collected += packet_len
            except queue.Empty:
                needed = frames_needed - frames_collected
                silence = np.zeros(needed, dtype=np.int16)
                out_list.append(silence)
                frames_collected += needed

        return np.concatenate(out_list).tobytes()


class TaskFSMState(Enum):
    """Task FSM states"""
    IDLE = auto()
    ACTIVE = auto()
    PENDING_SWITCH = auto()


import uuid

def wrap_rtvi_envelope(message: dict, topic: str = "task-ir-control") -> dict:
    """
    Wrap a control message in the RTVI standard envelope for transmission.
    This ensures compatibility with Pipecat's strict RTVIProcessor ingestion.
    """
    return {
        "label": "rtvi-ai",
        "type": "client-message",
        "id": f"msg-{uuid.uuid4().hex[:8]}",
        "data": {
            "t": topic,
            "d": message
        }
    }

def unwrap_rtvi_envelope(message: dict) -> dict:
    """
    Unwrap an RTVI envelope from Pipecat to get the raw payload.
    Compatible with both flat and encapsulated JSON structures.
    """
    if "label" in message and message.get("label") == "rtvi-ai":
        inner = message.get("data", message)
        # Handle the t/d schema if present
        if isinstance(inner, dict) and "d" in inner:
            return inner["d"]
        return inner
    return message


class TaskFSM:
    """
    Task Finite State Machine for client-side task state coordination.

    Handles bidirectional task switching protocol:
    - Client-initiated: requestSwitch() -> server approves/denies -> commit
    - Server-initiated: server sends advice -> client auto-commits if confidence > 0.8

    Maintains local revision counter and current task state.
    """

    def __init__(self, on_task_change: Optional[Callable[[str, str], None]] = None, auto_switch_confidence_threshold: float = 0.8):
        """
        Args:
            on_task_change: Callback(old_task, new_task) when task changes
            auto_switch_confidence_threshold: Confidence threshold for auto-switching tasks
        """
        self.state = TaskFSMState.IDLE
        self.current_task: Optional[str] = None
        self.pending_task: Optional[str] = None
        self.revision = 0
        self.allowed_tasks: List[str] = []
        self._on_task_change = on_task_change
        self.auto_switch_confidence_threshold = auto_switch_confidence_threshold
        self._lock = threading.Lock()

    def handle_message(self, raw_message: dict):
        """
        Process incoming server message.

        Handles:
        - task.switch.advice: Server suggests task switch
        - task.switch.result: Server responds to client's request
        - system_config: Server sends allowed tasks list
        """
        # Always attempt to unwrap the RTVI envelope first
        message = unwrap_rtvi_envelope(raw_message)
        
        msg_type = message.get("type", "unknown")

        # Handle system_config
        if msg_type == "system_config":
            self._handle_system_config(message)
            return None

        # Handle task.switch.result (has "approved" field)
        if msg_type == "task.switch.result" or "approved" in message:
            return self._handle_switch_result(message)

        # Handle task.switch.advice (has "suggested_task" field)
        if msg_type == "task.switch.advice" or "suggested_task" in message:
            return self._handle_switch_advice(message)

        return None

    def _handle_system_config(self, config: dict):
        """Update allowed tasks list from server"""
        with self._lock:
            self.allowed_tasks = config.get("valid_tasks", [])
            logger.info(f"[TaskFSM] SystemConfig updated. Allowed tasks: {self.allowed_tasks}")

    def _handle_switch_result(self, result: dict):
        """Handle server's approval/denial of client's switch request"""
        approved = result.get("approved", False)
        reason = result.get("reason", "")
        command_id = result.get("id", "")

        notify_callback = False
        old_task = None
        new_task = None
        ret_val = None

        with self._lock:
            if approved:
                old_task = self.current_task

                # Switch to pending task
                self.current_task = self.pending_task
                self.state = TaskFSMState.ACTIVE
                self.revision += 1
                self.pending_task = None
                new_task = self.current_task

                logger.info(f"[TaskFSM] Switch approved: {old_task} -> {self.current_task} (revision {self.revision})")

                if self._on_task_change and old_task != self.current_task:
                    notify_callback = True

                # Return the message for commit (caller will send it)
                ret_val = {
                    "type": "task.switch.commit",
                    "id": f"commit_{uuid.uuid4().hex[:8]}",
                    "final_task": self.current_task,
                    "revision": self.revision,
                    "ref_source": "edge_command",
                    "ref_id": command_id
                }
            else:
                # Switch denied
                self.state = TaskFSMState.ACTIVE if self.current_task else TaskFSMState.IDLE
                self.pending_task = None
                logger.info(f"[TaskFSM] Switch denied: {reason}")
                ret_val = None

        if notify_callback:
            try:
                self._on_task_change(old_task or "", new_task or "")
            except Exception as e:
                logger.error(f"[TaskFSM] Error in task change callback: {e}")

        return ret_val

    def _handle_switch_advice(self, advice: dict):
        """Handle server's task switch suggestion"""
        suggested_task = advice.get("suggested_task", "")
        confidence = advice.get("confidence", 0.0)
        advice_id = advice.get("id", "")

        logger.info(f"[TaskFSM] Received advice: {suggested_task} (confidence: {confidence:.2f})")

        # Auto-switch based on confidence threshold
        if confidence > self.auto_switch_confidence_threshold:
            notify_callback = False
            old_task = None
            new_task = None
            ret_val = None

            with self._lock:
                old_task = self.current_task
                self.current_task = suggested_task
                self.state = TaskFSMState.ACTIVE
                self.revision += 1
                new_task = self.current_task

                logger.info(f"[TaskFSM] Auto-switch triggered: {old_task} -> {self.current_task} (revision {self.revision})")

                if self._on_task_change and old_task != self.current_task:
                    notify_callback = True

                # Return the message for commit (caller will send it)
                ret_val = {
                    "type": "task.switch.commit",
                    "id": f"commit_{uuid.uuid4().hex[:8]}",
                    "final_task": self.current_task,
                    "revision": self.revision,
                    "ref_source": "advice",
                    "ref_id": advice_id
                }

            if notify_callback:
                try:
                    self._on_task_change(old_task or "", new_task or "")
                except Exception as e:
                    logger.error(f"[TaskFSM] Error in task change callback: {e}")

            return ret_val
        return None

    def request_switch(self, target_task: str, reason: str = "User Request") -> Optional[dict]:
        """
        Request a task switch.

        Args:
            target_task: Target task name
            reason: Reason for the switch

        Returns:
            Command message dict to send, or None if request is invalid
        """
        with self._lock:
            # Check if task is allowed
            if self.allowed_tasks and target_task not in self.allowed_tasks:
                logger.warning(f"[TaskFSM] Switch to {target_task} denied: not in allowed tasks")
                return None

            # Build command
            command = {
                "type": "task.switch.command",
                "id": f"cmd_{uuid.uuid4().hex[:8]}",
                "from_task": self.current_task or "",
                "to_task": target_task,
                "reason": reason,
                "revision": self.revision
            }

            # Update state
            self.pending_task = target_task
            self.state = TaskFSMState.PENDING_SWITCH

            logger.info(f"[TaskFSM] Requested switch to {target_task}, state: PENDING_SWITCH")
            return command

    def initialize(self, initial_task: str):
        """Initialize FSM with the first task"""
        with self._lock:
            self.current_task = initial_task
            self.state = TaskFSMState.ACTIVE
            logger.info(f"[TaskFSM] Initialized with task: {initial_task}")


class WakeWordRunner:
    """
    Background wake word detector.

    Uses VOSK engine: Full speech recognition + text matching, supports Chinese.

    Runs in a separate thread, continuously listening to microphone audio.
    When wake word is detected, triggers a callback (typically to request task switch).
    """

    def __init__(
        self,
        wake_word: str,
        on_detected: Callable[[], None],
        model_path: Optional[str] = None,
        sample_rate: int = 16000,
    ):
        """
        Args:
            wake_word: Wake word text to detect (e.g., "你好方舟")
            on_detected: Callback function when wake word is detected
            model_path: Path to model. For VOSK: directory path (e.g., "vosk-model-small-cn-0.22").
                        If None, will auto-download a small Chinese model.
            sample_rate: Audio sample rate (default 16000)
        """
        self.wake_word = wake_word
        self.on_detected = on_detected
        self.model_path = model_path
        self.sample_rate = sample_rate

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._audio_buffer: List[np.ndarray] = []
        self._buffer_lock = threading.Lock()
        self._data_event = threading.Event()
        self._available = False

        self._init_vosk()

    def _init_vosk(self):
        """Initialize VOSK engine"""
        try:
            from vosk import Model
            self._vosk_model_class = Model
            self._available = True
            logger.info(f"[WakeWord] VOSK engine loaded, wake word: '{self.wake_word}'")
        except ImportError:
            logger.warning("[WakeWord] vosk not installed. Install with: pip install vosk")
            self._vosk_model_class = None

    def _ensure_vosk_model(self) -> Optional[str]:
        """Ensure VOSK model is available, download if needed. Returns model path."""
        if self.model_path:
            return self.model_path

        # Auto-download small Chinese model
        model_name = "vosk-model-small-cn-0.22"
        cache_dir = Path.home() / ".cache" / "eva_ws_client"
        model_dir = cache_dir / model_name

        if model_dir.exists():
            return str(model_dir)

        cache_dir.mkdir(parents=True, exist_ok=True)
        url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
        zip_path = cache_dir / f"{model_name}.zip"

        logger.info(f"[WakeWord] Downloading VOSK model: {model_name} (~50MB)...")
        try:
            import urllib.request
            urllib.request.urlretrieve(url, str(zip_path))

            logger.info("[WakeWord] Extracting model...")
            import zipfile
            with zipfile.ZipFile(str(zip_path), 'r') as zf:
                zf.extractall(str(cache_dir))
            zip_path.unlink()

            logger.info(f"[WakeWord] Model ready at: {model_dir}")
            return str(model_dir)
        except Exception as e:
            logger.error(f"[WakeWord] Failed to download VOSK model: {e}")
            return None

    def add_audio_frame(self, audio_data: np.ndarray):
        """
        Add audio frame to buffer for wake word detection.

        Args:
            audio_data: int16 PCM audio data (mono, 16kHz)
        """
        if not self._running:
            return

        with self._buffer_lock:
            self._audio_buffer.append(audio_data)
            # Keep only last 2 seconds of audio (32000 samples at 16kHz)
            max_samples = self.sample_rate * 2
            total_samples = sum(len(frame) for frame in self._audio_buffer)
            while total_samples > max_samples and self._audio_buffer:
                removed = self._audio_buffer.pop(0)
                total_samples -= len(removed)
        self._data_event.set()

    def start(self):
        """Start wake word detection in background thread"""
        if not self._available:
            logger.warning("[WakeWord] Cannot start: VOSK not available")
            return

        self._running = True
        self._thread = threading.Thread(target=self._vosk_detection_loop, daemon=True)
        self._thread.start()
        logger.info("[WakeWord] Detection started (engine=vosk)")

    def stop(self):
        """Stop wake word detection"""
        self._running = False
        self._data_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        logger.info("[WakeWord] Detection stopped")

    def _vosk_detection_loop(self):
        """VOSK-based detection: continuous speech recognition + text matching"""
        try:
            model_path = self._ensure_vosk_model()
            if not model_path:
                logger.error("[WakeWord] No VOSK model available, stopping detection")
                self._running = False
                return

            from vosk import KaldiRecognizer

            # Suppress VOSK's verbose logging
            import vosk
            vosk.SetLogLevel(-1)

            model = self._vosk_model_class(model_path)
            recognizer = KaldiRecognizer(model, self.sample_rate)

            logger.info(f"[WakeWord] VOSK recognizer ready, listening for '{self.wake_word}'")

            while self._running:
                # Wait for data or wake up periodically
                self._data_event.wait(timeout=0.1)
                self._data_event.clear()

                # Collect audio from buffer
                with self._buffer_lock:
                    if not self._audio_buffer:
                        continue
                    audio = np.concatenate(self._audio_buffer)
                    self._audio_buffer.clear()

                # Feed to recognizer (expects raw bytes)
                audio_bytes = audio.astype(np.int16).tobytes()

                # Process in chunks to avoid blocking
                chunk_size = self.sample_rate * 2 * 2  # 1 second of int16 audio = 32000 bytes
                for i in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[i:i + chunk_size]

                    if recognizer.AcceptWaveform(chunk):
                        # Complete utterance recognized
                        result = json.loads(recognizer.Result())
                        text = result.get("text", "").replace(" ", "")

                        if text:
                            logger.debug(f"[WakeWord] Recognized: '{text}'")

                        if self.wake_word in text:
                            logger.info(
                                f"[WakeWord] Detected! '{self.wake_word}' found in '{text}'"
                            )
                            if self.on_detected:
                                self.on_detected()
                    else:
                        # Partial result (for real-time feedback, optional)
                        partial = json.loads(recognizer.PartialResult())
                        partial_text = partial.get("partial", "").replace(" ", "")
                        if partial_text and self.wake_word in partial_text:
                            logger.info(
                                f"[WakeWord] Detected (partial)! '{self.wake_word}' in '{partial_text}'"
                            )
                            if self.on_detected:
                                self.on_detected()
                            # Reset recognizer to avoid duplicate detection
                            recognizer.Reset()

        except Exception as e:
            logger.error(f"[WakeWord] VOSK detection loop error: {e}")
        finally:
            logger.info("[WakeWord] VOSK detection loop ended")




def find_audio_device_index(pa: pyaudio.PyAudio, value, is_input: bool = True) -> Optional[int]:
    """
    Find audio device index by name or index.

    Args:
        pa: PyAudio instance
        value: Device index (int) or name substring (str)
        is_input: True for input devices, False for output devices

    Returns:
        Device index, or None if not found (use system default)
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        pass

    target = str(value).strip()
    count = pa.get_device_count()
    for i in range(count):
        info = pa.get_device_info_by_index(i)
        name = info.get("name", "")
        if is_input and info.get("maxInputChannels", 0) == 0:
            continue
        if not is_input and info.get("maxOutputChannels", 0) == 0:
            continue
        if target in name:
            return i
    logger.warning(f"Audio device '{target}' not found, using system default")
    return None
