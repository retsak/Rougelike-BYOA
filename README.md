<div align="center">

# DungeonGPT: Build‑Your‑Own‑Adventure Roguelike

Procedurally generated dungeon crawler + AI Dungeon Master + speech narration + modern Pygame UI.

Explore. Converse naturally. Fight. Loot. Adapt.

</div>

---

## 1. Overview
DungeonGPT is a hybrid roguelike / narrative sandbox. The deterministic game engine (movement, HP, inventory, enemies, XP) runs locally; an OpenAI model acts only as the narrative layer (descriptions, consequences, flavour) and may propose options **only when you explicitly ask for a hint** via `/hint`.

Core goals:
- Keep game state authoritative on the client (no model hallucination of stats).
- Fast iterative movement with compressed narration for long traversals.
- Option system opt‑in: you choose when you want structured suggestions.
- Immersive spoken narration (TTS) you can interrupt instantly with new input.

## 2. Feature Highlights
- 6×6 grid dungeon (procedurally generated) with room typing & enemy placement.
- Visual map with parallax background & ambient adaptive music.
- Hero class selection (stats + unique ability + auto‑equipped starter weapon).
- Inventory with equipment bonuses, consumables, equip / unequip UI panel.
- AI narration w/ movement brevity mode (`[BRIEF]` injected for fast commands).
- Strict hint gating: numbered options appear only after `/hint`.
- Combat panel: enemy cards + quick buttons (Attack / Flee / Ability) – no need to wait for model suggestions.
- Text‑to‑Speech DM voice (interruptible, adjustable volume & speed, offline fallback tone).
- Scrollable multi‑tab log (Scene & Combat) with search & collapse of older lines.
- Ambient audio separated from SFX to prevent music dropouts.
- Adaptive frame rate + optional VSync toggle (F8) for smoother idle performance.

## 3. Technology Stack
- Python 3.9+
- Pygame (rendering, input, audio mixer for loops & SFX)
- OpenAI Responses API (narrative JSON, streamed under the hood)
- SimpleAudio (low‑latency chunked TTS playback)
- Pure Python procedural generation & state containers

## 4. Repository Structure (Essentials)
```
config.py              Global configuration (TTS, audio volumes)
play.py                Launcher (calls ui.main)
ai/__init__.py         AI system prompt, OpenAI call + command handling, hint gating
core/grid.py           Dungeon grid generation
core/dungeon.py        Deep update helpers & utilities
core/models.py         Data models: Player, GameState, enemy / item logic
ui/game_loop.py        Main Pygame loop, rendering, input, panels, combat UI
ui/assets.py           Asset loading (sprites, backgrounds, loops, SFX)
ui/dialogs.py          Hero select & game over dialogs
tts_engine.py          Chunked TTS queue, interruption, volume & speed controls
Assets/...             Art & audio assets (see licensing notes)
tests/test_dungeon_generation.py  Basic generation test
```

## 5. Quick Start
1. Clone & enter directory:
   ```bash
   git clone https://github.com/<you>/<repo>.git
   cd <repo>
   ```
2. (Optional) Create / activate venv:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set your OpenAI key (PowerShell example):
   ```powershell
   $env:OPENAI_API_KEY="sk-..."
   ```
   Or export in bash: `export OPENAI_API_KEY=sk-...`
5. Launch:
   ```bash
   python play.py
   ```
6. Select a hero. Type natural language or use meta commands. Enjoy.

## 6. Controls & Input
| Action | Method |
| ------ | ------ |
| Enter command | Type + Enter or click Send |
| Quick meta command | Click button row (/look /loot /stats etc.) |
| Move | Natural language ("go north"), numbered option (from /hint), or click adjacent room tile |
| Combat action | Click Attack / Flee / Ability or type (e.g. "attack") |
| Inventory panel | Click /inventory button |
| Equip/Use | Click item → action buttons |
| Scroll log | Mouse wheel / PageUp / PageDown |
| Toggle VSync | F8 |
| Search log | Click search box above log |
| Request options | Type `/hint` (options appear, else hidden) |
| Interrupt narration | Enter any new command or click a button |

## 7. Command Reference (Meta)
```
/help       Show help
/look       Describe current room
/loot       Pick up all items in room
/inventory  Show UI inventory panel
/stats      Player stats
/map        ASCII map in console (visited rooms)
/ability    Use hero ability (contextual)
/hint       Ask DM for suggested next actions (reveals numbered options)
/detail     Richer local description (no movement)
/equip X    Equip an item by name
/use X      Consume usable item
/voicevol N Set TTS volume 0.0–1.0
/voicespeed N  Set TTS speed multiplier
/save /load Save/load game state
/quit       Exit
```
Everything else is free‑form natural language. Movement commands get auto‑tagged with `[BRIEF]` to request concise narration.

## 8. Hint System Philosophy
The AI never spams numbered choices. It only emits an `options` array (max 5) when you deliberately type `/hint`. Internally:
- `/hint` is stripped before sending to the model (clean semantic input).
- A `hint_mode` flag augments the system prompt.
- Post‑processing purges any accidentally produced options when not in hint mode.

## 9. Architecture (Text Diagram)
```
         +--------------------+
Input -> |  ui/game_loop.py   | -- movement/enemy logic --> core/*
         +---------+----------+
                   | JSON (state snapshot + command)
                   v
              ai/__init__.py  --SYSTEM_PROMPT--> OpenAI API
                   | (narrative + state_delta)
                   v
         +--------------------+
         |  GameState merge   |
         +---------+----------+
                   | narrative
                   v
            tts_engine.py (queued audio)
```

Authoritative data lives in `GameState`. The model can suggest state_delta changes; they are merged conservatively (deep_update). Sanitizers protect against invalid room ids, impossible teleports, or rogue mutations.

## 10. Text‑To‑Speech
- Configurable in `config.py` (model, voice, volume, rate, fallback).
- Narration chunked to avoid long blocking synthesis.
- `voice.stop_all()` interrupts playback instantly on new input.
- Adjust volume: `/voicevol 0.7`   Speed: `/voicespeed 1.15`.
- Offline fallback: emits a simple tone if API fails (toggle in config).

## 11. Audio System
- Ambient loops chosen per room type (`ui/assets.py` -> `ROOM_TYPE_TO_LOOP_KEYS`).
- Short SFX (steps, sword) separated so they do not cut off looping music.
- Ambient volume scaled via `AMBIENT_VOLUME` in `config.py`.

## 12. Dungeon Generation
`core/grid.py` builds a fixed 6×6 grid, tagging rooms (entrance, treasure, shrine, boss, traps, lairs). You can:
- Change grid size (update constants in `game_loop.py` + generation logic for bounds).
- Add new room types: introduce type assignment + add rendering color in `game_loop.py` + optional ambient mapping.

## 13. Player & Items
`core/models.py` defines `Player`, inventory list, equipped slots, bonuses and ability logic. To add a new ability:
1. Add the ability name when assigning hero stats in `ui/dialogs.py`.
2. Extend the `/ability` branch inside `ai/__init__.py` meta handler for its effect.
3. (Optional) Teach the model about it by amending `SYSTEM_PROMPT` action lore.

Adding an item:
1. Introduce name in loot table generation (grid or enemy spawn logic).
2. Update classification rules in `Player.classify_item`.
3. If equipment, map to slot in `detect_slot` & bonus in `compute_bonus`.

## 14. Enemy Behaviour
Enemies are stored per room; simple movement/spawn updates happen only after player movement (keeps non‑movement commands responsive). Attacks:
- Opportunity attacks if you flee / move while sharing a tile.
- Auto retaliation appended in `handle_command` if player ignores an enemy.

To add an enemy sprite: drop PNG into `Assets/Basic Enemies/` and ensure its filename contains the enemy name (partial match attaches sprite).

## 15. AI System & Prompt Tuning
`ai/__init__.py`:
- `SYSTEM_PROMPT` sets narrative style + hint gating rules.
- `call_openai()` packages state + last 10 history entries.
- Movement brevity uses `[BRIEF]` token inserted by UI for fast travel.
- Safety passes remove stray `Options:` text if not in hint mode.

To experiment:
1. Edit `SYSTEM_PROMPT` (keep JSON contract: must return `narrative`, `state_delta`, optional `options`).
2. Add new meta commands to `META_CMDS` + implement branch in `handle_meta`.
3. Expand state snapshot with new tracked fields (ensure they are serializable).

## 16. Customization Cookbook
| Goal | File(s) | Steps |
| ---- | ------- | ----- |
| Change grid size | `ui/game_loop.py`, `core/grid.py` | Adjust `GRID_W`, `GRID_H`; ensure generation loops respect new bounds |
| New hero class | `ui/dialogs.py` (selection), `game_loop.py` (default weapon) | Add sprite + stats + ability |
| Add ambient track | `Assets/Audio`, `ui/assets.py` | Drop file, register key in loop loader, map room type |
| Lower / raise music | `config.py` | Adjust `AMBIENT_VOLUME` (0.0–1.0) |
| New item slot | `core/models.py` | Extend `equipped` dict, update equip/unequip + bonuses |
| Disable TTS | `config.py` | Set `TTS_ENABLED = False` |
| Change voice | `config.py` | Set `TTS_VOICE` | 
| Remove hint system | `ai/__init__.py` | Allow options always (remove gating) |
| Add status effect | `core/models.py`, `ui/game_loop.py` | Track on player, render icon in conditions block |

## 17. Performance Tips
- Large resolutions or alpha PNGs can slow draws: batch assets, reduce `CELL_SIZE`.
- Idle frame rate auto lowers; keep window focused for smoother input.
- Disable parallax by skipping offset update.
- If API latency high, pre‑issue movement chains (e.g. "go north three rooms") — the model will compress responses.

## 18. Saving & Loading
`/save` writes JSON snapshot (rooms, player, turn) to a default path (configure or extend in future). `/load` restores. The model is stateless across full reloads; only the limited `history` segment is sent each turn.

## 19. Troubleshooting
| Problem | Cause | Fix |
| ------- | ----- | --- |
| "OpenAI API key not found" | Env var missing | Set `OPENAI_API_KEY` before launch |
| No music | Mixer init failed or file missing | Check `pygame.mixer.init()` logs & asset paths |
| TTS silent | API blocked / voice unsupported | Try different `TTS_VOICE` or disable TTS |
| Options appear without /hint | Outdated code | Pull latest (hint gating enforced post‑processing) |
| Movement stalls | Duplicate processing (older bug) | Ensure single pending command handler (current version fixed) |
| High CPU idle | VSync off + large window | Toggle F8 or reduce size |

## 20. Roadmap (Ideas)
- Procedural multi‑floor expansion
- Fog‑of‑war with light radius
- Rich enemy AI (pathing, ranged attacks)
- Loot rarity tiers & affixes
- In‑game settings panel (audio sliders, keybinds)
- Local LLM fallback / offline narrative templates

## 21. Contributing
Small focused PRs welcome: bug fixes, performance tweaks, modularization. Please keep AI prompt changes surgical and justify state mutations.

## 22. Licensing & Assets
Code: MIT (see below). Some art/audio placeholders are third‑party—replace if distributing commercially. Verify license compatibility for any newly added assets.

## 23. Security & Privacy
Only the minimal game state snapshot + last ~10 turns are sent to OpenAI. No personal user info is included. Do not paste secrets into the command box.

## 24. Extending Tests
Add deterministic tests around generation (`core/grid.py`) & state mutation utilities. Mock out OpenAI calls when testing AI handlers.

## 25. License
MIT

---

Happy delving. May your streak of natural 20s be statistically improbable.

