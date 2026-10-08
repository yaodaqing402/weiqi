"""落子等音效——用 numpy 合成，避免打包二进制音频资源。"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pygame

SAMPLE_RATE = 44100


def _envelope(n: int, attack: float = 0.005, decay: float = 0.12) -> np.ndarray:
    t = np.arange(n) / SAMPLE_RATE
    env = np.exp(-t / decay)
    a = int(attack * SAMPLE_RATE)
    if a > 0:
        env[:a] *= np.linspace(0, 1, a)
    return env


def _tone(freq: float, dur: float, vol: float = 0.5, decay: float = 0.12) -> np.ndarray:
    n = int(dur * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    wave = np.sin(2 * np.pi * freq * t)
    return wave * _envelope(n, decay=decay) * vol


def _click(dur: float = 0.09) -> np.ndarray:
    """木质“嗒”声：双频 + 少量噪声，快速衰减。"""
    n = int(dur * SAMPLE_RATE)
    env = _envelope(n, decay=0.045)
    t = np.arange(n) / SAMPLE_RATE
    body = 0.6 * np.sin(2 * np.pi * 620 * t) + 0.4 * np.sin(2 * np.pi * 1040 * t)
    noise = 0.25 * np.random.default_rng(7).standard_normal(n)
    return (body + noise) * env * 0.55


def _sequence(*tones: np.ndarray) -> np.ndarray:
    return np.concatenate(tones) if tones else np.zeros(1)


def _build_raw() -> Dict[str, np.ndarray]:
    return {
        "select": _tone(880, 0.06, 0.3, 0.04),
        "move": _click(0.09),
        "capture": _sequence(_click(0.06), _tone(180, 0.12, 0.5, 0.09)),
        "check": _sequence(_tone(1200, 0.09, 0.45, 0.06), _tone(1500, 0.12, 0.4, 0.08)),
        "win": _sequence(_tone(523, 0.12, 0.4), _tone(659, 0.12, 0.4), _tone(784, 0.18, 0.45)),
        "lose": _sequence(_tone(392, 0.16, 0.4), _tone(294, 0.24, 0.4, 0.2)),
        "button": _tone(660, 0.05, 0.25, 0.03),
        "promote": _sequence(_tone(659, 0.1, 0.4), _tone(784, 0.1, 0.4),
                             _tone(988, 0.1, 0.4), _tone(1319, 0.2, 0.45)),
    }


class SoundManager:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.ok = False
        self._sounds: Dict[str, pygame.mixer.Sound] = {}
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
            self._make()
            self.ok = True
        except (pygame.error, Exception):
            self.ok = False

    def _make(self) -> None:
        for name, wave in _build_raw().items():
            arr = np.clip(wave, -1.0, 1.0)
            data = (arr * 32767).astype(np.int16)
            stereo = np.column_stack((data, data))
            self._sounds[name] = pygame.sndarray.make_sound(np.ascontiguousarray(stereo))

    def play(self, name: str) -> None:
        if not self.enabled or not self.ok:
            return
        snd = self._sounds.get(name)
        if snd is not None:
            try:
                snd.play()
            except pygame.error:
                pass

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
