import threading
import json
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, Protocol, runtime_checkable
import numpy as np
import logging

from .audio import AudioConsumer

logger = logging.getLogger("EvaSharedWakeWord")

class WakeWordEvent:
    def __init__(self, keyword: str, confidence: float = 1.0, metadata: Optional[Dict[str, Any]] = None):
        self.keyword = keyword
        self.confidence = confidence
        self.metadata = metadata or {}

class WakeWordEngine(Protocol):
    def start(self) -> None:
        """
        Start the wake word detection engine.
        Can be overridden by engines that need explicit startup (e.g. threads, hardware init).
        """
        ...

    def stop(self) -> None:
        """
        Stop the wake word detection engine.
        Can be overridden by engines that need explicit teardown.
        """
        ...

    def set_callback(self, callback: Callable[[WakeWordEvent], None]) -> None:
        """
        Set the callback to be invoked when a wake word is detected.
        """
        ...

class VoskWakeWordEngine(WakeWordEngine, AudioConsumer):
    def __init__(
        self,
        wake_word: str,
        model_path: Optional[str] = None,
        sample_rate: int = 16000,
    ):
        self.wake_word = wake_word
        self.model_path = model_path
        self.sample_rate = sample_rate
        
        self.on_detected: Optional[Callable[[WakeWordEvent], None]] = None

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._audio_buffer: List[np.ndarray] = []
        self._buffer_lock = threading.Lock()
        self._data_event = threading.Event()
        self._available = False

        self._init_vosk()

    def set_callback(self, callback: Callable[[WakeWordEvent], None]) -> None:
        self.on_detected = callback

    def _init_vosk(self):
        try:
            from vosk import Model
            self._vosk_model_class = Model
            self._available = True
            logger.info(f"[WakeWord] VOSK engine loaded, wake word: '{self.wake_word}'")
        except ImportError:
            logger.warning("[WakeWord] vosk not installed. Install with: pip install vosk")
            self._vosk_model_class = None

    def _ensure_vosk_model(self) -> Optional[str]:
        if self.model_path:
            return self.model_path

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

    def add_audio_frame(self, pcm_data: bytes, sample_rate: int, channels: int) -> None:
        if not self._running:
            return

        audio_data = np.frombuffer(pcm_data, dtype=np.int16)

        if channels > 1:
            # Simple downmix by dropping extra channels
            audio_data = audio_data[::channels]

        if sample_rate != self.sample_rate:
            if sample_rate % self.sample_rate == 0:
                # Simple decimation
                ratio = sample_rate // self.sample_rate
                audio_data = audio_data[::ratio]
            else:
                if not getattr(self, "_warned_sr", False):
                    logger.warning(f"[WakeWord] Audio sample rate {sample_rate} differs from VOSK expected {self.sample_rate} and cannot be easily decimated. Wake word detection might fail.")
                    self._warned_sr = True
        with self._buffer_lock:
            self._audio_buffer.append(audio_data)
            max_samples = self.sample_rate * 2
            total_samples = sum(len(frame) for frame in self._audio_buffer)
            while total_samples > max_samples and self._audio_buffer:
                removed = self._audio_buffer.pop(0)
                total_samples -= len(removed)
        self._data_event.set()

    def start(self):
        if not self._available:
            logger.warning("[WakeWord] Cannot start: VOSK not available")
            return

        self._running = True
        self._thread = threading.Thread(target=self._vosk_detection_loop, daemon=True)
        self._thread.start()
        logger.info("[WakeWord] Detection started (engine=vosk)")

    def stop(self):
        self._running = False
        self._data_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        logger.info("[WakeWord] Detection stopped")

    def _vosk_detection_loop(self):
        try:
            model_path = self._ensure_vosk_model()
            if not model_path:
                logger.error("[WakeWord] No VOSK model available, stopping detection")
                self._running = False
                return

            from vosk import KaldiRecognizer
            import vosk
            vosk.SetLogLevel(-1)

            model = self._vosk_model_class(model_path)
            recognizer = KaldiRecognizer(model, self.sample_rate)

            logger.info(f"[WakeWord] VOSK recognizer ready, listening for '{self.wake_word}'")

            while self._running:
                self._data_event.wait(timeout=0.1)
                self._data_event.clear()

                with self._buffer_lock:
                    if not self._audio_buffer:
                        continue
                    audio = np.concatenate(self._audio_buffer)
                    self._audio_buffer.clear()

                audio_bytes = audio.astype(np.int16).tobytes()
                chunk_size = self.sample_rate * 2 * 2 
                for i in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[i:i + chunk_size]

                    if recognizer.AcceptWaveform(chunk):
                        result = json.loads(recognizer.Result())
                        text = result.get("text", "").replace(" ", "")
                        if text:
                            logger.debug(f"[WakeWord] Recognized: '{text}'")

                        if self.wake_word in text:
                            logger.info(f"[WakeWord] Detected! '{self.wake_word}' found in '{text}'")
                            if self.on_detected:
                                self.on_detected(WakeWordEvent(keyword=self.wake_word, metadata={"text": text}))
                    else:
                        partial = json.loads(recognizer.PartialResult())
                        partial_text = partial.get("partial", "").replace(" ", "")
                        if partial_text and self.wake_word in partial_text:
                            logger.info(f"[WakeWord] Detected (partial)! '{self.wake_word}' in '{partial_text}'")
                            if self.on_detected:
                                self.on_detected(WakeWordEvent(keyword=self.wake_word, metadata={"partial": partial_text}))
                            recognizer.Reset()

        except Exception as e:
            logger.error(f"[WakeWord] VOSK detection loop error: {e}")
        finally:
            logger.info("[WakeWord] VOSK detection loop ended")
