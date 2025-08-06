import os
import pygame


def load_enemy_sprites():
    sprite_dict = {}
    basic_path = 'assets/basic enemies'
    for fname in os.listdir(basic_path):
        if fname.lower().endswith('.png'):
            img = pygame.image.load(os.path.join(basic_path, fname)).convert_alpha()
            img = pygame.transform.smoothscale(img, (48, 48))
            sprite_dict[fname[:-4]] = img
    boss_path = 'assets/bosses'
    if os.path.exists(boss_path):
        for fname in os.listdir(boss_path):
            if fname.lower().endswith('.png'):
                img = pygame.image.load(os.path.join(boss_path, fname)).convert_alpha()
                img = pygame.transform.smoothscale(img, (64, 64))
                sprite_dict[fname[:-4]] = img
                print("Loaded boss sprites:", [fname[:-4] for fname in os.listdir(boss_path) if fname.lower().endswith('.png')])
    return sprite_dict


def load_hero_sprites():
    hero_dict = {}
    hero_path = 'assets/Hero'
    for fname in os.listdir(hero_path):
        if fname.lower().endswith('.png'):
            img = pygame.image.load(os.path.join(hero_path, fname)).convert_alpha()
            img = pygame.transform.smoothscale(img, (64, 64))
            key = fname[:-4].replace("Rouge", "Rogue")
            hero_dict[key] = img
    return hero_dict


def load_backgrounds(width: int, height: int):
    bg_list = []
    bg_path = 'assets/Backgrounds'
    for fname in os.listdir(bg_path):
        if fname.lower().endswith('.png'):
            img = pygame.image.load(os.path.join(bg_path, fname)).convert()
            img = pygame.transform.smoothscale(img, (width, height))
            bg_list.append(img)
    return bg_list
