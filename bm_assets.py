"""Runtime asset loading (images) after pygame init."""

import pygame

from bm_paths import resource_path


def load_images():
    return {
        "quad_damage_image": pygame.image.load(resource_path("img", "qd.png")),
        "fire_powerup_image": pygame.image.load(resource_path("img", "fireup.png")),
        "blast_image": pygame.image.load(resource_path("img", "blast.png")),
        "blast_image_qd": pygame.image.load(resource_path("img", "blast_qd.png")),
        "blast_centre_image": pygame.image.load(resource_path("img", "blast_centre.png")),
        "blast_centre_image_qd": pygame.image.load(resource_path("img", "blast_centre_qd.png")),
        "logo_image": pygame.image.load(resource_path("img", "logo.png")),
    }
