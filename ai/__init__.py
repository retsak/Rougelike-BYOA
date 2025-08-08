from __future__ import annotations

"""OpenAI-powered command handling for DungeonGPT."""

import json
import os
import random
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
    "Describe the world in vivid second-person prose (what the player sees, hears, feels) and keep pacing brisk. "
    "Warn the player if in danger and narrate consequences of ignoring or leaving hostile creatures. "
    "ONLY provide an 'options' list (numbered suggestions) when the player explicitly requests a hint via the /hint command. "
    "Otherwise DO NOT include an 'options' list or numbered suggestions; just give immersive narrative and consequences. "
    "In combat you also refrain from enumerating options unless /hint was used; the client UI supplies action buttons. "
    "A numeric 'roll_result' may be supplied by the engine; this is an actual d20 roll already made. Interpret it using standard d20 intuition: 1 = dramatic failure, 2-9 failure, 10-11 marginal, 12-18 success (degree scales), 19 strong success, 20 = critical success. NEVER ask the player to roll again for that action—resolve with this provided outcome. If no roll_result is provided, you may narrate setup or request for a roll implicitly through fiction but do NOT fabricate a roll. "
    "Never reveal hidden info or raw die rolls—only outcomes; don't print the number explicitly unless the player explicitly framed the action around the roll. "
    "Do NOT output internal bookkeeping like 'State changes:', JSON dumps, or '(state_delta)'. The player should only see story narration. "
    "Output JSON with at least: 'narrative' and 'state_delta'. If (and only if) /hint was used AND you have concrete helpful next steps, include an 'options' array of concise actionable strings (max 5). "
    "Do not include 'force_option_select' unless an unavoidable binary or multi-way mandatory choice blocks progress AND /hint was requested. "
    "Keep narration concise when movement-only unless detail was requested."
)

# Add a counter to track API calls
api_call_counter = 1

# Initialize OpenAI client lazily
client: OpenAI | None = None


def call_openai(state: GameState, cmd: str, model: str, roll_result: int | None = None, hint_mode: bool = False) -> dict:
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
    brief = False
    if "[BRIEF]" in cmd:
        brief = True
        cmd = cmd.replace("[BRIEF]", "").strip()
    # Prepare state snapshot, but strip internal-only / non-JSON friendly pieces (ensure lists not sets)
    state_dict = asdict(state)
    # Replace any 'room_X' style location names in narrative phase later; keep internal ids here
    user_payload = {
        "state": state_dict,
        "command": cmd,
        "roll_result": roll_result,
        "history": state.history[-10:]
    }
    if brief:
        user_payload["style_hint"] = "Provide a concise 2-3 sentence scene description focused on immediate tactical context."
    extra_directive = " (User did NOT request /hint; omit any options array and numbered suggestions.)" if not hint_mode else " (User requested /hint; you MAY add an 'options' array of concise numbered actionable suggestions.)"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + (" Always keep movement-only responses to 2-3 sentences unless player asks for detail." if brief else "") + extra_directive},
        {"role": "user", "content": json.dumps(user_payload)},
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
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {"narrative": content, "state_delta": {}}
    # Strip options if not in hint mode regardless of model output
    if not hint_mode and isinstance(data, dict):
        if 'options' in data:
            del data['options']
        # Remove any inline 'Options:' section from narrative
        narr = data.get('narrative', '') or ''
        if 'Options:' in narr:
            lines = []
            skipping = False
            for ln in narr.split('\n'):
                if ln.strip().lower().startswith('options:'):
                    skipping = True
                    continue
                if skipping:
                    # Stop skipping when line no longer looks like numbered option
                    if not ln.strip().startswith(tuple(f"{i}." for i in range(1,10))):
                        skipping = False
                    else:
                        continue
                if not skipping:
                    lines.append(ln)
            data['narrative'] = '\n'.join(lines).strip()
    # Additional sanitation: remove any 'State changes:' debug block & raw JSON dumps accidentally emitted
    def _sanitize(narr: str) -> str:
        if not narr:
            return narr
        lines = narr.split('\n')
        cleaned = []
        skip_mode = False
        json_block = False
        brace_depth = 0
        for ln in lines:
            low = ln.strip().lower()
            # Start of state changes block
            if not skip_mode and low.startswith('state changes:'):
                skip_mode = True
                continue
            if skip_mode:
                # end when blank line encountered
                if not ln.strip():
                    skip_mode = False
                continue
            # Skip lines that look like explicit '(state_delta)' marker
            if low.startswith('(state_delta)'):
                continue
            # Remove leading 'narrative:' label if model echoed it
            if low.startswith('narrative:'):
                # Drop the label but keep the remainder after colon
                after = ln.split(':',1)[1].lstrip() if ':' in ln else ''
                if after:
                    cleaned.append(after)
                continue
            # Remove lines starting with 'state_delta:' and any inline JSON that follows
            if low.startswith('state_delta:'):
                # Attempt to detect inline JSON on same line; if braces start here, suppress until balanced
                idx = ln.find('{')
                if idx != -1:
                    json_block = True
                    brace_depth = ln.count('{') - ln.count('}')
                continue
            # Detect raw JSON block heuristically: line starts with '{' and contains '"player"' or '"rooms"'
            if not json_block and ln.strip().startswith('{') and ('"player"' in ln or '"rooms"' in ln):
                json_block = True
                # Track braces to know when to end
                brace_depth = ln.count('{') - ln.count('}')
                continue
            if json_block:
                brace_depth += ln.count('{') - ln.count('}')
                if brace_depth <= 0:
                    json_block = False
                continue
            cleaned.append(ln)
        # Trim leading/trailing empty lines
        while cleaned and not cleaned[0].strip():
            cleaned.pop(0)
        while cleaned and not cleaned[-1].strip():
            cleaned.pop()
        return '\n'.join(cleaned)
    if isinstance(data, dict) and 'narrative' in data:
        data['narrative'] = _sanitize(data.get('narrative', ''))
    return data


def get_api_call_counter() -> int:
    """Return the number of API calls made via ``call_openai``."""
    return api_call_counter


META_CMDS = {"/save", "/load", "/quit", "/exit", "/stats", "/inventory", "/look", "/loot", "/map", "/help", "/ability", "/detail", "/equip", "/use", "/skipvoice", "/voicevol", "/voicespeed", "/autoroll", "/adv", "/dis", "/clearadv"}

# Default cooldown turns for hero abilities (can be overridden per balance needs)
ABILITY_COOLDOWNS = {
    "heal": 5,          # Cleric heal (prevents infinite loop spam)
    "shield_block": 4,  # Knight defensive boost
    "fire_breath": 6,   # Dragon AoE
    "power_strike": 3,  # Fighter burst
    "backstab": 3,      # Rogue high damage
    "tongue_whip": 2,   # Toad moderate attack
}

# Track a simple movement streak to compress repetitive corridor narration
movement_streak: list[str] = []  # list of direction tokens

# --- Auto-rolling & advantage state (engine-side, not persisted) ---
autoroll_enabled: bool = False           # if True, non-movement natural language actions auto-roll a d20
pending_advantage: str | None = None     # 'adv' | 'dis' | None (consumed on next auto-roll)


def _tick_time(state: GameState, advance: bool = True) -> None:
    """Advance global turn counter and decrement ability cooldowns.
    If advance is False no mutation occurs (used for non-time meta commands like /save,/load).
    """
    if not advance:
        return
    state.turn += 1
    cds = getattr(state, 'ability_cooldowns', {}) or {}
    new_cds: dict = {}
    for abil, remaining in cds.items():
        if remaining > 1:
            new_cds[abil] = remaining - 1
        # if remaining == 1 it expires this turn
    state.ability_cooldowns = new_cds


def handle_meta(cmd: str, state: GameState, save_file) -> bool:
    lc = cmd.lower()
    global autoroll_enabled, pending_advantage
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
        equipped = ", ".join(f"{slot}:{item}" for slot,item in state.player.equipped.items()) or "(none)"
        print("Inventory: " + ", ".join(inv))
        print("Equipped: " + equipped + "\n")
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
        else:
            # Cooldown check
            remaining = state.ability_cooldowns.get(ability, 0) if hasattr(state, 'ability_cooldowns') else 0
            if remaining > 0:
                print(f"Your {ability.replace('_',' ')} ability is recharging ({remaining} turn(s) left).\n")
                return True
            # Execute ability
            if ability == "heal":
                state.player.hp += 10
                print("You channel divine power and heal 10 HP.\n")
                state.ability_cooldowns[ability] = ABILITY_COOLDOWNS.get(ability, 5)
            elif ability == "shield_block":
                state.player.hp += 5
                print("You raise your shield and bolster your defenses, gaining 5 HP.\n")
                state.ability_cooldowns[ability] = ABILITY_COOLDOWNS.get(ability, 4)
            elif not living_enemies:
                print("No enemies to target with your ability.\n")
            else:
                enemy = living_enemies[0]
                if ability == "fire_breath":
                    dmg = state.player.str + 5
                    for e in living_enemies:
                        e["hp"] -= dmg
                    print(f"You breathe fire, dealing {dmg} damage to all foes!\n")
                    state.ability_cooldowns[ability] = ABILITY_COOLDOWNS.get(ability, 6)
                elif ability == "power_strike":
                    dmg = state.player.str * 2
                    enemy["hp"] -= dmg
                    print(f"You deliver a power strike for {dmg} damage!\n")
                    state.ability_cooldowns[ability] = ABILITY_COOLDOWNS.get(ability, 3)
                elif ability == "backstab":
                    dmg = state.player.dex * 2
                    enemy["hp"] -= dmg
                    print(f"You backstab {enemy['name']} for {dmg} damage!\n")
                    state.ability_cooldowns[ability] = ABILITY_COOLDOWNS.get(ability, 3)
                elif ability == "tongue_whip":
                    dmg = state.player.str + state.player.dex
                    enemy["hp"] -= dmg
                    print(f"You lash out with your tongue, dealing {dmg} damage!\n")
                    state.ability_cooldowns[ability] = ABILITY_COOLDOWNS.get(ability, 2)
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
  /detail       Ask for a richer description of current location
  /save         Save your game
  /load         Load your game
  /quit, /exit  Quit the game
""")
        return True
    if lc == "/detail":
        room = state.rooms[state.player.location]
        desc = f"(Detail) You focus your senses on this {room['type'].replace('_',' ')}. "
        if room["enemies"]:
            desc += "Hostile presence: " + ", ".join(e["name"] for e in room["enemies"]) + ". "
        if room["items"]:
            desc += "Items here: " + ", ".join(room["items"]) + ". "
        if room.get("locked"):
            desc += "A heavy lock bars one way. "
        if room.get("trap"):
            desc += "The floor bears suspicious seams—likely a trap. "
        print(desc + "\n")
        return True
    if lc.startswith('/skipvoice'):
        from tts_engine import voice
        flushed = voice.flush_queue()
        print(f"[Voice] Skipped {flushed} queued narration segment(s).\n")
        return True
    if lc.startswith('/voicevol'):
        parts = cmd.split()
        if len(parts) == 2:
            try:
                val = float(parts[1])
                from tts_engine import voice
                voice.set_volume(val)
                print(f"[Voice] Volume set to {voice.volume:.2f}.\n")
            except ValueError:
                print("Usage: /voicevol <0.0-1.0>\n")
        else:
            print("Usage: /voicevol <0.0-1.0>\n")
        return True
    if lc.startswith('/voicespeed'):
        parts = cmd.split()
        if len(parts) == 2:
            try:
                val = float(parts[1])
                from tts_engine import voice
                voice.set_rate(val)
                print(f"[Voice] Speed multiplier set to {voice.rate:.2f}.\n")
            except ValueError:
                print("Usage: /voicespeed <multiplier> (e.g. 1.2)\n")
        else:
            print("Usage: /voicespeed <multiplier> (e.g. 1.2)\n")
        return True
    if lc.startswith('/autoroll'):
        parts = cmd.split()
        if len(parts) == 1:
            print(f"Auto-roll is {'ON' if autoroll_enabled else 'OFF'}. Use /autoroll on or /autoroll off.\n")
        else:
            toggle = parts[1].lower()
            if toggle in {'on','off'}:
                autoroll_enabled = (toggle == 'on')
                print(f"[AutoRoll] {'Enabled' if autoroll_enabled else 'Disabled'}.\n")
            else:
                print("Usage: /autoroll on|off\n")
        return True
    if lc == '/adv':
        pending_advantage = 'adv'
        print("[AutoRoll] Next roll will have advantage.\n")
        return True
    if lc == '/dis':
        pending_advantage = 'dis'
        print("[AutoRoll] Next roll will have disadvantage.\n")
        return True
    if lc == '/clearadv':
        pending_advantage = None
        print("[AutoRoll] Advantage/disadvantage cleared.\n")
        return True
    if lc.startswith("/equip"):
        parts = cmd.split(maxsplit=1)
        if len(parts) == 1:
            print("Usage: /equip <item name>\n")
        else:
            item = parts[1].strip()
            msg = state.player.equip_item(item)
            print(msg + "\n")
        return True
    if lc.startswith("/use"):
        parts = cmd.split(maxsplit=1)
        if len(parts) == 1:
            print("Usage: /use <item name>\n")
        else:
            item = parts[1].strip()
            msg = state.player.consume_item(item)
            print(msg + "\n")
        return True
    return False


def handle_command(cmd: str, state: GameState, model: str, roll_result: int | None = None, save_file=None) -> dict:
    """Process a player command and merge the resulting state changes."""
    global autoroll_enabled, pending_advantage
    old_location = state.player.location if hasattr(state.player, 'location') else None
    if cmd.startswith("/"):
        # Meta command time advancement rules:
        # - /save and /load do not advance time
        # - /ability only advances time if the ability actually fires (not while recharging)
        # - All other meta commands advance time once when issued
        lower_cmd = cmd.lower()
        advance = False
        if lower_cmd in {"/save", "/load"}:
            advance = False
        elif lower_cmd == "/ability":
            abil = getattr(state.player, 'ability', None)
            if abil:
                remaining = getattr(state, 'ability_cooldowns', {}).get(abil, 0)
                # Only advance if ability is ready (remaining == 0)
                if remaining == 0:
                    advance = True
        else:
            advance = True
        if advance:
            _tick_time(state, True)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            handled = handle_meta(cmd, state, save_file)
        meta_out = buf.getvalue().strip()
        if handled:
            return {"narrative": meta_out, "state_delta": {}}
        return {"narrative": "[!] Unknown command.", "state_delta": {}}
    hint_mode = cmd.lower().startswith('/hint')
    # Remove the /hint token from the command sent to the model for cleaner language understanding
    model_cmd = cmd[5:].strip() if hint_mode else cmd
    # Natural language commands always advance time
    _tick_time(state, True)
    auto_roll_summary = None
    # Determine if we should auto-roll (only if no explicit roll_result passed and autoroll is on and command is not a movement/basic look)
    def _is_movement_like(c: str) -> bool:
        c = c.lower().strip()
        return c.startswith(("move","go","walk","run","look","flee","attack"))
    if roll_result is None and autoroll_enabled and not cmd.startswith('/') and not _is_movement_like(model_cmd):
        # Perform auto-roll (with optional advantage/disadvantage)
        r1 = random.randint(1,20)
        chosen = r1
        mode = 'single'
        detail = f"d20 => {r1}"
        if pending_advantage in {'adv','dis'}:
            r2 = random.randint(1,20)
            if pending_advantage == 'adv':
                chosen = max(r1, r2)
                mode = 'advantage'
            else:
                chosen = min(r1, r2)
                mode = 'disadvantage'
            detail = f"d20 ({r1}, {r2}) {mode} => {chosen}"
            pending_advantage = None  # consume
        roll_result = chosen
        auto_roll_summary = f"[auto-roll] {detail}"
    openai_resp = call_openai(state, model_cmd, model, roll_result, hint_mode=hint_mode)
    narrative, state_delta = openai_resp["narrative"], openai_resp["state_delta"]
    # --- Memory: append to history ---
    state.history.append({"turn": state.turn, "command": cmd, "narrative": narrative})
    # --- Safe merge of model-proposed state_delta ---
    # The model is NOT authoritative: ignore unknown keys and never fully replace the Player object.
    if isinstance(state_delta, dict):
        for k, v in list(state_delta.items()):
            if k == 'player' and isinstance(v, dict):
                for pk, pv in v.items():
                    if hasattr(state.player, pk):
                        try:
                            setattr(state.player, pk, pv)
                        except Exception:
                            pass
                state_delta.pop('player', None)
                continue
            if k == 'history':
                state_delta.pop('history', None)
                continue
            if not hasattr(state, k):
                state_delta.pop(k, None)
                continue
            try:
                current = getattr(state, k)
                if isinstance(current, dict) and isinstance(v, dict):
                    deep_update(current, v)
                else:
                    setattr(state, k, v)
            except Exception:
                state_delta.pop(k, None)
                continue
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
    # --- Sanitize player location if model produced an invalid room id ---
    def _sanitize_location() -> None:
        loc = state.player.location
        if loc in state.rooms:
            return
        # Attempt to parse patterns like 'room_X_direction'
        if '_' in loc:
            base, *rest = loc.split('_')
            if base == 'room' and len(rest) >= 2:
                # pattern room_<index>_direction
                try:
                    idx = int(rest[0])
                except ValueError:
                    idx = None
                direction = rest[-1].lower()
                if idx is not None:
                    # reconstruct valid room id from idx
                    candidate = f"room_{idx}"
                    if candidate in state.rooms:
                        # derive target via direction from candidate coords
                        cx, cy = state.rooms[candidate]["coords"]
                        deltas = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
                        if direction in deltas:
                            dx, dy = deltas[direction]
                            tx, ty = cx + dx, cy + dy
                            # Build coord->id map once
                            coord_to_id = {r["coords"]: rid for rid, r in state.rooms.items()}
                            target_id = coord_to_id.get((tx, ty))
                            if target_id:
                                state.player.location = target_id
                                state.rooms[target_id]["visited"] = True
                                return
                        # Fallback to candidate if direction invalid
                        state.player.location = candidate
                        return
        # Final fallback: revert to old_location if valid, else entrance
        if old_location and old_location in state.rooms:
            state.player.location = old_location
        else:
            # choose safest default
            if 'room_0' in state.rooms:
                state.player.location = 'room_0'
            else:
                # arbitrary first key
                state.player.location = next(iter(state.rooms))
    _sanitize_location()
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
    # Movement compression: detect sequences of brief movement commands
    lower_cmd = cmd.lower()
    moved = False
    for token in ("move ", "go ", "walk "):
        if lower_cmd.startswith(token):
            direction = lower_cmd.split(' ')[1] if len(lower_cmd.split(' ')) > 1 else "?"
            movement_streak.append(direction)
            moved = True
            break
    if not moved:
        # flush streak if present and user did a non-move action
        if movement_streak:
            if len(movement_streak) > 2:
                narrative = f"You traverse {len(movement_streak)} quiet passages ({', '.join(movement_streak)}).\n" + narrative
            movement_streak.clear()
    else:
        # if streak length large and narrative long, compress current narrative
        if len(movement_streak) > 2 and len(narrative.split()) > 40:
            narrative = f"You continue ({movement_streak[-3:]}) through the dungeon."
    # Replace internal room ids like room_3 with more user-friendly terms if they appear verbatim
    # Simple heuristic: room_<number> -> "the chamber" (first) or "the next chamber"
    import re
    def _room_sub(match, counter={'n':0}):
        counter['n'] += 1
        return 'the chamber' if counter['n']==1 else 'the next chamber'
    narrative = re.sub(r"room_\d+", _room_sub, narrative)
    dm_say(narrative)
    # Return the full OpenAI response dict, plus any modifications
    openai_resp["narrative"] = narrative
    openai_resp["state_delta"] = state_delta
    if auto_roll_summary:
        openai_resp["auto_roll_summary"] = auto_roll_summary
    return openai_resp
