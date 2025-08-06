import pygame
import sys
from roguelike_ai import generate_dungeon, Player, GameState, handle_command, ROOM_TYPES, ENEMIES, LOOT_TABLE, openai, api_call_counter, get_api_call_counter
import random
import copy
import os
import time  # Import time module for timeout logic
import json

# Ensure OpenAI API key is set
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("OpenAI API key not found in environment variables.")
    OPENAI_API_KEY = input("Please enter your OpenAI API key: ")
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Pass the OpenAI API key to roguelike_ai
openai.api_key = OPENAI_API_KEY

# --- Pygame Setup ---
pygame.init()
CELL_SIZE = 120  # Even larger
GRID_W, GRID_H = 6, 6
STATUS_BAR_HEIGHT = 40
WIDTH, HEIGHT = CELL_SIZE * GRID_W + 80 + 320, CELL_SIZE * GRID_H + 400 + STATUS_BAR_HEIGHT  # Add status bar height
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("DungeonGPT Roguelike")
font = pygame.font.SysFont(None, 36)  # Larger font
output_font = pygame.font.SysFont(None, 28)

# --- Load Enemy Sprites ---
def load_enemy_sprites():
    sprite_dict = {}
    # Load basic enemy sprites
    basic_path = 'assets/basic enemies'
    for fname in os.listdir(basic_path):
        if fname.lower().endswith('.png'):
            img = pygame.image.load(os.path.join(basic_path, fname)).convert_alpha()
            img = pygame.transform.smoothscale(img, (48, 48))
            sprite_dict[fname[:-4]] = img  # key is filename without .png
    # Load boss enemy sprites
    boss_path = 'assets/bosses'
    if os.path.exists(boss_path):
        for fname in os.listdir(boss_path):
            if fname.lower().endswith('.png'):
                img = pygame.image.load(os.path.join(boss_path, fname)).convert_alpha()
                img = pygame.transform.smoothscale(img, (64, 64))
                sprite_dict[fname[:-4]] = img
                # Debugging: Print loaded boss sprites
                print("Loaded boss sprites:", [fname[:-4] for fname in os.listdir(boss_path) if fname.lower().endswith('.png')])
    return sprite_dict

enemy_sprites = load_enemy_sprites()

# --- Dungeon Generation ---
def generate_grid_dungeon(seed: int, grid_w: int = 6, grid_h: int = 6) -> dict:
    random.seed(seed)
    rooms = {}
    for y in range(grid_h):
        for x in range(grid_w):
            room_id = f"room_{y*grid_w + x}"
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
                enemy = {**ENEMIES[name], "name": name}
                sprite_keys = [k for k in enemy_sprites if name in k]
                if sprite_keys:
                    enemy['sprite'] = random.choice(sprite_keys)
                else:
                    enemy['sprite'] = None
                rooms[room_id]["enemies"].append(enemy)
            if random.random() < 0.5:
                rooms[room_id]["items"].append(random.choice(LOOT_TABLE))
    # Assign a boss room explicitly after all others are generated since
    # "boss_room" is not part of ROOM_TYPES.
    boss_room = f"room_{grid_w*grid_h-1}"
    rooms[boss_room]["type"] = "boss_room"
    boss_enemy = {**ENEMIES["dungeon_boss"], "name": "dungeon_boss"}
    # Ensure boss sprite assignment
    boss_sprite_keys = [k for k in enemy_sprites if any(word in k.lower() for word in ["boss", "dungeon_boss", "dragon"])]
    if not boss_sprite_keys:
        boss_sprite_keys = list(enemy_sprites.keys())  # fallback: use any sprite
    if boss_sprite_keys:
        boss_enemy['sprite'] = random.choice(boss_sprite_keys)
    else:
        print("Warning: No boss sprites found in assets/bosses.")
        boss_enemy['sprite'] = None
    rooms[boss_room]["enemies"] = [boss_enemy]
    return rooms

# --- Game State ---
seed = 1337
rooms = generate_grid_dungeon(seed, GRID_W, GRID_H)
player = Player(location="room_0")
state = GameState(seed=seed, rooms=rooms, player=player)

# --- Colors ---
BLACK = (20, 20, 30)
WHITE = (240, 240, 240)
GRAY = (60, 60, 80)
BLUE = (80, 180, 255)
GREEN = (80, 220, 120)
RED = (255, 80, 80)
YELLOW = (255, 220, 80)
ROOM_BORDER = (180, 180, 220)
CONNECTION = (60, 60, 120)

# --- Stats Panel Setup ---
STATS_PANEL_WIDTH = 320
stats_panel = pygame.Rect(CELL_SIZE * GRID_W + 80, 0, STATS_PANEL_WIDTH, HEIGHT)

# --- Text Input State ---
input_text = ""
input_active = True
input_box_width = stats_panel.left - 8  # Leave margin before stats panel
input_box = pygame.Rect(0, HEIGHT-STATUS_BAR_HEIGHT-64, input_box_width, 64)  # Adjusted to sit above status bar
input_color = (30, 30, 30)
input_text_color = (200, 255, 200)

# --- Output State ---
output_lines = [
    "Welcome, brave adventurer, to DungeonGPT!",
    "Your quest begins in a mysterious dungeon filled with monsters,",
    "treasures, and untold dangers. Navigate carefully, fight wisely,",
    "and may fortune favor your journey!",
    "",
    "Type /help to see available commands."
]
max_output_lines = 12  # Number of lines visible at once
output_history_limit = 200  # Total lines to keep for scrolling
output_scroll = 0  # Scroll offset
output_area_width = stats_panel.left - 8  # Match input box width
output_area_height = int(320)  # Restore full height for the output area
output_area = pygame.Rect(0, HEIGHT-STATUS_BAR_HEIGHT-64-output_area_height, output_area_width, output_area_height)  # Make output area 10% shorter
output_color = (20, 20, 20)
output_text_color = (255, 255, 180)

# --- Text Wrapping Function ---
def wrap_text(text, font, max_width):
    words = text.split(' ')
    lines = []
    current = ''
    effective_width = int(max_width * 0.8)
    for word in words:
        test = current + (' ' if current else '') + word
        if font.size(test)[0] <= effective_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

# --- Load Hero Sprites ---
def load_hero_sprites():
    hero_dict = {}
    hero_path = 'assets/Hero'
    for fname in os.listdir(hero_path):
        if fname.lower().endswith('.png'):
            img = pygame.image.load(os.path.join(hero_path, fname)).convert_alpha()
            img = pygame.transform.smoothscale(img, (64, 64))
            key = fname[:-4].replace("Rouge", "Rogue")
            hero_dict[key] = img  # key is filename without .png
    return hero_dict

hero_sprites = load_hero_sprites()

# --- Load Backgrounds ---
def load_backgrounds():
    bg_list = []
    bg_path = 'assets/Backgrounds'
    for fname in os.listdir(bg_path):
        if fname.lower().endswith('.png'):
            img = pygame.image.load(os.path.join(bg_path, fname)).convert()
            img = pygame.transform.smoothscale(img, (WIDTH, HEIGHT))
            bg_list.append(img)
    return bg_list

backgrounds = load_backgrounds()
selected_bg = random.choice(backgrounds) if backgrounds else None

# --- Enemy Movement and Spawning Helpers ---
def move_non_boss_enemies(state):
    grid_w, grid_h = GRID_W, GRID_H
    new_rooms = copy.deepcopy(state.rooms)
    for room_id, room in state.rooms.items():
        for enemy in room['enemies'][:]:
            if enemy['name'] == 'dungeon_boss':
                continue  # Boss does not move
            # Move enemy to random adjacent room
            x, y = room['coords']
            directions = [(-1,0),(1,0),(0,-1),(0,1)]
            random.shuffle(directions)
            moved = False
            for dx, dy in directions:
                nx, ny = x+dx, y+dy
                if 0 <= nx < grid_w and 0 <= ny < grid_h:
                    # Find the room at (nx, ny)
                    for dest_id, dest_room in state.rooms.items():
                        if 'coords' in dest_room and dest_room['coords'] == (nx, ny):
                            # Don't move into boss room
                            if dest_room['type'] == 'boss_room':
                                continue
                            # Move enemy
                            new_rooms[room_id]['enemies'].remove(enemy)
                            new_rooms[dest_id]['enemies'].append(enemy)
                            moved = True
                            break
                if moved:
                    break
    state.rooms = new_rooms
    return state

def count_non_boss_enemies(state):
    count = 0
    for room in state.rooms.values():
        for enemy in room['enemies']:
            if enemy['name'] != 'dungeon_boss':
                count += 1
    return count

def spawn_enemy(state):
    # Spawn a new non-boss enemy in a random room not occupied by player or boss
    possible_rooms = [rid for rid, room in state.rooms.items()
                     if room['type'] != 'boss_room' and rid != state.player.location]
    if not possible_rooms:
        return state
    room_id = random.choice(possible_rooms)
    name = random.choice([k for k in ENEMIES if k != 'dungeon_boss'])
    enemy = {**ENEMIES[name], 'name': name}
    # Assign a random sprite for this enemy
    sprite_keys = [k for k in enemy_sprites if name in k]
    if sprite_keys:
        enemy['sprite'] = random.choice(sprite_keys)
    else:
        enemy['sprite'] = None
    new_rooms = copy.deepcopy(state.rooms)
    new_rooms[room_id]['enemies'].append(enemy)
    state.rooms = new_rooms
    return state

# --- Hero Selection Dialog ---
def select_hero():
    dialog_w, dialog_h = 700, 320
    dialog_x = (WIDTH - dialog_w) // 2
    dialog_y = (HEIGHT - dialog_h) // 2
    dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_w, dialog_h)
    pygame.draw.rect(screen, (30,30,60), dialog_rect, border_radius=18)
    pygame.draw.rect(screen, (200,200,255), dialog_rect, 4, border_radius=18)
    title = font.render("Choose Your Hero", True, (255,255,255))
    screen.blit(title, (dialog_x + dialog_w//2 - title.get_width()//2, dialog_y + 24))
    hero_keys = list(hero_sprites.keys())
    spacing = dialog_w // max(1, len(hero_keys))
    btn_rects = []
    for i, key in enumerate(hero_keys):
        img = hero_sprites[key]
        img_rect = img.get_rect(center=(dialog_x + spacing//2 + i*spacing, dialog_y + 120))
        screen.blit(img, img_rect)
        label = output_font.render(key.title(), True, (255,255,255))
        screen.blit(label, (img_rect.centerx - label.get_width()//2, img_rect.bottom + 8))
        btn_rects.append(img_rect)
    pygame.display.flip()
    # Wait for click
    selecting = True
    selected_key = None
    while selecting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pygame.mouse.get_pos()
                for i, rect in enumerate(btn_rects):
                    if rect.collidepoint(mx, my):
                        selected_key = hero_keys[i]
                        selecting = False
    return selected_key

# --- D20 Roll Function ---
def roll_d20():
    return random.randint(1, 20)

# --- D20 Roll Animation ---
def animate_d20_roll(screen, font, roll_result):
    roll_rect = pygame.Rect(WIDTH // 2 - 50, HEIGHT // 2 - 50, 100, 100)
    pygame.draw.rect(screen, (30, 30, 60), roll_rect, border_radius=12)
    pygame.draw.rect(screen, (200, 200, 255), roll_rect, 4, border_radius=12)
    roll_text = font.render(f"D20: {roll_result}", True, (255, 255, 255))
    screen.blit(roll_text, (roll_rect.centerx - roll_text.get_width() // 2, roll_rect.centery - roll_text.get_height() // 2))
    pygame.display.flip()
    pygame.time.delay(1000)

# --- Integrate D20 Roll into Attack Logic ---
def attack_enemy(state, enemy):
    """Roll a d20 and apply damage to the given enemy.

    Returns a tuple of (message, roll_result) so the caller can display the
    roll in the output area and forward the result to the AI for consistent
    narration.
    """
    roll_result = roll_d20()
    animate_d20_roll(screen, font, roll_result)
    damage = roll_result + state.player.str  # Example: Add player's strength to roll
    enemy["hp"] -= damage
    msg = f"You rolled a {roll_result} and dealt {damage} damage to {enemy['name']}!"
    return msg, roll_result

# --- Main Loop ---
running = True
waiting = False
waiting_dots = 0
pending_command = None  # Holds command to process after waiting indicator is shown
flash_timer = 0  # ms, for enemy encounter flash
flash_duration = 200  # ms
battle_dialog = None  # Holds enemy names if a battle dialog should be shown
selected_hero = select_hero()
player_icon = hero_sprites[selected_hero]
# Ensure battle_options is defined before use
battle_options = None
waiting_start_time = None  # Initialize waiting start time
TIMEOUT_DURATION = 10  # seconds
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and input_active:
            if event.key == pygame.K_RETURN:
                if input_text.strip():
                    pending_command = input_text.strip()
                    waiting = True
                    waiting_dots = 0
                    waiting_start_time = time.time()  # Reset waiting start time
                input_text = ""
            elif event.key == pygame.K_BACKSPACE:
                input_text = input_text[:-1]
            elif event.key == pygame.K_PAGEUP:
                if len(output_lines) > max_output_lines:
                    output_scroll = min(output_scroll + 1, len(output_lines) - max_output_lines)
            elif event.key == pygame.K_PAGEDOWN:
                if len(output_lines) > max_output_lines:
                    output_scroll = max(output_scroll - 1, 0)
            else:
                if len(event.unicode) == 1 and 32 <= ord(event.unicode) < 127:
                    input_text += event.unicode
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4:  # Scroll up
                if len(output_lines) > max_output_lines:
                    output_scroll = min(output_scroll + 1, len(output_lines) - max_output_lines)
            elif event.button == 5:  # Scroll down
                if len(output_lines) > max_output_lines:
                    output_scroll = max(output_scroll - 1, 0)

    # Ensure the background fills the screen
    if selected_bg:
        screen.blit(selected_bg, (0, 0))
    else:
        screen.fill(BLACK)  # Fallback to black if no background is selected

    # --- Draw dungeon grid and connections ---
    # Draw connections between rooms
    for room in state.rooms.values():
        x, y = room["coords"]
        cx, cy = x * CELL_SIZE + CELL_SIZE // 2, y * CELL_SIZE + CELL_SIZE // 2
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            nx, ny = x+dx, y+dy
            for other in state.rooms.values():
                if other["coords"] == (nx, ny):
                    ncx, ncy = nx * CELL_SIZE + CELL_SIZE // 2, ny * CELL_SIZE + CELL_SIZE // 2
                    pygame.draw.line(screen, CONNECTION, (cx,cy), (ncx,ncy), 16)
    # Draw rooms with rounded rectangles and shadow
    for room in state.rooms.values():
        x, y = room["coords"]
        rect = pygame.Rect(x*CELL_SIZE+8, y*CELL_SIZE+8, CELL_SIZE-16, CELL_SIZE-16)
        shadow_rect = rect.move(6, 6)
        pygame.draw.rect(screen, (30,30,40), shadow_rect, border_radius=18)
        color = GREEN if room["type"] == "shrine" else YELLOW if room["type"] == "treasure" else RED if room["enemies"] else GRAY if room["visited"] else BLACK
        pygame.draw.rect(screen, color, rect, border_radius=18)
        pygame.draw.rect(screen, ROOM_BORDER, rect, 3, border_radius=18)
        # Draw enemy marker if enemies present
        for enemy in room["enemies"]:
            ex, ey = x*CELL_SIZE + CELL_SIZE//2, y*CELL_SIZE + CELL_SIZE//2
            sprite_key = enemy.get('sprite')
            if sprite_key and sprite_key in enemy_sprites:
                img_rect = enemy_sprites[sprite_key].get_rect(center=(ex, ey))
                screen.blit(enemy_sprites[sprite_key], img_rect)
            elif enemy['name'] == 'slime' and 'slime' in enemy_sprites:
                img_rect = enemy_sprites['slime'].get_rect(center=(ex, ey))
                screen.blit(enemy_sprites['slime'], img_rect)
            else:
                pygame.draw.circle(screen, (220, 60, 60), (ex, ey), 18)
                e_txt = output_font.render("E", True, (255,255,255))
                screen.blit(e_txt, (ex - e_txt.get_width()//2, ey - e_txt.get_height()//2))
    # Draw player with hero icon
    px, py = state.rooms[state.player.location]["coords"]
    prect = pygame.Rect(px*CELL_SIZE+28, py*CELL_SIZE+28, CELL_SIZE-56, CELL_SIZE-56)
    glow_rect = prect.inflate(24, 24)
    pygame.draw.ellipse(screen, (80,180,255,80), glow_rect)
    if player_icon:
        img_rect = player_icon.get_rect(center=prect.center)
        screen.blit(player_icon, img_rect)
    else:
        pygame.draw.ellipse(screen, BLUE, prect)
    # Draw room type text
    type_abbr = {
        "enemy_lair": "EN",
        "treasure": "TR",
        "shrine": "SH",
        "boss_room": "BO",
        "locked": "LO",
        "corridor": "CO",
        "trap": "TRP",
        "entrance": "EN"
    }
    for room in state.rooms.values():
        x, y = room["coords"]
        abbr = type_abbr.get(room["type"], room["type"][:2].upper())
        label = font.render(abbr, True, WHITE)
        screen.blit(label, (x*CELL_SIZE+20, y*CELL_SIZE+20))
    # Draw output area with border
    pygame.draw.rect(screen, output_color, output_area, border_radius=12)
    pygame.draw.rect(screen, ROOM_BORDER, output_area, 2, border_radius=12)
    start = max(0, len(output_lines) - max_output_lines - output_scroll)
    end = start + max_output_lines
    for i, line in enumerate(output_lines[start:end]):
        txt = output_font.render(line, True, output_text_color)
        screen.blit(txt, (output_area.x+16, output_area.y+12 + i*24))
    # Draw scroll indicator
    if len(output_lines) > max_output_lines:
        scroll_bar_height = max(32, int(max_output_lines / len(output_lines) * output_area.height))
        scroll_bar_y = int(output_area.y + (output_scroll / max(1, len(output_lines) - max_output_lines)) * (output_area.height - scroll_bar_height))
        pygame.draw.rect(screen, (100, 100, 160), (output_area.right - 12, scroll_bar_y, 8, scroll_bar_height), border_radius=4)
    # Draw input box with border
    pygame.draw.rect(screen, input_color, input_box, border_radius=12)
    pygame.draw.rect(screen, ROOM_BORDER, input_box, 2, border_radius=12)
    txt_surface = font.render(input_text, True, input_text_color)
    screen.blit(txt_surface, (input_box.x+16, input_box.y+18))
    # Draw cursor
    cursor_x = input_box.x + 16 + txt_surface.get_width()
    cursor_y = input_box.y + 18
    cursor_height = txt_surface.get_height()
    if (pygame.time.get_ticks() // 500) % 2 == 0:  # Blinking cursor
        pygame.draw.line(screen, input_text_color, (cursor_x, cursor_y), (cursor_x, cursor_y + cursor_height), 3)

    # --- Status Bar ---
    status_bar_rect = pygame.Rect(0, HEIGHT-STATUS_BAR_HEIGHT, WIDTH, STATUS_BAR_HEIGHT)
    pygame.draw.rect(screen, (30, 30, 50), status_bar_rect, border_radius=8)
    pygame.draw.rect(screen, ROOM_BORDER, status_bar_rect, 2, border_radius=8)
    if waiting:
        if waiting_start_time is None:
            waiting_start_time = time.time()
        elif time.time() - waiting_start_time > TIMEOUT_DURATION:
            waiting = False
            pending_command = None
            waiting_start_time = None
            output_lines.append("Dungeon Master did not respond in time. Please try again.")
            output_scroll = 0
        else:
            dots = '.' * ((pygame.time.get_ticks() // 400) % 4)
            wait_txt = output_font.render(f"Waiting for Dungeon Master{dots} (API Calls: {get_api_call_counter()})", True, (180, 180, 255))
            txt_x = status_bar_rect.x+16
            txt_y = status_bar_rect.y + (STATUS_BAR_HEIGHT - wait_txt.get_height()) // 2
            screen.blit(wait_txt, (txt_x, txt_y))
    # --- Stats Panel ---
    pygame.draw.rect(screen, (28, 28, 40), stats_panel)
    pygame.draw.rect(screen, ROOM_BORDER, stats_panel, 3)
    stats_y = 24
    stats_x = stats_panel.x + 24
    p = state.player
    stats_lines = [
        f"HP: {p.hp}",
        f"STR: {p.str}",
        f"DEX: {p.dex}",
        f"LVL: {p.level}",
        f"XP: {p.xp}/{p.level*100}",
        "",
        "Inventory:",
    ]
    inv = p.inventory if p.inventory else ["(empty)"]
    stats_lines.extend(inv)
    for line in stats_lines:
        txt = output_font.render(line, True, (220, 220, 255))
        screen.blit(txt, (stats_x, stats_y))
        stats_y += 32
    # Draw legend at the bottom of the stats panel (draw upward to avoid cutoff)
    legend_lines = [
        "Legend:",
        "EN = Enemy room",
        "TR = Treasure",
        "SH = Shrine",
        "BO = Boss",
        "LO = Locked",
        "CO = Corridor",
        "TRP = Trap",
        "E (red) = Enemy present",
        "@ = You (player)",
    ]
    legend_line_height = 22  # Slightly smaller spacing for legend
    legend_y = stats_panel.bottom - 24 - legend_line_height * (len(legend_lines) - 1)
    for line in legend_lines:
        txt = output_font.render(line, True, (180, 220, 180))
        screen.blit(txt, (stats_x, legend_y))
        legend_y += legend_line_height

    # Draw Send button after stats panel so it's always visible
    send_btn_width, send_btn_height = 90, 44
    send_btn_rect = pygame.Rect(input_box.right - send_btn_width - 16, input_box.y + 10, send_btn_width, send_btn_height)
    # No need to check overlap, input_box now ends before stats panel
    pygame.draw.rect(screen, (60, 120, 60), send_btn_rect, border_radius=10)
    pygame.draw.rect(screen, (120, 200, 120), send_btn_rect, 2, border_radius=10)
    send_txt = font.render("Send", True, (255,255,255))
    screen.blit(send_txt, (send_btn_rect.centerx - send_txt.get_width()//2, send_btn_rect.centery - send_txt.get_height()//2))

    pygame.display.flip()

    # Handle Send button click
    if pygame.mouse.get_pressed()[0]:
        mx, my = pygame.mouse.get_pos()
        if send_btn_rect.collidepoint(mx, my) and input_active and input_text.strip():
            pending_command = input_text.strip()
            waiting = True
            waiting_dots = 0
            waiting_start_time = time.time()  # Reset waiting start time
            input_text = ""
        while pygame.mouse.get_pressed()[0]:
            pygame.event.pump()

    # Process pending command after waiting indicator is shown
    if waiting and pending_command:
        prev_location = state.player.location
        roll_result_to_send = None
        output_lines = [f"> {pending_command}"]
        if battle_options:
            cmd_lower = pending_command.lower()
            selected_option = None
            if cmd_lower.isdigit():
                idx = int(cmd_lower) - 1
                if 0 <= idx < len(battle_options):
                    selected_option = battle_options[idx]
            else:
                for opt in battle_options:
                    if cmd_lower in opt.lower():
                        selected_option = opt
                        break
            if selected_option and "attack" in selected_option.lower():
                room = state.rooms.get(state.player.location, {})
                target_enemy = next((e for e in room.get('enemies', []) if e.get('hp', 0) > 0), None)
                if target_enemy:
                    atk_msg, roll_result_to_send = attack_enemy(state, target_enemy)
                    for line in wrap_text(atk_msg, output_font, output_area.width-32):
                        output_lines.append(line)
                    if target_enemy["hp"] <= 0:
                        room["enemies"].remove(target_enemy)
                        state.player.give_xp(target_enemy.get("xp", 0))
                        output_lines.append(f"The {target_enemy['name'].replace('_', ' ')} is defeated!")
                pending_command = "attack"
        try:
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                result = handle_command(pending_command, state, "gpt-4.1-mini", roll_result_to_send, None)
            narrative = ""
            options = []
            force_option_select = False
            state_delta = None
            if isinstance(result, dict):
                narrative = result.get('narrative', '')
                options = result.get('options', [])
                force_option_select = result.get('force_option_select', False)
                state_delta = result.get('state_delta', None)
                if not options:
                    for line in narrative.split('\n'):
                        if line.strip().startswith(tuple(str(i)+'.' for i in range(1,10))):
                            options.append(line.strip())
            elif isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    narrative = parsed.get('narrative', '')
                    options = parsed.get('options', [])
                    force_option_select = parsed.get('force_option_select', False)
                    state_delta = parsed.get('state_delta', None)
                    if not options:
                        for line in narrative.split('\n'):
                            if line.strip().startswith(tuple(str(i)+'.' for i in range(1,10))):
                                options.append(line.strip())
                except Exception:
                    narrative = result
            else:
                narrative = "(No narrative returned)"
            if state_delta and isinstance(state_delta, dict):
                if 'player' in state_delta and isinstance(state_delta['player'], dict):
                    for k, v in state_delta['player'].items():
                        setattr(state.player, k, v)
            if narrative:
                for para in narrative.split('\n'):
                    for line in wrap_text(para, output_font, output_area.width-32):
                        output_lines.append(line)
            battle_options = options if options else None
            battle_force_select = force_option_select if options else False
        except Exception as e:
            output_lines.append(f"Error: {e}")
            battle_options = None
            battle_force_select = False
        output_lines = output_lines[-output_history_limit:]
        output_scroll = 0
        input_text = ""  # Clear input after response
        # Only move/spawn enemies if not in battle dialog
        if not battle_options:
            state = move_non_boss_enemies(state)
            while count_non_boss_enemies(state) < 2:
                state = spawn_enemy(state)
        # Flash if entered a room with enemies
        new_room = state.rooms.get(state.player.location, {})
        if state.player.location != prev_location and new_room.get("enemies"):
            flash_timer = pygame.time.get_ticks() + flash_duration
            # Prepare battle dialog
            enemy_names = [e['name'].replace('_', ' ').title() for e in new_room.get('enemies',[])]
            battle_dialog = enemy_names
        waiting = False
        pending_command = None
        # --- Game Over Check ---
        if state.player.hp <= 0:
            # Show Game Over dialog
            dialog_w, dialog_h = 480, 220
            dialog_x = (WIDTH - dialog_w) // 2
            dialog_y = (HEIGHT - dialog_h) // 2
            dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_w, dialog_h)
            pygame.draw.rect(screen, (40,0,0), dialog_rect, border_radius=18)
            pygame.draw.rect(screen, (255,80,80), dialog_rect, 4, border_radius=18)
            title = font.render("Game Over!", True, (255,255,255))
            screen.blit(title, (dialog_x + dialog_w//2 - title.get_width()//2, dialog_y + 32))
            msg = output_font.render("You have perished in the dungeon.", True, (255,200,200))
            screen.blit(msg, (dialog_x + dialog_w//2 - msg.get_width()//2, dialog_y + 80))
            # Draw buttons
            btns = []
            btn_labels = ["Play Again", "Exit"]
            for i, label in enumerate(btn_labels):
                btn_w, btn_h = 180, 48
                btn_rect = pygame.Rect(dialog_x + 40 + i*220, dialog_y + dialog_h - btn_h - 32, btn_w, btn_h)
                pygame.draw.rect(screen, (60,60,120), btn_rect, border_radius=12)
                pygame.draw.rect(screen, (120,120,200), btn_rect, 2, border_radius=12)
                btn_txt = font.render(label, True, (255,255,255))
                screen.blit(btn_txt, (btn_rect.centerx - btn_txt.get_width()//2, btn_rect.centery - btn_txt.get_height()//2))
                btns.append((btn_rect, label))
            pygame.display.flip()
            # Wait for button click
            game_over = True
            while game_over:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        mx, my = pygame.mouse.get_pos()
                        for btn_rect, label in btns:
                            if btn_rect.collidepoint(mx, my):
                                if label == "Play Again":
                                    # Reset game state
                                    seed = random.randint(1, 999999)
                                    rooms = generate_grid_dungeon(seed, GRID_W, GRID_H)
                                    player = Player(location="room_0")
                                    state = GameState(seed=seed, rooms=rooms, player=player)
                                    selected_hero = select_hero()
                                    player_icon = hero_sprites[selected_hero]
                                    game_over = False
                                elif label == "Exit":
                                    pygame.quit()
                                    sys.exit()
            continue  # Skip rest of loop after game over

    # After setting pending_command, immediately process the command
    if pending_command:
        prev_location = state.player.location
        roll_result_to_send = None
        output_lines = [f"> {pending_command}"]
        if battle_options:
            cmd_lower = pending_command.lower()
            selected_option = None
            if cmd_lower.isdigit():
                idx = int(cmd_lower) - 1
                if 0 <= idx < len(battle_options):
                    selected_option = battle_options[idx]
            else:
                for opt in battle_options:
                    if cmd_lower in opt.lower():
                        selected_option = opt
                        break
            if selected_option and "attack" in selected_option.lower():
                room = state.rooms.get(state.player.location, {})
                target_enemy = next((e for e in room.get('enemies', []) if e.get('hp', 0) > 0), None)
                if target_enemy:
                    atk_msg, roll_result_to_send = attack_enemy(state, target_enemy)
                    for line in wrap_text(atk_msg, output_font, output_area.width-32):
                        output_lines.append(line)
                    if target_enemy["hp"] <= 0:
                        room["enemies"].remove(target_enemy)
                        state.player.give_xp(target_enemy.get("xp", 0))
                        output_lines.append(f"The {target_enemy['name'].replace('_', ' ')} is defeated!")
                pending_command = "attack"
        try:
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                result = handle_command(pending_command, state, "gpt-4.1-mini", roll_result_to_send, None)
            narrative = ""
            options = []
            force_option_select = False
            state_delta = None
            if isinstance(result, dict):
                narrative = result.get('narrative', '')
                options = result.get('options', [])
                force_option_select = result.get('force_option_select', False)
                state_delta = result.get('state_delta', None)
                if not options:
                    for line in narrative.split('\n'):
                        if line.strip().startswith(tuple(str(i)+'.' for i in range(1,10))):
                            options.append(line.strip())
            elif isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    narrative = parsed.get('narrative', '')
                    options = parsed.get('options', [])
                    force_option_select = parsed.get('force_option_select', False)
                    state_delta = parsed.get('state_delta', None)
                    if not options:
                        for line in narrative.split('\n'):
                            if line.strip().startswith(tuple(str(i)+'.' for i in range(1,10))):
                                options.append(line.strip())
                except Exception:
                    narrative = result
            else:
                narrative = "(No narrative returned)"
            if state_delta and isinstance(state_delta, dict):
                if 'player' in state_delta and isinstance(state_delta['player'], dict):
                    for k, v in state_delta['player'].items():
                        setattr(state.player, k, v)
            if narrative:
                for para in narrative.split('\n'):
                    for line in wrap_text(para, output_font, output_area.width-32):
                        output_lines.append(line)
            battle_options = options if options else None
            battle_force_select = force_option_select if options else False
        except Exception as e:
            output_lines.append(f"Error: {e}")
            battle_options = None
            battle_force_select = False
        output_lines = output_lines[-output_history_limit:]
        output_scroll = 0
        input_text = ""
        if not battle_options:
            state = move_non_boss_enemies(state)
            while count_non_boss_enemies(state) < 2:
                state = spawn_enemy(state)
        new_room = state.rooms.get(state.player.location, {})
        if state.player.location != prev_location and new_room.get("enemies"):
            flash_timer = pygame.time.get_ticks() + flash_duration
            enemy_names = [e['name'].replace('_', ' ').title() for e in new_room.get('enemies',[])]
            battle_dialog = enemy_names
        else:
            battle_dialog = None
            battle_options = None
            battle_force_select = False
        waiting = False
        pending_command = None
        # --- Game Over Check ---
        if state.player.hp <= 0:
            dialog_w, dialog_h = 480, 220
            dialog_x = (WIDTH - dialog_w) // 2
            dialog_y = (HEIGHT - dialog_h) // 2
            dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_w, dialog_h)
            pygame.draw.rect(screen, (40,0,0), dialog_rect, border_radius=18)
            pygame.draw.rect(screen, (255,80,80), dialog_rect, 4, border_radius=18)
            title = font.render("Game Over!", True, (255,255,255))
            screen.blit(title, (dialog_x + dialog_w//2 - title.get_width()//2, dialog_y + 32))
            msg = output_font.render("You have perished in the dungeon.", True, (255,200,200))
            screen.blit(msg, (dialog_x + dialog_w//2 - msg.get_width()//2, dialog_y + 80))
            btns = []
            btn_labels = ["Play Again", "Exit"]
            for i, label in enumerate(btn_labels):
                btn_w, btn_h = 180, 48
                btn_rect = pygame.Rect(dialog_x + 40 + i*220, dialog_y + dialog_h - btn_h - 32, btn_w, btn_h)
                pygame.draw.rect(screen, (60,60,120), btn_rect, border_radius=12)
                pygame.draw.rect(screen, (120,120,200), btn_rect, 2, border_radius=12)
                btn_txt = font.render(label, True, (255,255,255))
                screen.blit(btn_txt, (btn_rect.centerx - btn_txt.get_width()//2, btn_rect.centery - btn_txt.get_height()//2))
                btns.append((btn_rect, label))
            pygame.display.flip()
            game_over = True
            while game_over:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        mx, my = pygame.mouse.get_pos()
                        for btn_rect, label in btns:
                            if btn_rect.collidepoint(mx, my):
                                if label == "Play Again":
                                    seed = random.randint(1, 999999)
                                    rooms = generate_grid_dungeon(seed, GRID_W, GRID_H)
                                    player = Player(location="room_0")
                                    state = GameState(seed=seed, rooms=rooms, player=player)
                                    selected_hero = select_hero()
                                    player_icon = hero_sprites[selected_hero]
                                    game_over = False
                                elif label == "Exit":
                                    pygame.quit()
                                    sys.exit()
            continue

pygame.quit()
sys.exit()
