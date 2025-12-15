import asyncio
import logging
import requests
import numpy as np
import pyaudio
import queue
import cv2
from livekit import rtc

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - [%(name)s] %(levelname)s - %(message)s"
)
logger = logging.getLogger("EvaClient")


class AudioOutputBuffer:
    """
    Streaming buffer designed to handle the impedance mismatch between
    fixed-size network packets and variable-size hardware callback requests.
    """

    def __init__(self):
        self.queue = queue.Queue(maxsize=200)
        self.remainder = None

    def put(self, data: bytes):
        """
        Converts raw bytes to a numpy array and pushes it into the thread-safe queue.
        """
        np_data = np.frombuffer(data, dtype=np.int16)
        self.queue.put(np_data)

    def get_chunk(self, frames_needed):
        """
        Retrieves the exact number of frames requested by the hardware.
        Returns data as bytes.
        """
        out_list = []
        frames_collected = 0

        # 1. Process data remaining from the previous callback, if any
        if self.remainder is not None:
            n = len(self.remainder)
            if n > frames_needed:
                # Remainder is larger than needed; take what is required and save the rest
                out_list.append(self.remainder[:frames_needed])
                self.remainder = self.remainder[frames_needed:]
                return np.concatenate(out_list).tobytes()
            else:
                # Remainder is smaller or equal; consume it entirely
                out_list.append(self.remainder)
                frames_collected += n
                self.remainder = None

        # 2. Fetch new packets from the queue until the required frame count is met
        while frames_collected < frames_needed:
            try:
                new_packet = self.queue.get_nowait()

                # Ensure shape consistency
                packet_len = len(new_packet)
                needed = frames_needed - frames_collected

                if packet_len > needed:
                    # Packet is larger than remaining space; slice and save overflow
                    out_list.append(new_packet[:needed])
                    self.remainder = new_packet[needed:]
                    frames_collected += needed
                else:
                    # Packet fits entirely
                    out_list.append(new_packet)
                    frames_collected += packet_len

            except queue.Empty:
                # Queue is empty; fill with silence to prevent hardware underrun artifacts
                needed = frames_needed - frames_collected
                silence = np.zeros(needed, dtype=np.int16)
                out_list.append(silence)
                frames_collected += needed

        # Concatenate all segments and convert back to bytes for PyAudio
        return np.concatenate(out_list).tobytes()


class EvaClient:
    """
    Initializes the Eva client.

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
        mic_channels (int, optional): 
            Number of microphone input channels. Defaults to 1.
        spk_channels (int, optional): 
            Number of speaker output channels. Defaults to 1.
        frame_size_ms (int, optional): 
            Duration of a single audio frame in milliseconds. Defaults to 60ms.
        camera_index (int, optional): 
            Index of the camera device (usually 0 for /dev/video0). Defaults to 0.
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
    """
    def __init__(
        self,
        api_key,
        mic_index=0,
        spk_index=0,
        mic_sample_rate=48000,
        spk_sample_rate=48000,
        mic_channels=1,
        spk_channels=1,
        frame_size_ms=60,
        camera_index=0,
        video_width=640,
        video_height=480,
        video_fps=30,
        base_url="https://eva.autoarkai.com",
        wss_url="wss://rtc.autoarkai.com",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.wss_url = wss_url

        # Audio Configuration
        self.pa = pyaudio.PyAudio()
        self.mic_sample_rate = mic_sample_rate
        self.spk_sample_rate = spk_sample_rate
        self.mic_channels = mic_channels
        self.spk_channels = spk_channels
        self.frame_size_ms = frame_size_ms

        # Video Configuration
        self.camera_index = camera_index
        self.video_width = video_width
        self.video_height = video_height
        self.video_fps = video_fps

        # Resolve audio device indices
        self.mic_index = self._find_device_index(mic_index, input=True)
        self.spk_index = self._find_device_index(spk_index, input=False)

        if not all([self.base_url, self.wss_url, self.api_key]):
            raise ValueError("Missing required environment variables.")

        self.audio_buffer = AudioOutputBuffer()
        self.room = None
        self._shutdown_event = asyncio.Event()
        
        # Sources & Tracks
        self.mic_source = None
        self.video_source = None
        self.video_cap = None

        # PyAudio streams
        self.input_stream = None
        self.output_stream = None

    def _find_device_index(self, value, input=True):
        """
        Resolves the audio device index.
        """
        if value is None:
            return None
        
        if type(value) is str and value.strip() == "":
            return None

        try:
            return int(value)
        except ValueError:
            pass

        target = value.strip()
        count = self.pa.get_device_count()
        logger.info(f"Searching for audio device matching: '{target}'...")

        for i in range(count):
            info = self.pa.get_device_info_by_index(i)
            name = info.get("name", "")
            if input and info.get("maxInputChannels") == 0:
                continue
            if not input and info.get("maxOutputChannels") == 0:
                continue

            if target in name:
                logger.info(f"Found device '{name}' at index {i}")
                return i

        logger.warning(f"Device '{target}' not found. Using system default.")
        return None

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
        try:
            token = self.get_room_token()
        except Exception:
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

        logger.info(f"Connecting to {self.wss_url}")
        try:
            await self.room.connect(self.wss_url, token)
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return

        # Start Media Tasks
        mic_task = asyncio.create_task(self.publish_microphone())
        video_task = asyncio.create_task(self.publish_camera())

        await self._shutdown_event.wait()

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
        self.mic_source = rtc.AudioSource(self.mic_sample_rate, self.mic_channels)
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

        frames_per_buffer = int(self.mic_sample_rate * self.frame_size_ms / 1000)
        loop = asyncio.get_running_loop()

        # PyAudio Callback
        def mic_callback(in_data, frame_count, time_info, status):
            # in_data comes as bytes
            audio_frame = rtc.AudioFrame(
                data=in_data,
                sample_rate=self.mic_sample_rate,
                num_channels=self.mic_channels,
                samples_per_channel=frame_count,
            )
            asyncio.run_coroutine_threadsafe(
                self.mic_source.capture_frame(audio_frame), loop
            )
            return (None, pyaudio.paContinue)

        try:
            self.input_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.mic_channels,
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
            track, sample_rate=self.spk_sample_rate, num_channels=self.spk_channels
        )
        logger.info(
            f"Speaker stream started. Rate: {self.spk_sample_rate}, Index: {self.spk_index}"
        )

        frames_per_buffer = int(self.spk_sample_rate * self.frame_size_ms / 1000)

        # PyAudio Output Callback
        def spk_callback(in_data, frame_count, time_info, status):
            # Retrieve the exact number of bytes needed from the buffer
            data = self.audio_buffer.get_chunk(frame_count)
            return (data, pyaudio.paContinue)

        try:
            self.output_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.spk_channels,
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