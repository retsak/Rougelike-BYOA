# DungeonGPT: Build‑Your‑Own‑Adventure Roguelike

A text-based roguelike adventure powered by OpenAI. Explore a procedurally generated dungeon, fight monsters, collect loot, and map your journey—all from your terminal!

## Features
- Procedural dungeon generation
- Classic roguelike stats and inventory
- Natural language commands powered by OpenAI
- Meta-commands for saving, loading, stats, inventory, and mapping
- Simple ASCII dungeon map

## Requirements
- Python 3.9.13
- An OpenAI API key ([get one here](https://platform.openai.com/account/api-keys))
- `openai` Python package (see below)

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
   pip install openai
   ```

## Running the Game
1. **Set your OpenAI API key:**
   - Recommended: set the environment variable before running:
     ```sh
     set OPENAI_API_KEY=sk-...   # Windows
     export OPENAI_API_KEY=sk-... # macOS/Linux
     ```
   - Or, you can use the `--key` flag when running the script.

2. **Start the game:**
   ```sh
   python roguelike_ai.py --seed 1337
   # Or with explicit API key
   python roguelike_ai.py --key sk-... --seed 1337
   ```

## Running in Google Colab

You can also run DungeonGPT in a Google Colab notebook:

1. **Upload your project files to Colab** (or clone the repo in a Colab cell):
   ```python
   !git clone <repo-url>
   %cd <repo-folder>
   ```
2. **Install the OpenAI package:**
   ```python
   !pip install openai
   ```
3. **Set your OpenAI API key:**
   ```python
   import os
   os.environ["OPENAI_API_KEY"] = "sk-..."
   ```
4. **Run the game script:**
   ```python
   !python roguelike_ai.py --seed 1337
   ```

**Note:**
- Colab notebooks are not ideal for interactive input. For best results, use the script in a terminal. If you want to play in Colab, you may need to adapt the code to use notebook cells for input/output.
- The game requires an internet connection and a valid OpenAI API key.

## Commands
- `/help`         Show help menu
- `/look`         Describe the current room
- `/loot`         Pick up all items in the room
- `/inventory`    Show your inventory
- `/stats`        Show your stats
- `/map`          Show a map of the dungeon
- `/save`         Save your game
- `/load`         Load your game
- `/quit` `/exit` Quit the game

You can also type natural language commands (e.g., `Go north`, `Attack the goblin`, `Use health potion`).

## Notes
- The game requires an internet connection to communicate with OpenAI.
- The virtual environment (`.venv`) is provided but you must install `openai` yourself.
- The default model is `gpt-4.1-mini` (change with `--model` if needed).

## License
MIT
