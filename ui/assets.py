import pygame
from config import BASIC_ENEMIES_DIR, BOSSES_DIR, HERO_DIR, BACKGROUND_DIR, AUDIO_DIR
import random


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
    """Return dict mapping base filename stem to surface."""
    bg_map = {}
    for path in BACKGROUND_DIR.glob("*.png"):
        img = pygame.image.load(str(path)).convert()
        img = pygame.transform.smoothscale(img, (width, height))
        bg_map[path.stem.lower()] = img
    return bg_map


ROOM_BG_FALLBACK_KEYS = ["forest", "grass", "fey"]

ROOM_TYPE_TO_BG = {
    "entrance": ["forest", "grass"],
    "corridor": ["grass"],
    "enemy_lair": ["fey"],
    "treasure": ["fey"],
    "trap": ["grass"],
    "shrine": ["fey"],
    "locked": ["forest"],
    "boss_room": ["fey"],
}

def pick_background_for_room(room, backgrounds):
    rtype = room.get("type", "corridor")
    choices = ROOM_TYPE_TO_BG.get(rtype, ROOM_BG_FALLBACK_KEYS)
    random.shuffle(choices)
    for key in choices:
        surf = backgrounds.get(key)
        if surf:
            return surf
    # fallback any background
    if backgrounds:
        return next(iter(backgrounds.values()))
    return None

def load_ambient_loops():
    """Load ambient audio/music loops (long background tracks)."""
    loops = {}
    if not AUDIO_DIR.exists():
        return loops
    for path in AUDIO_DIR.glob("*.*"):
        if path.suffix.lower() not in {".wav", ".mp3", ".ogg"}:
            continue
        stem = path.stem.lower()
        # Heuristic: treat very short SFX-like names (footsteps, sword, success) as non-ambient
        if any(key in stem for key in ["footsteps","sword","success","slash"]):
            continue
        try:
            loops[stem] = pygame.mixer.Sound(str(path))
        except Exception:
            continue
    return loops

def load_sfx():
    """Load short sound effects (non-looping)."""
    sfx = {}
    if not AUDIO_DIR.exists():
        return sfx
    for path in AUDIO_DIR.glob("*.*"):
        if path.suffix.lower() not in {".wav", ".mp3", ".ogg"}:
            continue
        stem = path.stem.lower()
        if any(key in stem for key in ["footsteps","sword","success","slash","door"]):
            try:
                sfx[stem] = pygame.mixer.Sound(str(path))
            except Exception:
                pass
    return sfx

ROOM_TYPE_TO_LOOP_KEYS = {
    # Only musical / ambient loops here now; SFX removed
    "entrance": ["wizard-rider-enchanted-fantasy-orchestral-loop-379413"],
    "corridor": ["wizard-rider-enchanted-fantasy-orchestral-loop-379413"],
    "enemy_lair": ["wizard-rider-enchanted-fantasy-orchestral-loop-379413"],
    "treasure": ["wizard-rider-enchanted-fantasy-orchestral-loop-379413"],
    "trap": ["wizard-rider-enchanted-fantasy-orchestral-loop-379413"],
    "shrine": ["wizard-rider-enchanted-fantasy-orchestral-loop-379413"],
    "locked": ["wizard-rider-enchanted-fantasy-orchestral-loop-379413"],
    "boss_room": ["wizard-rider-enchanted-fantasy-orchestral-loop-379413"],
}

def pick_loop_for_room(room, loops):
    rtype = room.get("type", "corridor")
    keys = ROOM_TYPE_TO_LOOP_KEYS.get(rtype, [])
    for k in keys:
        snd = loops.get(k)
        if snd:
            return snd
    return None
