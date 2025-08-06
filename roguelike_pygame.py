import pygame
import sys
from roguelike_ai import generate_dungeon, Player, GameState, handle_command, ROOM_TYPES, ENEMIES, LOOT_TABLE
import random

# --- Pygame Setup ---
pygame.init()
CELL_SIZE = 120  # Even larger
GRID_W, GRID_H = 6, 6
WIDTH, HEIGHT = CELL_SIZE * GRID_W + 80, CELL_SIZE * GRID_H + 400  # More width and height
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

# --- Text Input State ---
input_text = ""
input_active = True
input_box = pygame.Rect(0, HEIGHT-64, WIDTH, 64)  # Taller input box
input_color = (30, 30, 30)
input_text_color = (200, 255, 200)

# --- Output State ---
output_lines = ["Welcome to DungeonGPT! Type /help for commands."]
max_output_lines = 12  # Increased from 4
output_area = pygame.Rect(0, HEIGHT-64-320, WIDTH, 320)  # Make output area taller
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

# --- Main Loop ---
running = True
waiting = False
waiting_dots = 0
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and input_active:
            if event.key == pygame.K_RETURN:
                if input_text.strip():
                    waiting = True
                    waiting_dots = 0
                    # Process command using handle_command
                    try:
                        import io
                        import contextlib
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf):
                            state = handle_command(input_text.strip(), state, "gpt-4.1-mini", None)
                        narrative = buf.getvalue().strip()
                        output_lines = [f"> {input_text.strip()}"]
                        if narrative:
                            for para in narrative.split('\n'):
                                for line in wrap_text(para, output_font, output_area.width-32):
                                    output_lines.append(line)
                    except Exception as e:
                        output_lines = [f"Error: {e}"]
                    output_lines = output_lines[-max_output_lines:]
                    waiting = False
                input_text = ""
            elif event.key == pygame.K_BACKSPACE:
                input_text = input_text[:-1]
            else:
                if len(event.unicode) == 1 and 32 <= ord(event.unicode) < 127:
                    input_text += event.unicode

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
    for i, line in enumerate(output_lines[-max_output_lines:]):
        txt = output_font.render(line, True, output_text_color)
        screen.blit(txt, (output_area.x+16, output_area.y+12 + i*24))
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
    pygame.display.flip()

pygame.quit()
sys.exit()
