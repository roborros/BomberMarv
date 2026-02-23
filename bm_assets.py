"""Runtime asset loading (images) after pygame init."""

import pygame


def load_images():
    return {
        "quad_damage_image": pygame.image.load('img\\qd.png'),
        "fire_powerup_image": pygame.image.load('img\\fireup.png'),
        "blast_image": pygame.image.load('img\\blast.png'),
        "blast_image_qd": pygame.image.load('img\\blast_qd.png'),
        "blast_centre_image": pygame.image.load('img\\blast_centre.png'),
        "blast_centre_image_qd": pygame.image.load('img\\blast_centre_qd.png'),
        "logo_image": pygame.image.load('img\\logo.png'),
    }
