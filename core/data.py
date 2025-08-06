from __future__ import annotations

"""Static game data used by DungeonGPT."""

ENEMIES = {
    "goblin":     {"hp": 8,  "str": 2, "dex": 2, "xp": 15, "loot": ["copper coin"]},
    "skeleton":   {"hp": 12, "str": 3, "dex": 1, "xp": 25, "loot": ["bone shard"]},
    "orc":        {"hp": 18, "str": 4, "dex": 1, "xp": 40, "loot": ["rusty axe"]},
    "slime":      {"hp": 6,  "str": 1, "dex": 3, "xp": 10, "loot": ["gelatin goop"]},
    "dungeon_boss": {"hp": 35, "str": 6, "dex": 3, "xp": 150, "loot": ["legendary sword"]},
}

# Potential items that can appear in rooms
LOOT_TABLE = [
    "health potion",
    "silver key",
    "torch",
    "old map piece",
    "leather boots",
]

# Types of rooms that may be generated
# Note: "boss_room" is intentionally excluded; it is assigned explicitly
ROOM_TYPES = ["corridor", "treasure", "trap", "enemy_lair", "shrine", "locked"]
