# DungeonGPT: Build‑Your‑Own‑Adventure Roguelike

A text-based roguelike adventure powered by OpenAI. Explore a procedurally generated dungeon, fight monsters, collect loot, and map your journey—all from your terminal!

## Features
- Procedural dungeon generation (now a true grid: rooms and movement match the map)
- Classic roguelike stats and inventory
- Natural language commands powered by OpenAI
- Meta-commands for saving, loading, stats, inventory, and mapping
- Simple ASCII dungeon map
- Modern graphical interface with Pygame (all gameplay/UI is now in the graphical client)

## Requirements
- Python 3.9.13
- An OpenAI API key ([get one here](https://platform.openai.com/account/api-keys))
- `openai` Python package (see below)
- `pygame` Python package (for graphical version)

## Setup
1. **Clone the repository and enter the folder:**
   ```sh
   git clone <repo-url>
   cd <repo-folder>
   ```
2. **(Optional) Activate the provided virtual environment:**
   ```sh
   # On Windows
   .venv\Scripts\activate
   # On macOS/Linux
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```

## Running the Game

### Graphical (Pygame) Version
1. **Install Pygame if you haven't already:**
   ```sh
   pip install pygame
   ```
2. **Run the graphical client:**
   ```sh
   python roguelike_pygame.py
   ```
   - All gameplay and UI are now handled in the graphical client. The core logic is in `roguelike_ai.py` (as a library only).
   - The graphical version features a large, modern grid map, clickable input box, and a scrollable output area. Movement and room connections now match the visual grid exactly.

> **Note:** The old terminal/CLI version is no longer supported. `roguelike_ai.py` is now a pure library and does not run the game by itself.

## Commands
- `/help`         Show help menu
- `/look`         Describe the current room
- `/loot`         Pick up all items in the room
- `/inventory`    Show your inventory
- `/stats`        Show your stats
- `/map`          Show a map of the dungeon (matches the grid in the graphical version)
- `/save`         Save your game
- `/load`         Load your game
- `/quit` `/exit` Quit the game

You can also type natural language commands (e.g., `Go north`, `Attack the goblin`, `Use health potion`).

## Notes
- The game requires an internet connection to communicate with OpenAI.
- The virtual environment (`.venv`) is provided but you must install `openai` yourself.
- The default model is `gpt-4.1-mini` (change with `--model` if needed).

## Credits
- Some visual assets and inspiration from [2-Minute Tabletop](https://tools.2minutetabletop.com/)

## License
MIT
