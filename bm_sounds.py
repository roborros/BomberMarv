import os
import random

import pygame

from bm_params import BIG_EXPLOSION_VOLUME, MOCNY_STRAL_VARIANTS
from bm_paths import resource_path

# Initialize the mixer module
pygame.mixer.init()

# Load the sound file
bonus_sound = pygame.mixer.Sound(resource_path("sounds", "pick-bonus.wav"))
explosion_sound = pygame.mixer.Sound(resource_path("sounds", "explosion_short.wav"))
explosion_sound_qd = pygame.mixer.Sound(resource_path("sounds", "explosion_short_qd.wav"))
death_sound = pygame.mixer.Sound(resource_path("sounds", "death.wav"))
qd_sound = pygame.mixer.Sound(resource_path("sounds", "quad_damage.mp3"))
mocny_stral_sounds = [
    pygame.mixer.Sound(resource_path("sounds", f"mocny_stral_{index}.mp3"))
    for index in range(1, MOCNY_STRAL_VARIANTS + 1)
]
mocny_stral_sound = mocny_stral_sounds[0]


def _load_voice(*filenames):
    """Prefer a dropped-in mp3, then the generated placeholder wav."""
    for name in filenames:
        path = resource_path("sounds", name)
        if os.path.isfile(path):
            return pygame.mixer.Sound(path)
    raise FileNotFoundError("Missing boss voice. Expected one of: " + ", ".join(filenames))


# BomberMarv's "Fresh meat!" line. An mp3 in sounds/ still wins if one is dropped in later.
fresh_meat_sound = _load_voice("fresh_meat.mp3", "fresh_meat.wav")

# Set the volume for the explosion sounds to a lower level
explosion_sound.set_volume(0.1)  # Set volume to 30%
bonus_sound.set_volume(0.1)  # Set volume to 30%
death_sound.set_volume(0.1)  # Set volume to 30%
for _mocny in mocny_stral_sounds:
    _mocny.set_volume(BIG_EXPLOSION_VOLUME)
fresh_meat_sound.set_volume(0.9)


def play_sound_event(event: dict) -> None:
    """Renderer-side audio playback for a single sound event announced by the backend."""
    if not isinstance(event, dict):
        return
    kind = str(event.get("type") or event.get("sound") or "")
    if kind in ("bonus", "countdown", "player_joined"):
        bonus_sound.play()
    elif kind == "explosion":
        explosion_sound.play()
    elif kind == "explosion_qd":
        explosion_sound_qd.play()
    elif kind == "death":
        death_sound.play()
    elif kind == "qd":
        qd_sound.play()
    elif kind == "fresh_meat":
        fresh_meat_sound.play()
    elif kind == "big_explosion":
        if mocny_stral_sounds:
            sound = random.choice(mocny_stral_sounds)
            try:
                vol = float(event.get("volume", BIG_EXPLOSION_VOLUME))
            except (TypeError, ValueError):
                vol = float(BIG_EXPLOSION_VOLUME)
            sound.set_volume(vol)
            sound.play()


def play_sound_events(events) -> None:
    """Renderer-side consumer that plays all sound events announced in a frame/state."""
    if not events:
        return
    for event in events:
        play_sound_event(event)

