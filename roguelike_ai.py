#!/usr/bin/env python
"""
roguelike_ai.py ─ Build‑Your‑Own‑Adventure Roguelike powered by OpenAI
=====================================================================
🎲 **v0.3.1 PATCH** – Optional `--key`
------------------------------------
* **Auth flexibility**: Supply `--key YOUR_API_KEY` *or* rely on the `OPENAI_API_KEY` env‑var. If neither is set, the script will prompt you interactively instead of bailing out.
* Updated CLI help strings & README header.

```bash
# env‑var route (recommended)
export OPENAI_API_KEY=sk‑...
python roguelike_ai.py --seed 1337

# explicit CLI flag route
python roguelike_ai.py --key sk‑... --seed 1337
```
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import random
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

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

    def to_json(self):
        return json.dumps(asdict(self), indent=2)

    @staticmethod
    def from_json(txt: str) -> "GameState":
        d = json.loads(txt)
        return GameState(seed=d["seed"], rooms=d["rooms"], player=Player(**d["player"]), turn=d["turn"])

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
    "You are DungeonGPT, an impartial text dungeon master. "
    "Return JSON with 'narrative' and 'state_delta'. Use vivid second‑person. "
    "Never reveal dice rolls or hidden data. Rules: " + json.dumps(RULES)
)

def call_openai(state: GameState, cmd: str, model: str) -> dict:
    resp = openai.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"state": asdict(state), "command": cmd})}
        ],
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
META_CMDS = {"/save", "/load", "/quit", "/exit", "/stats", "/inventory", "/look", "/loot"}


def handle_meta(cmd: str, state: GameState, save_file: Path) -> bool:
    lc = cmd.lower()
    if lc in {"/quit", "/exit"}:
        print("Goodbye!")
        sys.exit(0)
    if lc == "/save":
        save_file.write_text(state.to_json())
        print(f"[✓] Saved to {save_file}")
        return True
    if lc == "/load":
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
    if lc == "/help":
        print("""
Available commands:
  /help         Show this help message
  /look         Describe the current room
  /loot         Pick up all items in the room
  /inventory    Show your inventory
  /stats        Show your stats
  /save         Save your game
  /load         Load your game
  /quit, /exit  Quit the game
""")
        return True
    return False

def handle_command(cmd: str, state: GameState, model: str, save_file: Path) -> GameState:
    if cmd.startswith("/"):
        if handle_meta(cmd, state, save_file):
            return state
        print("[!] Unknown command:", cmd)
        return state
    # Normal play command
    openai_resp = call_openai(state, cmd, model)
    narrative, state_delta = openai_resp["narrative"], openai_resp["state_delta"]
    # Update state
    for k, v in state_delta.items():
        if isinstance(getattr(state, k), dict):
            getattr(state, k).update(v)
        else:
            setattr(state, k, v)
    print(narrative)
    return state

########################################################################
# 7. CLI & Main Loop                                                  #
########################################################################
def print_intro():
    print(
        "🎲 Welcome to DungeonGPT! 🎲\n"
        "Build‑Your‑Own‑Adventure Roguelike powered by OpenAI.\n"
        "Type /help for commands.\n"
    )

def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", type=str, help="OpenAI API key")
    parser.add_argument("--model", type=str, default="gpt-4.1-mini", help="OpenAI model")
    parser.add_argument("--seed", type=int, default=random.randint(0, 2**32 - 1), help="Random seed")
    parser.add_argument("--load", type=Path, help="Save file to load")
    return parser.parse_args()

def main():
    args = get_args()
    if args.key:
        openai.api_key = args.key
    else:
        openai.api_key = os.getenv("OPENAI_API_KEY") or getpass.getpass("OpenAI API Key: ")
    random.seed(args.seed)
    print(f"Using seed: {args.seed}\n")
    # Dungeon setup
    rooms = generate_dungeon(args.seed)
    player = Player(location="room_0")
    state = GameState(seed=args.seed, rooms=rooms, player=player)
    save_file = Path("savefile.json")  # Default save file

    # Load from file if requested
    if args.load and args.load.exists():
        state = GameState.from_json(args.load.read_text())
        print(f"Loaded game state from {args.load}")

    print_intro()
    print(state.rooms)
    # Main loop
    while player.is_alive():
        state.turn += 1
        cmd = input("> ")
        if cmd.strip():
            state = handle_command(cmd.strip(), state, args.model, save_file)
        if state.rooms[player.location]["visited"] is False:
            state.rooms[player.location]["visited"] = True
            print("You have entered a new room.")
        else:
            print("You are back in a familiar room.")

    print("You have died. Game over.")

if __name__ == "__main__":
    main()
