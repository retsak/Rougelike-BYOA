"""Grid-based dungeon generation utilities."""

from __future__ import annotations

import random
from typing import Dict

from .data import ENEMIES, LOOT_TABLE, ROOM_TYPES


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

