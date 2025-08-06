import pygame
import sys
from roguelike_ai import generate_dungeon, Player, GameState, handle_command, ROOM_TYPES, ENEMIES, LOOT_TABLE
import random
import copy

# --- Pygame Setup ---
pygame.init()
CELL_SIZE = 120  # Even larger
GRID_W, GRID_H = 6, 6
WIDTH, HEIGHT = CELL_SIZE * GRID_W + 80 + 320, CELL_SIZE * GRID_H + 400  # More width and height
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("DungeonGPT Roguelike")
font = pygame.font.SysFont(None, 36)  # Larger font
output_font = pygame.font.SysFont(None, 28)

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
                rooms[room_id]["enemies"].append({**ENEMIES[name], "name": name})
            if random.random() < 0.5:
                rooms[room_id]["items"].append(random.choice(LOOT_TABLE))
    # Place boss room at farthest cell
    boss_room = f"room_{grid_w*grid_h-1}"
    rooms[boss_room]["type"] = "boss_room"
    rooms[boss_room]["enemies"] = [{**ENEMIES["dungeon_boss"], "name": "dungeon_boss"}]
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
input_box = pygame.Rect(0, HEIGHT-64, input_box_width, 64)  # Adjusted width
input_color = (30, 30, 30)
input_text_color = (200, 255, 200)

# --- Output State ---
output_lines = ["Welcome to DungeonGPT! Type /help for commands."]
max_output_lines = 12  # Number of lines visible at once
output_history_limit = 200  # Total lines to keep for scrolling
output_scroll = 0  # Scroll offset
output_area_width = stats_panel.left - 8  # Match input box width
output_area = pygame.Rect(0, HEIGHT-64-320, output_area_width, 320)  # Make output area taller
output_color = (20, 20, 20)
output_text_color = (255, 255, 180)

# --- Text Wrapping Function ---
def wrap_text(text, font, max_width):
    words = text.split(' ')
    lines = []
    current = ''
    for word in words:
        test = current + (' ' if current else '') + word
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

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
                        if dest_room['coords'] == (nx, ny):
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
    new_rooms = copy.deepcopy(state.rooms)
    new_rooms[room_id]['enemies'].append(enemy)
    state.rooms = new_rooms
    return state

# --- Load Enemy Sprites ---
slime_img = pygame.image.load('assets/basic enemies/slime.png').convert_alpha()
slime_img = pygame.transform.smoothscale(slime_img, (48, 48))

# --- Main Loop ---
running = True
waiting = False
waiting_dots = 0
pending_command = None  # Holds command to process after waiting indicator is shown
flash_timer = 0  # ms, for enemy encounter flash
flash_duration = 200  # ms
battle_dialog = None  # Holds enemy names if a battle dialog should be shown
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
                input_text = ""
            elif event.key == pygame.K_BACKSPACE:
                input_text = input_text[:-1]
            elif event.key == pygame.K_PAGEUP:
                output_scroll = min(output_scroll + 1, max(0, len(output_lines) - max_output_lines))
            elif event.key == pygame.K_PAGEDOWN:
                output_scroll = max(output_scroll - 1, 0)
            else:
                if len(event.unicode) == 1 and 32 <= ord(event.unicode) < 127:
                    input_text += event.unicode
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 4:  # Scroll up
                output_scroll = min(output_scroll + 1, max(0, len(output_lines) - max_output_lines))
            elif event.button == 5:  # Scroll down
                output_scroll = max(output_scroll - 1, 0)

    screen.fill(BLACK)
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
            if enemy['name'] == 'slime':
                img_rect = slime_img.get_rect(center=(ex, ey))
                screen.blit(slime_img, img_rect)
            else:
                pygame.draw.circle(screen, (220, 60, 60), (ex, ey), 18)
                e_txt = output_font.render("E", True, (255,255,255))
                screen.blit(e_txt, (ex - e_txt.get_width()//2, ey - e_txt.get_height()//2))
    # Draw player with glow
    px, py = state.rooms[state.player.location]["coords"]
    prect = pygame.Rect(px*CELL_SIZE+28, py*CELL_SIZE+28, CELL_SIZE-56, CELL_SIZE-56)
    glow_rect = prect.inflate(24, 24)
    pygame.draw.ellipse(screen, (80,180,255,80), glow_rect)
    pygame.draw.ellipse(screen, BLUE, prect)
    # Draw room type text
    for room in state.rooms.values():
        x, y = room["coords"]
        label = font.render(room["type"][:2].upper(), True, WHITE)
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
    # Draw waiting indicator if needed
    if waiting:
        dots = '.' * ((pygame.time.get_ticks() // 400) % 4)
        wait_txt = output_font.render(f"Waiting for Dungeon Master{dots}", True, (180, 180, 255))
        screen.blit(wait_txt, (output_area.x+16, output_area.y+12 + (max_output_lines-1)*24))
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
            input_text = ""
        while pygame.mouse.get_pressed()[0]:
            pygame.event.pump()

    # Process pending command after waiting indicator is shown
    if waiting and pending_command:
        prev_location = state.player.location
        try:
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                state = handle_command(pending_command, state, "gpt-4.1-mini", None)
            narrative = buf.getvalue().strip()
            # Clear output area before showing new response
            output_lines = []
            output_lines.append(f"> {pending_command}")
            if narrative:
                for para in narrative.split('\n'):
                    for line in wrap_text(para, output_font, output_area.width-32):
                        output_lines.append(line)
        except Exception as e:
            output_lines = [f"Error: {e}"]
        output_lines = output_lines[-output_history_limit:]
        output_scroll = 0
        input_text = ""  # Clear input after response
        # Move non-boss enemies
        state = move_non_boss_enemies(state)
        # Ensure there are always 2 non-boss enemies
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

    # Draw flash overlay if needed
    if flash_timer and pygame.time.get_ticks() < flash_timer:
        s = pygame.Surface((WIDTH, HEIGHT))
        s.set_alpha(200)
        s.fill((255,255,255))
        screen.blit(s, (0,0))
        pygame.display.flip()
    elif flash_timer and pygame.time.get_ticks() >= flash_timer:
        flash_timer = 0

    # Draw battle dialog if needed
    if battle_dialog:
        dialog_w, dialog_h = 600, 180
        dialog_x = (WIDTH - dialog_w) // 2
        dialog_y = (HEIGHT - dialog_h) // 2
        dialog_rect = pygame.Rect(dialog_x, dialog_y, dialog_w, dialog_h)
        pygame.draw.rect(screen, (30,30,60), dialog_rect, border_radius=18)
        pygame.draw.rect(screen, (200,200,255), dialog_rect, 4, border_radius=18)
        msg = f"A wild {', '.join(battle_dialog)} appears!"
        msg_lines = wrap_text(msg, font, dialog_w-40)
        for i, line in enumerate(msg_lines):
            txt = font.render(line, True, (255,255,255))
            screen.blit(txt, (dialog_x+24, dialog_y+32 + i*38))
        # Draw Continue button
        btn_w, btn_h = 180, 48
        btn_rect = pygame.Rect(dialog_x + dialog_w//2 - btn_w//2, dialog_y + dialog_h - btn_h - 16, btn_w, btn_h)
        pygame.draw.rect(screen, (60,120,60), btn_rect, border_radius=12)
        pygame.draw.rect(screen, (120,200,120), btn_rect, 2, border_radius=12)
        btn_txt = font.render("Continue", True, (255,255,255))
        screen.blit(btn_txt, (btn_rect.centerx - btn_txt.get_width()//2, btn_rect.centery - btn_txt.get_height()//2))
        pygame.display.flip()
        # Wait for click or Enter
        waiting_for_continue = True
        while waiting_for_continue:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.KEYDOWN and (event.key == pygame.K_RETURN or event.key == pygame.K_SPACE):
                    waiting_for_continue = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    if btn_rect.collidepoint(mx, my):
                        waiting_for_continue = False
        battle_dialog = None

pygame.quit()
sys.exit()
