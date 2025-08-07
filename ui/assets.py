import pygame
from config import BASIC_ENEMIES_DIR, BOSSES_DIR, HERO_DIR, BACKGROUND_DIR


def load_enemy_sprites():
    sprite_dict = {}
    for path in BASIC_ENEMIES_DIR.glob("*.png"):
        img = pygame.image.load(str(path)).convert_alpha()
        img = pygame.transform.smoothscale(img, (48, 48))
        sprite_dict[path.stem] = img
    if BOSSES_DIR.exists():
        boss_files = list(BOSSES_DIR.glob("*.png"))
        for path in boss_files:
            img = pygame.image.load(str(path)).convert_alpha()
            img = pygame.transform.smoothscale(img, (64, 64))
            sprite_dict[path.stem] = img
        print("Loaded boss sprites:", [p.stem for p in boss_files])
    return sprite_dict


def load_hero_sprites():
    hero_dict = {}
    for path in HERO_DIR.glob("*.png"):
        img = pygame.image.load(str(path)).convert_alpha()
        img = pygame.transform.smoothscale(img, (64, 64))
        key = path.stem.replace("Rouge", "Rogue")
        hero_dict[key] = img
    return hero_dict


def load_backgrounds(width, height):
    bg_list = []
    for path in BACKGROUND_DIR.glob("*.png"):
        img = pygame.image.load(str(path)).convert()
        img = pygame.transform.smoothscale(img, (width, height))
        bg_list.append(img)
    return bg_list
