import queue
import numpy as np
import pyaudio
import logging
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger("EvaSharedAudio")

@runtime_checkable
class AudioConsumer(Protocol):
    def add_audio_frame(self, pcm_data: bytes, sample_rate: int, channels: int) -> None:
        """
        Feed audio data to the consumer.
        """
        ...

class AudioOutputBuffer:
    def __init__(self, maxsize: int = 200):
        self.queue: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=maxsize)
        self.remainder = None

    def put(self, data: bytes):
        np_data = np.frombuffer(data, dtype=np.int16)
        try:
            self.queue.put_nowait(np_data)
        except queue.Full:
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

def find_audio_device_index(pa: pyaudio.PyAudio, value, is_input: bool = True) -> Optional[int]:
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
