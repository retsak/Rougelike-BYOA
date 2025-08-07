from __future__ import annotations

"""Dungeon generation and helper utilities."""

import random
import re
from typing import Dict

from .data import ENEMIES, LOOT_TABLE, ROOM_TYPES

DICE_RE = re.compile(r"(\d+)d(\d+)")


def roll(expr: str | int) -> int:
    """Roll dice in NdM format or return integer directly."""
    if isinstance(expr, int):
        return expr
    n, sides = map(int, DICE_RE.fullmatch(expr).groups())
    return sum(random.randint(1, sides) for _ in range(n))


def deep_update(d: dict, u: dict) -> None:
    """Recursively update mapping ``d`` with values from ``u``."""
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            deep_update(d[k], v)
        else:
            d[k] = v


def cardinal_direction(from_xy, to_xy) -> str:
    dx = to_xy[0] - from_xy[0]
    dy = to_xy[1] - from_xy[1]
    if dy == -1:
        return "north"
    if dy == 1:
        return "south"
    if dx == 1:
        return "east"
    if dx == -1:
        return "west"
    return "unknown"


def generate_dungeon(seed: int, n_rooms: int = 12) -> Dict[str, dict]:
    """Generate a simple dungeon layout with enemies and loot."""
    random.seed(seed)
    rooms: Dict[str, dict] = {}
    for i in range(n_rooms):
        room_id = f"room_{i}"
        r_type = random.choice(ROOM_TYPES if i else ["entrance"])
        rooms[room_id] = {
            "type": r_type,
            "coords": (random.randint(0, 5), random.randint(0, 5)),
            "visited": False,
            "locked": r_type == "locked",
            "trap": r_type == "trap" and random.randint(0, 1),
            "enemies": [],
            "items": [],
        }
        if r_type in {"enemy_lair", "corridor"} and random.random() < 0.6:
            name = random.choice(list(ENEMIES)[:-1])  # exclude boss
            rooms[room_id]["enemies"].append({**ENEMIES[name], "name": name})
        if random.random() < 0.5:
            rooms[room_id]["items"].append(random.choice(LOOT_TABLE))
    boss_room = random.choice([rid for rid in rooms if rid != "room_0"])
    rooms[boss_room]["type"] = "boss_room"
    rooms[boss_room]["enemies"] = [{**ENEMIES["dungeon_boss"], "name": "dungeon_boss"}]
    rooms["room_0"]["visited"] = True
    return rooms


def generate_grid_dungeon(seed: int, grid_w: int = 6, grid_h: int = 6) -> Dict[str, dict]:
    """Generate a grid-based dungeon layout."""
    random.seed(seed)
    rooms: Dict[str, dict] = {}
    for y in range(grid_h):
        for x in range(grid_w):
            room_id = f"room_{y * grid_w + x}"
            r_type = random.choice(ROOM_TYPES if (x, y) != (0, 0) else ["entrance"])
            rooms[room_id] = {
                "type": r_type,
                "coords": (x, y),
                "visited": (x, y) == (0, 0),
                "locked": r_type == "locked",
                "trap": r_type == "trap" and random.randint(0, 1),
                "enemies": [],
                "items": [],
            }
            if r_type in {"enemy_lair", "corridor"} and random.random() < 0.6:
                name = random.choice(list(ENEMIES)[:-1])
                rooms[room_id]["enemies"].append({**ENEMIES[name], "name": name})
            if random.random() < 0.5:
                rooms[room_id]["items"].append(random.choice(LOOT_TABLE))
    boss_room = f"room_{grid_w * grid_h - 1}"
    rooms[boss_room]["type"] = "boss_room"
    rooms[boss_room]["enemies"] = [{**ENEMIES["dungeon_boss"], "name": "dungeon_boss"}]
    return rooms
