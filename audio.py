"""
SigmaScope – Audio Engine
Callback-based audio playback using sounddevice + soundfile.
"""

import numpy as np
import soundfile as sf
import sounddevice as sd
from enum import Enum


class PlayState(Enum):
    STOPPED = 0
    PLAYING = 1
    PAUSED = 2


class AudioEngine:
    """Thread-safe audio playback engine with callback streaming."""

    def __init__(self):
        self._data = None
        self._samplerate = 44100
        self._channels = 2
        self._frame = 0
        self._volume = 0.7
        self._state = PlayState.STOPPED
        self._stream = None
        self._total_frames = 0
        self._filepath = None

    # ── Properties ──────────────────────────────────────────────

    @property
    def state(self):
        return self._state

    @property
    def samplerate(self):
        return self._samplerate

    # ── File I/O ────────────────────────────────────────────────

    def load(self, filepath: str) -> bool:
        """Load an audio file (WAV, FLAC, OGG, or MP3 if libsndfile supports it)."""
        self.stop()
        try:
            data, sr = sf.read(filepath, dtype="float32", always_2d=True)
            self._data = data
            self._samplerate = sr
            self._channels = data.shape[1]
            self._total_frames = data.shape[0]
            self._frame = 0
            self._filepath = filepath
            self._state = PlayState.STOPPED
            return True
        except Exception as e:
            print(f"[AudioEngine] Error loading '{filepath}': {e}")
            return False

    def is_loaded(self) -> bool:
        return self._data is not None

    # ── Playback Controls ───────────────────────────────────────

    def play(self):
        if self._data is None:
            return

        if self._state == PlayState.PAUSED:
            self._state = PlayState.PLAYING
            return

        # Restart from beginning if we reached the end
        if self._frame >= self._total_frames:
            self._frame = 0

        self._state = PlayState.PLAYING

        # Start a new stream if needed
        if self._stream is None or not self._stream.active:
            try:
                self._stream = sd.OutputStream(
                    samplerate=self._samplerate,
                    channels=self._channels,
                    dtype="float32",
                    callback=self._audio_callback,
                    blocksize=1024,
                )
                self._stream.start()
            except Exception as e:
                print(f"[AudioEngine] Stream error: {e}")
                self._state = PlayState.STOPPED

    def pause(self):
        if self._state == PlayState.PLAYING:
            self._state = PlayState.PAUSED

    def stop(self):
        self._state = PlayState.STOPPED
        self._frame = 0
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def seek(self, position: float):
        """Seek to normalized position (0.0 – 1.0)."""
        if self._data is None:
            return
        self._frame = int(position * self._total_frames)
        self._frame = max(0, min(self._frame, self._total_frames - 1))

    def set_volume(self, level: float):
        """Set playback volume (0.0 – 1.0)."""
        self._volume = max(0.0, min(1.0, level))

    # ── Position Queries ────────────────────────────────────────

    def get_position(self) -> float:
        """Current playback position in seconds."""
        if self._data is None:
            return 0.0
        return self._frame / self._samplerate

    def get_duration(self) -> float:
        """Total duration in seconds."""
        if self._data is None:
            return 0.0
        return self._total_frames / self._samplerate

    def get_progress(self) -> float:
        """Normalized playback progress (0.0 – 1.0)."""
        if self._total_frames == 0:
            return 0.0
        return self._frame / self._total_frames

    # ── Visualization Data ──────────────────────────────────────

    def get_current_chunk(self, size: int = 2048) -> np.ndarray:
        """Return a mono chunk of `size` samples centred on the playhead."""
        if self._data is None or self._frame == 0:
            return np.zeros(size, dtype=np.float32)

        end = self._frame
        start = max(0, end - size)
        chunk = self._data[start:end, 0] if self._data.ndim > 1 else self._data[start:end]

        if len(chunk) < size:
            padded = np.zeros(size, dtype=np.float32)
            padded[size - len(chunk):] = chunk
            return padded
        return chunk.copy()

    def get_stereo_chunk(self, size: int = 2048):
        """Return (L, R) float32 arrays of `size` samples.

        Uses the actual L/R channels if the file is stereo,
        otherwise synthesises a stereo pair from mono using a
        quarter-cycle delay (makes Lissajous / Polar readable).
        """
        if self._data is None or self._frame == 0:
            z = np.zeros(size, dtype=np.float32)
            return z, z.copy()

        end  = self._frame
        start = max(0, end - size)

        if self._channels >= 2:
            raw_l = self._data[start:end, 0]
            raw_r = self._data[start:end, 1]
        else:
            raw_l = self._data[start:end, 0] if self._data.ndim > 1 else self._data[start:end]
            raw_r = raw_l  # will synthesise below

        def _pad(arr):
            if len(arr) < size:
                p = np.zeros(size, dtype=np.float32)
                p[size - len(arr):] = arr
                return p
            return arr.copy().astype(np.float32)

        L = _pad(raw_l)
        if self._channels >= 2:
            R = _pad(raw_r)
        else:
            # Quarter-period delay gives a circular Lissajous for a sine wave
            delay = size // 4
            R = np.roll(L, delay)
        return L, R

    # ── Internal ────────────────────────────────────────────────

    def _audio_callback(self, outdata, frames, time_info, status):
        """sounddevice callback — runs on the audio thread."""
        if self._state != PlayState.PLAYING or self._data is None:
            outdata.fill(0)
            return

        start = self._frame
        end = start + frames

        if end >= self._total_frames:
            # Reached end of file
            valid = self._total_frames - start
            if valid > 0:
                outdata[:valid] = self._data[start : self._total_frames] * self._volume
            outdata[valid:] = 0
            self._frame = self._total_frames
            self._state = PlayState.STOPPED
        else:
            outdata[:] = self._data[start:end] * self._volume
            self._frame = end

    def cleanup(self):
        """Release resources."""
        self.stop()
        self._data = None
