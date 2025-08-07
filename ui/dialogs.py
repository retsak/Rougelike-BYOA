"""Dialog utilities for the UI layer."""

import pygame
import sys

# Mapping of hero names to stat blocks and abilities
HERO_STATS = {
    "Cleric": {"hp": 25, "str": 4, "dex": 3, "ability": "heal"},
    "Dragon": {"hp": 35, "str": 8, "dex": 2, "ability": "fire_breath"},
    "Fighter": {"hp": 30, "str": 6, "dex": 3, "ability": "power_strike"},
    "Knight": {"hp": 28, "str": 5, "dex": 4, "ability": "shield_block"},
    "Rogue": {"hp": 22, "str": 4, "dex": 6, "ability": "backstab"},
    "Toad": {"hp": 18, "str": 3, "dex": 5, "ability": "tongue_whip"},
}


def select_hero(screen, hero_sprites, font, output_font, width, height):
    """Display a hero selection dialog and return the chosen hero key."""
    dialog_w, dialog_h = 700, 320
    dialog_x = (width - dialog_w) // 2
    dialog_y = (height - dialog_h) // 2
    dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_w, dialog_h)
    pygame.draw.rect(screen, (30, 30, 60), dialog_rect, border_radius=18)
    pygame.draw.rect(screen, (200, 200, 255), dialog_rect, 4, border_radius=18)
    title = font.render("Choose Your Hero", True, (255, 255, 255))
    screen.blit(title, (dialog_x + dialog_w // 2 - title.get_width() // 2, dialog_y + 24))
    hero_keys = list(hero_sprites.keys())
    spacing = dialog_w // max(1, len(hero_keys))
    btn_rects = []
    for i, key in enumerate(hero_keys):
        img = hero_sprites[key]
        img_rect = img.get_rect(center=(dialog_x + spacing // 2 + i * spacing, dialog_y + 120))
        screen.blit(img, img_rect)
        label = output_font.render(key.title(), True, (255, 255, 255))
        screen.blit(label, (img_rect.centerx - label.get_width() // 2, img_rect.bottom + 8))
        btn_rects.append(img_rect)
    pygame.display.flip()
    selecting = True
    selected_key = None
    while selecting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pygame.mouse.get_pos()
                for i, rect in enumerate(btn_rects):
                    if rect.collidepoint(mx, my):
                        selected_key = hero_keys[i]
                        selecting = False
    return selected_key


def game_over_dialog(screen, font, output_font, width, height):
    """Display a game over dialog and return the chosen action."""
    dialog_w, dialog_h = 480, 220
    dialog_x = (width - dialog_w) // 2
    dialog_y = (height - dialog_h) // 2
    dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_w, dialog_h)
    pygame.draw.rect(screen, (40, 0, 0), dialog_rect, border_radius=18)
    pygame.draw.rect(screen, (255, 80, 80), dialog_rect, 4, border_radius=18)
    title = font.render("Game Over!", True, (255, 255, 255))
    screen.blit(title, (dialog_x + dialog_w // 2 - title.get_width() // 2, dialog_y + 32))
    msg = output_font.render("You have perished in the dungeon.", True, (255, 200, 200))
    screen.blit(msg, (dialog_x + dialog_w // 2 - msg.get_width() // 2, dialog_y + 80))
    btns = []
    btn_labels = ["Play Again", "Exit"]
    for i, label in enumerate(btn_labels):
        btn_w, btn_h = 180, 48
        btn_rect = pygame.Rect(dialog_x + 40 + i * 220, dialog_y + dialog_h - btn_h - 32, btn_w, btn_h)
        pygame.draw.rect(screen, (60, 60, 120), btn_rect, border_radius=12)
        pygame.draw.rect(screen, (120, 120, 200), btn_rect, 2, border_radius=12)
        btn_txt = font.render(label, True, (255, 255, 255))
        screen.blit(btn_txt, (btn_rect.centerx - btn_txt.get_width() // 2, btn_rect.centery - btn_txt.get_height() // 2))
        btns.append((btn_rect, label))
    pygame.display.flip()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pygame.mouse.get_pos()
                for btn_rect, label in btns:
                    if btn_rect.collidepoint(mx, my):
                        return "play_again" if label == "Play Again" else "exit"
