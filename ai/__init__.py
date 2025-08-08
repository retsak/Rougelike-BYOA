from __future__ import annotations

"""OpenAI-powered command handling for DungeonGPT."""

import json
import os
from dataclasses import asdict

from openai import OpenAI
from tts_engine import dm_say

from core.models import GameState, Player
from core.dungeon import deep_update


RULES = {
    # Core character stats the engine persists
    "core_stats": ["hp", "str", "dex", "level", "xp"],

    # Default die for contested rolls
    "dice": "d20",

    # Actions the player may type (you can still suggest colourful synonyms in narration)
    "actions": [
        "move", "look", "attack", "loot",
        "inventory", "use",
        "flee",          # disengage & move in the same turn
        "equip"          # swap weapons / armour
    ],

    # Combat & hazard logic the DM must enforce
    "combat": {
        # Order is always Player ➜ Enemies
        "turn_order": "player_then_enemies",

        # If the player tries to leave a tile that still contains a living enemy
        # the enemy gains an automatic “opportunity attack”.
        "opportunity_attack": True,

        # If the player **ignores** a living enemy (any action other than
        # attack / flee while sharing a tile), the enemy makes a free attack.
        "auto_damage_on_ignore": True
    },

    # The front-end/game engine is the single source of truth
    "engine_authority": "Always trust state_delta",

    # Dice rolls for actions
    "dice_rolls": {
        "attack": "d20",
        "skill_check": "d20"
    }
}

SYSTEM_PROMPT = (
    "You are **DungeonGPT**, a seasoned Dungeons & Dragons Dungeon Master. "
    "You actively direct the player, offering clear choices, warnings, and suggestions for what to do next. "
    "Describe the world in vivid second-person prose—what the player sees, hears, and feels. "
    "Role-play NPCs and monsters, and always keep the pacing brisk. "
    "If the player is in danger, warn them and suggest defensive or clever actions. "
    "If the player ignores or moves away from a hostile creature, narrate the enemy's reaction and the consequences (damage, attacks, etc.). "
    "Always offer at least two possible actions or directions after each turn. "
    "If the player is in a battle (i.e., shares a room with a living enemy), you MUST provide at least two numbered actionable options (e.g., '1. Attack', '2. Flee', '3. Use Item') for the player to select from, and you MUST include a boolean field 'force_option_select': true in your JSON output. "
    "If the player must select an option, always present the options as a numbered list at the end of your narrative, and set 'force_option_select': true in your JSON output. "
    "If the player is not forced to select an option, do not include the 'force_option_select' field or set it to false. "

    "### Strict Gameplay Rules\n"
    "• Always apply the rules in the JSON `RULES` block above.\n"
    "• After every player action, resolve enemy reactions automatically.  \n"
    "    – If the player ignores or moves away from a hostile creature that is still alive, "
    "      the creature immediately attacks (deal damage in `state_delta`).\n"
    "• Never reveal hidden information or raw die rolls—only outcomes.\n"
    "• Output **JSON** with two top-level keys:\n"
    "    1. `narrative`: rich, immersive description for the player, including consequences and next steps.\n"
    "    2. `state_delta`: exact stat/position/flag changes caused this turn.\n"
    "If you are forcing the player to select an option, add a third key: 'force_option_select': true.\n"
    "The client UI will merge `state_delta` into authoritative game state—treat it as truth.\n"

    "Stay consistent, keep tension high, and remember: an un-dealt-with enemy is a stabbing you owe the player."
)

# Add a counter to track API calls
api_call_counter = 1

# Initialize OpenAI client lazily
client: OpenAI | None = None


def call_openai(state: GameState, cmd: str, model: str, roll_result: int | None = None) -> dict:
    """Send state and command to OpenAI and return the parsed response."""
    global api_call_counter
    api_call_counter += 1  # Increment the counter

    # Ensure OpenAI API key is set
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API key is not set. Please check your environment variables.")

    global client
    if client is None:
        client = OpenAI(api_key=api_key)

    # Pass history as context for memory
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "state": asdict(state),
            "command": cmd,
            "roll_result": roll_result,  # Include roll result
            "history": state.history[-10:]  # Last 10 events for context
        })},
    ]
    resp = client.responses.create(
        model=model,
        input=messages,
        reasoning={"effort": "minimal"},
    )
    content = ""
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    content += c.text
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"narrative": content, "state_delta": {}}


def get_api_call_counter() -> int:
    """Return the number of API calls made via ``call_openai``."""
    return api_call_counter


META_CMDS = {"/save", "/load", "/quit", "/exit", "/stats", "/inventory", "/look", "/loot", "/map", "/help", "/ability"}


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
        ability = f" Ability: {p.ability}" if p.ability else ""
        print(f"HP {p.hp} STR {p.str} DEX {p.dex} LVL {p.level} XP {p.xp}/{p.level*100}{ability}\n")
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
    if lc == "/ability":
        ability = getattr(state.player, "ability", None)
        room = state.rooms[state.player.location]
        living_enemies = [e for e in room["enemies"] if e.get("hp", 0) > 0]
        if not ability:
            print("You have no special ability.\n")
        elif ability == "heal":
            state.player.hp += 10
            print("You channel divine power and heal 10 HP.\n")
        elif ability == "shield_block":
            state.player.hp += 5
            print("You raise your shield and bolster your defenses, gaining 5 HP.\n")
        elif not living_enemies:
            print("No enemies to target with your ability.\n")
        else:
            enemy = living_enemies[0]
            if ability == "fire_breath":
                dmg = state.player.str + 5
                for e in living_enemies:
                    e["hp"] -= dmg
                print(f"You breathe fire, dealing {dmg} damage to all foes!\n")
            elif ability == "power_strike":
                dmg = state.player.str * 2
                enemy["hp"] -= dmg
                print(f"You deliver a power strike for {dmg} damage!\n")
            elif ability == "backstab":
                dmg = state.player.dex * 2
                enemy["hp"] -= dmg
                print(f"You backstab {enemy['name']} for {dmg} damage!\n")
            elif ability == "tongue_whip":
                dmg = state.player.str + state.player.dex
                enemy["hp"] -= dmg
                print(f"You lash out with your tongue, dealing {dmg} damage!\n")
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
  /ability      Use your hero's special ability
  /map          Show a map of the dungeon
  /save         Save your game
  /load         Load your game
  /quit, /exit  Quit the game
""")
        return True
    return False


def handle_command(cmd: str, state: GameState, model: str, roll_result: int | None = None, save_file=None) -> dict:
    """Process a player command and merge the resulting state changes."""
    old_location = state.player.location if hasattr(state.player, 'location') else None
    if cmd.startswith("/"):
        if handle_meta(cmd, state, save_file):
            return {"narrative": "", "state_delta": {}}
        print("[!] Unknown command:", cmd)
        return {"narrative": "[!] Unknown command.", "state_delta": {}}
    openai_resp = call_openai(state, cmd, model, roll_result)
    narrative, state_delta = openai_resp["narrative"], openai_resp["state_delta"]
    # --- Memory: append to history ---
    state.history.append({"turn": state.turn, "command": cmd, "narrative": narrative})
    for k, v in state_delta.items():
        current = getattr(state, k)
        if isinstance(current, dict) and isinstance(v, dict):
            deep_update(current, v)
        else:
            setattr(state, k, v)
    # Ensure state.player is always a Player object
    if isinstance(state.player, dict):
        if 'location' not in state.player:
            state.player['location'] = old_location
        state.player = Player(**state.player)
    elif not isinstance(state.player, Player):
        try:
            state.player = Player(**dict(state.player))
        except Exception:
            pass
    # --- Enemy reaction logic ---
    room = state.rooms[state.player.location]
    living_enemies = [e for e in room["enemies"] if e.get("hp", 0) > 0]
    if living_enemies and not any(x in cmd.lower() for x in ["attack", "flee"]):
        enemy = living_enemies[0]
        dmg = max(1, enemy["str"])
        state.player.hp -= dmg
        narrative += f"\nThe {enemy['name']} attacks you for {dmg} damage as you ignore it!"
        if "hp" in state_delta:
            state_delta["hp"] -= dmg
        else:
            state_delta["hp"] = state.player.hp
    # Speak + print the narrative using the TTS engine.
    dm_say(narrative)
    # Return the full OpenAI response dict, plus any modifications
    openai_resp["narrative"] = narrative
    openai_resp["state_delta"] = state_delta
    return openai_resp
