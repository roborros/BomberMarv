import pygame

# Initialize the mixer module
pygame.mixer.init()

# Load the sound file
bonus_sound = pygame.mixer.Sound('sounds/pick-bonus.wav')
explosion_sound = pygame.mixer.Sound('sounds/explosion_short.wav')
explosion_sound_qd = pygame.mixer.Sound('sounds/explosion_short_qd.wav')
death_sound = pygame.mixer.Sound('sounds/death.wav')
qd_sound = pygame.mixer.Sound('sounds/quad_damage.mp3')
mocny_stral_sound = pygame.mixer.Sound('sounds/mocny_stral.mp3')

# Set the volume for the explosion sounds to a lower level
explosion_sound.set_volume(0.1)  # Set volume to 30%
bonus_sound.set_volume(0.1)  # Set volume to 30%
death_sound.set_volume(0.1)  # Set volume to 30%
mocny_stral_sound.set_volume(0.4)
