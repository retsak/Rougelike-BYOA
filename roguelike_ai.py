#!/usr/bin/env python
"""
roguelike_ai.py ─ Build‑Your‑Own‑Adventure Roguelike powered by OpenAI
=====================================================================
Library of game logic, data classes, and OpenAI integration for DungeonGPT.
All gameplay and UI should be handled in the client (e.g., roguelike_pygame.py).
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List
import openai

########################################################################
# 1. Helpers                                                           #
########################################################################
DICE_RE = re.compile(r"(\d+)d(\d+)")

def roll(expr: str | int) -> int:
    if isinstance(expr, int):
        return expr
    n, sides = map(int, DICE_RE.fullmatch(expr).groups())
    return sum(random.randint(1, sides) for _ in range(n))

def deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            deep_update(d[k], v)
        else:
            d[k] = v

########################################################################
# 2. Static Game Data                                                  #
########################################################################
ENEMIES = {
    "goblin":     {"hp": 8,  "str": 2, "dex": 2, "xp": 15, "loot": ["copper coin"]},
    "skeleton":   {"hp": 12, "str": 3, "dex": 1, "xp": 25, "loot": ["bone shard"]},
    "orc":        {"hp": 18, "str": 4, "dex": 1, "xp": 40, "loot": ["rusty axe"]},
    "slime":      {"hp": 6,  "str": 1, "dex": 3, "xp": 10, "loot": ["gelatin goop"]},
    "dungeon_boss": {"hp": 35, "str": 6, "dex": 3, "xp": 150, "loot": ["legendary sword"]},
}

LOOT_TABLE = ["health potion", "silver key", "torch", "old map piece", "leather boots"]
ROOM_TYPES = ["corridor", "treasure", "trap", "enemy_lair", "shrine", "boss_room", "locked"]

########################################################################
# 3. Data classes                                                      #
########################################################################
@dataclass
class Player:
    hp: int = 20
    str: int = 4
    dex: int = 3
    level: int = 1
    xp: int = 0
    inventory: List[str] = field(default_factory=list)
    location: str = "room_0"
    torch_lit: bool = False

    def is_alive(self) -> bool:
        return self.hp > 0

    def give_xp(self, amount: int):
        self.xp += amount
        while self.xp >= self.level * 100:
            self.xp -= self.level * 100
            self.level += 1
            self.hp += 5
            self.str += 1
            self.dex += 1
            print(f"*** You reach level {self.level}! Stats increased. ***")

@dataclass
class GameState:
    seed: int
    rooms: Dict[str, dict]
    player: Player
    turn: int = 0
    history: list = field(default_factory=list)  # Memory of actions/events

    def to_json(self):
        return json.dumps(asdict(self), indent=2)

    @staticmethod
    def from_json(txt: str) -> "GameState":
        d = json.loads(txt)
        return GameState(seed=d["seed"], rooms=d["rooms"], player=Player(**d["player"]), turn=d["turn"], history=d.get("history", []))

########################################################################
# 4. Dungeon Generation                                               #
########################################################################
def generate_dungeon(seed: int, n_rooms: int = 12) -> Dict[str, dict]:
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
        # Populate enemies/items
        if r_type in {"enemy_lair", "corridor"} and random.random() < 0.6:
            name = random.choice(list(ENEMIES)[:-1])  # exclude boss
            rooms[room_id]["enemies"].append({**ENEMIES[name], "name": name})
        if random.random() < 0.5:
            rooms[room_id]["items"].append(random.choice(LOOT_TABLE))
    # Ensure a boss room
    boss_room = random.choice([rid for rid in rooms if rid != "room_0"])
    rooms[boss_room]["type"] = "boss_room"
    rooms[boss_room]["enemies"] = [{**ENEMIES["dungeon_boss"], "name": "dungeon_boss"}]
    rooms["room_0"]["visited"] = True
    return rooms

########################################################################
# 5. OpenAI Narration Layer                                           #
########################################################################
RULES = {"core_stats": ["hp", "str", "dex", "level", "xp"], "dice": "d20", "actions": ["move", "look", "attack", "loot", "inventory", "use"], "engine_authority": "Always trust state_delta"}
SYSTEM_PROMPT = (
    "You are DungeonGPT, a classic Dungeons & Dragons Dungeon Master. "
    "Narrate the world, describe what the player sees, hears, and feels. "
    "Offer vivid choices, suggest actions, and roleplay NPCs. "
    "Always give the player clear directions and options. "
    "Keep track of the story so far. "
    "Return JSON with 'narrative' and 'state_delta'. Use vivid second-person. "
    "Never reveal dice rolls or hidden data. Rules: " + json.dumps(RULES)
)

def call_openai(state: GameState, cmd: str, model: str) -> dict:
    # Pass history as context for memory
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "state": asdict(state),
            "command": cmd,
            "history": state.history[-10:]  # Last 10 events for context
        })}
    ]
    resp = openai.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )
    content = resp.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"narrative": content, "state_delta": {}}

########################################################################
# 6. Engine Functions                                                 #
########################################################################
META_CMDS = {"/save", "/load", "/quit", "/exit", "/stats", "/inventory", "/look", "/loot", "/map", "/help"}

def handle_meta(cmd: str, state: GameState, save_file) -> bool:
    lc = cmd.lower()
    if lc in {"/quit", "/exit"}:
        print("Goodbye!")
        return True
    if lc == "/save" and save_file:
        save_file.write_text(state.to_json())
        print(f"[✓] Saved to {save_file}")
        return True
    if lc == "/load" and save_file:
        if save_file.exists():
            new = GameState.from_json(save_file.read_text())
            state.rooms, state.player, state.turn = new.rooms, new.player, new.turn
            print("[✓] Loaded.")
        else:
            print("[!] No save found.")
        return True
    if lc == "/stats":
        p = state.player
        print(f"HP {p.hp} STR {p.str} DEX {p.dex} LVL {p.level} XP {p.xp}/{p.level*100}\n")
        return True
    if lc == "/inventory":
        inv = state.player.inventory or ["(empty)"]
        print("Inventory: " + ", ".join(inv) + "\n")
        return True
    if lc == "/look":
        room = state.rooms[state.player.location]
        desc = f"You are in a {room['type'].replace('_',' ')}. "
        if room["enemies"]:
            desc += "Enemies: " + ", ".join(e["name"] for e in room["enemies"]) + ". "
        if room["items"]:
            desc += "Items: " + ", ".join(room["items"]) + ". "
        if room.get("locked"):
            desc += "A heavy lock bars further passage. "
        if room.get("trap"):
            desc += "(something feels dangerous here) "
        print(desc + "\n")
        return True
    if lc == "/loot":
        room = state.rooms[state.player.location]
        if room["items"]:
            state.player.inventory.extend(room["items"])
            print("You pick up: " + ", ".join(room["items"]) + "\n")
            room["items"] = []
        else:
            print("There is nothing to loot here.\n")
        return True
    if lc == "/map":
        grid = [['#' for _ in range(6)] for _ in range(6)]
        for room in state.rooms.values():
            x, y = room["coords"]
            if room["visited"]:
                grid[y][x] = '.'
        px, py = state.rooms[state.player.location]["coords"]
        grid[py][px] = '@'
        print("Dungeon Map:")
        for row in grid:
            print(' '.join(row))
        print("@ = you, . = visited, # = unexplored")
        return True
    if lc == "/help":
        print("""
Available commands:
  /help         Show this help message
  /look         Describe the current room
  /loot         Pick up all items in the room
  /inventory    Show your inventory
  /stats        Show your stats
  /map          Show a map of the dungeon
  /save         Save your game
  /load         Load your game
  /quit, /exit  Quit the game
""")
        return True
    return False

def handle_command(cmd: str, state: GameState, model: str, save_file=None) -> GameState:
    old_location = state.player.location if hasattr(state.player, 'location') else None
    if cmd.startswith("/"):
        if handle_meta(cmd, state, save_file):
            return state
        print("[!] Unknown command:", cmd)
        return state
    openai_resp = call_openai(state, cmd, model)
    narrative, state_delta = openai_resp["narrative"], openai_resp["state_delta"]
    # --- Memory: append to history ---
    state.history.append({"turn": state.turn, "command": cmd, "narrative": narrative})
    for k, v in state_delta.items():
        current = getattr(state, k)
        if isinstance(current, dict) and isinstance(v, dict):
            deep_update(current, v)
        else:
            setattr(state, k, v)
    # Robustly preserve player location unless explicitly changed
    if isinstance(state.player, dict):
        new_location = state.player.get('location', None)
        if not new_location:
            state.player['location'] = old_location
        state.player = Player(**state.player)
    elif hasattr(state.player, 'location') and not getattr(state.player, 'location', None):
        state.player.location = old_location
    print(narrative)
    return state
