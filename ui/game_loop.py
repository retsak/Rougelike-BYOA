def run():
    import pygame
    import sys
    import openai
    import random
    import os
    import time  # Import time module for timeout logic
    import json
    from tts_engine import dm_say
    from ui.assets import (
        load_enemy_sprites,
        load_hero_sprites,
        load_backgrounds,
        pick_background_for_room,
        load_ambient_loops,
        pick_loop_for_room,
    )
    from config import AMBIENT_VOLUME
    from ui.gameplay import (
        move_non_boss_enemies,
        count_non_boss_enemies,
        spawn_enemy,
        attack_enemy,
    )

    from core.grid import generate_grid_dungeon
    from core.models import Player, GameState
    from ai import handle_command, get_api_call_counter
    from ui.dialogs import select_hero, game_over_dialog, HERO_STATS

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
    # Adaptive timing / vsync
    clock = pygame.time.Clock()
    vsync_enabled = False  # toggled with F8
    last_activity_time = time.time()

    # --- Load Enemy Sprites ---
    enemy_sprites = load_enemy_sprites()

    # --- Game State ---
    seed = 1337
    rooms = generate_grid_dungeon(seed, GRID_W, GRID_H)
    for room in rooms.values():
        for enemy in room["enemies"]:
            sprite_keys = [k for k in enemy_sprites if enemy["name"] in k]
            enemy["sprite"] = random.choice(sprite_keys) if sprite_keys else None
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
    # --- Input History & Auto-scroll state ---
    input_history = []  # stores prior entered commands
    history_index = -1  # -1 means new entry
    was_at_bottom = True  # track whether user was at bottom before adding new lines

    # --- Action Buttons (meta commands) ---
    action_labels = ["/look", "/loot", "/inventory", "/stats", "/ability", "/map"]
    action_button_rects = []  # populated each frame
    show_inventory_panel = False
    inventory_grid_rects = []  # (item, rect)
    hovered_inventory_item = None
    selected_inventory_item = None

    # --- Battle Option Buttons ---
    battle_button_rects = []  # clickable numbered options when presented

    # --- Tooltip / Hover ---
    hover_room_id = None

    # --- Output State ---
    intro_text = (
        "Welcome, brave adventurer! Your quest begins in a "
        "mysterious dungeon filled with monsters, treasures, and untold dangers. "
        "Navigate carefully, fight wisely, and may fortune favor your journey!"
    )
    dm_say(intro_text)
    output_lines = [
        "Welcome, brave adventurer! Your quest begins in a "
        "mysterious dungeon filled with monsters, treasures, and untold dangers. "
        "Navigate carefully, fight wisely, and may fortune favor your journey!"
    ]
    # New structured logs
    scene_log = list(output_lines)  # full narrative history
    active_log_tab = 'scene'  # 'scene' or 'combat'
    log_search_query = ''
    search_focused = False
    collapse_older = True
    collapsed_visible_tail = 120  # number of recent scene lines to show when collapsing
    max_output_lines = 12  # initial placeholder; recalculated after output area setup
    output_history_limit = 200  # Total lines to keep for scrolling
    output_scroll = 0  # Scroll offset
    total_wrapped_lines = 0  # current count of wrapped lines in active log view
    output_area_width = stats_panel.left - 8  # Match input box width
    # Reserve a horizontal action bar gap between log and input so buttons don't overlap wrapped text
    ACTION_BAR_HEIGHT = 60
    raw_output_area_height = 320
    output_area_height = raw_output_area_height - ACTION_BAR_HEIGHT
    output_area = pygame.Rect(0, HEIGHT-STATUS_BAR_HEIGHT-64-raw_output_area_height, output_area_width, output_area_height)
    output_color = (20, 20, 20)
    output_text_color = (255, 255, 180)
    # Recalculate max_output_lines to fit inside output_area (line height 24, top pad ~12)
    max_output_lines = max(4, (output_area.height - 12) // 24)

    # --- Wrapping Cache (performance) ---
    # Key: (text, width) -> list[str] wrapped lines
    wrap_cache = {}
    wrap_cache_order = []  # maintain insertion order for simple LRU trimming
    WRAP_CACHE_LIMIT = 6000  # max distinct entries

    def get_wrapped_cached(raw_text, width):
        """Return wrapped lines for raw_text using cache; only wrap once per width."""
        key = (raw_text, width)
        cached = wrap_cache.get(key)
        if cached is not None:
            return cached
        # Compute and store
        if not raw_text:
            lines = ['']
        elif output_font.size(raw_text)[0] <= width:
            lines = [raw_text]
        else:
            lines = wrap_text(raw_text, output_font, width)
        wrap_cache[key] = lines
        wrap_cache_order.append(key)
        # Trim cache if above limit (simple FIFO / approximate LRU)
        if len(wrap_cache_order) > WRAP_CACHE_LIMIT:
            drop_n = len(wrap_cache_order) - WRAP_CACHE_LIMIT
            for _ in range(drop_n):
                old_key = wrap_cache_order.pop(0)
                wrap_cache.pop(old_key, None)
        return lines

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
    hero_sprites = load_hero_sprites()

    # --- Load Backgrounds ---
    pygame.mixer.init()
    backgrounds = load_backgrounds(WIDTH, HEIGHT)
    ambient_loops = load_ambient_loops()
    current_loop = None
    selected_bg = None
    parallax_offset = [0,0]
    parallax_speed = 0.2

    # --- Main Loop ---
    running = True
    waiting = False
    waiting_dots = 0
    pending_command = None  # Holds command to process after waiting indicator is shown
    flash_timer = 0  # ms, for enemy encounter flash
    flash_duration = 200  # ms
    battle_dialog = None  # Holds enemy names if a battle dialog should be shown
    combat_log = []  # condensed per-round combat messages (also viewable via Combat tab)
    show_dice_breakdown = False
    selected_hero = select_hero(screen, hero_sprites, font, output_font, WIDTH, HEIGHT)
    # Apply selected hero stats to the player
    stats = HERO_STATS.get(selected_hero, {})
    player.hp = stats.get("hp", player.hp)
    player.str = stats.get("str", player.str)
    player.dex = stats.get("dex", player.dex)
    player.ability = stats.get("ability")
    player_icon = hero_sprites[selected_hero]
    # Ensure battle_options is defined before use
    battle_options = None
    waiting_start_time = None  # Initialize waiting start time
    TIMEOUT_DURATION = 10  # seconds
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and input_active and not search_focused:
                if event.key == pygame.K_RETURN:
                    if input_text.strip():
                        raw_cmd = input_text.strip()
                        head = raw_cmd.split(' ')[0].lower()
                        if head in {"move","go","walk","run","flee","look"}:
                            raw_cmd = f"[BRIEF] {raw_cmd}"
                        # push to history
                        if not input_history or (input_history and raw_cmd != input_history[-1]):
                            input_history.append(raw_cmd)
                        history_index = -1
                        pending_command = raw_cmd
                        waiting = True
                        waiting_dots = 0
                        waiting_start_time = time.time()  # Reset waiting start time
                    input_text = ""
                elif event.key == pygame.K_UP:
                    # navigate history (older)
                    if input_history:
                        if history_index == -1:
                            history_index = len(input_history) - 1
                        else:
                            history_index = max(0, history_index - 1)
                        input_text = input_history[history_index]
                elif event.key == pygame.K_DOWN:
                    if input_history and history_index != -1:
                        history_index += 1
                        if history_index >= len(input_history):
                            history_index = -1
                            input_text = ""
                        else:
                            input_text = input_history[history_index]
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                elif event.key == pygame.K_i:
                    show_inventory_panel = not show_inventory_panel
                elif event.key == pygame.K_d:
                    show_dice_breakdown = not show_dice_breakdown
                elif event.key == pygame.K_F8:
                    # Toggle vsync (recreate display surface)
                    vsync_enabled = not vsync_enabled
                    try:
                        # Try requesting vsync (pygame 2+)
                        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.DOUBLEBUF, vsync=1 if vsync_enabled else 0)
                        scene_log.append(f"[system] VSync {'enabled' if vsync_enabled else 'disabled'}.")
                    except Exception:
                        # Fallback without vsync flag, disable toggle
                        try:
                            screen = pygame.display.set_mode((WIDTH, HEIGHT))
                        except Exception:
                            pass
                        if vsync_enabled:
                            scene_log.append("[system] VSync not supported on this platform/driver.")
                        vsync_enabled = False
                    # Input activity update
                    last_activity_time = time.time()
                elif event.key == pygame.K_PAGEUP:
                    if total_wrapped_lines > max_output_lines:
                        # Move view up (earlier lines)
                        output_scroll = max(output_scroll - 1, 0)
                elif event.key == pygame.K_PAGEDOWN:
                    if total_wrapped_lines > max_output_lines:
                        # Move view down (later lines)
                        output_scroll = min(output_scroll + 1, max(0, total_wrapped_lines - max_output_lines))
                else:
                    if len(event.unicode) == 1 and 32 <= ord(event.unicode) < 127:
                        input_text += event.unicode
            elif event.type == pygame.KEYDOWN and search_focused:
                if event.key == pygame.K_ESCAPE:
                    search_focused = False
                    log_search_query = ''
                    input_active = True
                elif event.key == pygame.K_RETURN:
                    search_focused = False
                    input_active = True
                elif event.key == pygame.K_BACKSPACE:
                    log_search_query = log_search_query[:-1]
                else:
                    if len(event.unicode) == 1 and 32 <= ord(event.unicode) < 127:
                        log_search_query += event.unicode
                last_activity_time = time.time()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Any mouse button counts as activity
                last_activity_time = time.time()
                if event.button == 4:  # Scroll up
                    if total_wrapped_lines > max_output_lines:
                        # Scroll wheel up -> earlier content
                        output_scroll = max(output_scroll - 1, 0)
                elif event.button == 5:  # Scroll down
                    if total_wrapped_lines > max_output_lines:
                        # Scroll wheel down -> later content
                        output_scroll = min(output_scroll + 1, max(0, total_wrapped_lines - max_output_lines))
                elif event.button == 1:
                    mx, my = pygame.mouse.get_pos()
                    # Action buttons
                    for lbl, rect in action_button_rects:
                        if rect.collidepoint(mx, my):
                            input_text = lbl
                            pending_command = lbl
                            waiting = True
                            waiting_dots = 0
                            waiting_start_time = time.time()
                            # add to history
                            if not input_history or input_history[-1] != lbl:
                                input_history.append(lbl)
                            history_index = -1
                            if lbl == "/inventory":
                                show_inventory_panel = True
                            break
                    # Battle option buttons
                    if pending_command is None and battle_button_rects:
                        for opt_text, rect in battle_button_rects:
                            if rect.collidepoint(mx, my):
                                clean = opt_text
                                if '.' in clean:
                                    p0, p1 = clean.split('.',1)
                                    if p0.strip().isdigit():
                                        clean = p1.strip()
                                pending_command = clean.lower()
                                waiting = True
                                waiting_dots = 0
                                waiting_start_time = time.time()
                                if not input_history or input_history[-1] != opt_text:
                                    input_history.append(opt_text)
                                history_index = -1
                                break
                    # Click-to-move rooms
                    if pending_command is None and room_click_rects:
                        for rid, rrect, adjacent_dir in room_click_rects:
                            if rrect.collidepoint(mx, my) and adjacent_dir:
                                pending_command = f"[BRIEF] move {adjacent_dir}"
                                waiting = True
                                waiting_dots = 0
                                waiting_start_time = time.time()
                                if not input_history or input_history[-1] != pending_command:
                                    input_history.append(pending_command)
                                history_index = -1
                                break

        # --- Dynamic background & ambient audio per room ---
        active_room = state.rooms.get(state.player.location, {})
        desired_bg = pick_background_for_room(active_room, backgrounds)
        if desired_bg is not selected_bg:
            selected_bg = desired_bg
        # simple parallax drift
        if selected_bg:
            parallax_offset[0] = (parallax_offset[0] + parallax_speed) % selected_bg.get_width()
            screen.blit(selected_bg, (-parallax_offset[0], 0))
            if parallax_offset[0] > 0:
                screen.blit(selected_bg, (selected_bg.get_width()-parallax_offset[0], 0))
        else:
            screen.fill(BLACK)
        # Ambient loop handling
        desired_loop = pick_loop_for_room(active_room, ambient_loops)
        if desired_loop and current_loop is not desired_loop:
            if current_loop:
                try:
                    current_loop.stop()
                except Exception:
                    pass
            current_loop = desired_loop
            try:
                current_loop.set_volume(AMBIENT_VOLUME)
                current_loop.play(loops=-1)
            except Exception:
                current_loop = None

        # --- Draw dungeon grid and connections ---
        player_coords = state.rooms[state.player.location]["coords"]

        def is_adjacent(coords):
            px, py = player_coords
            x, y = coords
            return abs(x - px) + abs(y - py) == 1

        visible_rooms = [r for r in state.rooms.values() if r["visited"] or is_adjacent(r["coords"]) ]

        # Draw connections between rooms
        for room in visible_rooms:
            x, y = room["coords"]
            cx, cy = x * CELL_SIZE + CELL_SIZE // 2, y * CELL_SIZE + CELL_SIZE // 2
            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx, ny = x+dx, y+dy
                for other in visible_rooms:
                    if other["coords"] == (nx, ny):
                        ncx, ncy = nx * CELL_SIZE + CELL_SIZE // 2, ny * CELL_SIZE + CELL_SIZE // 2
                        pygame.draw.line(screen, CONNECTION, (cx,cy), (ncx,ncy), 16)
        # Draw rooms with rounded rectangles and shadow
        room_click_rects = []  # (room_id, rect, direction_from_player|None)
        hover_room_id = None
        mouse_pos = pygame.mouse.get_pos()
        for rid, room in state.rooms.items():
            if room not in visible_rooms:
                continue
        for room in visible_rooms:
            x, y = room["coords"]
            rect = pygame.Rect(x*CELL_SIZE+8, y*CELL_SIZE+8, CELL_SIZE-16, CELL_SIZE-16)
            shadow_rect = rect.move(6, 6)
            pygame.draw.rect(screen, (30,30,40), shadow_rect, border_radius=18)
            color = (
                (40, 40, 60) if not room["visited"]
                else GREEN if room["type"] == "shrine"
                else YELLOW if room["type"] == "treasure"
                else RED if room["enemies"]
                else GRAY
            )
            pygame.draw.rect(screen, color, rect, border_radius=18)
            pygame.draw.rect(screen, ROOM_BORDER, rect, 3, border_radius=18)
            # Determine direction from player for click movement (only if adjacent & visited adjacency rule)
            direction_from_player = None
            px0, py0 = player_coords
            if (abs(x - px0) + abs(y - py0) == 1):
                if x == px0 + 1: direction_from_player = "east"
                elif x == px0 - 1: direction_from_player = "west"
                elif y == py0 + 1: direction_from_player = "south"
                elif y == py0 - 1: direction_from_player = "north"
            room_id = None
            # recover room id for tooltip purposes
            for rid, rdata in state.rooms.items():
                if rdata is room:
                    room_id = rid
                    break
            if rect.collidepoint(mouse_pos):
                hover_room_id = room_id
                pygame.draw.rect(screen, (200,200,255), rect, 3, border_radius=18)
            room_click_rects.append((room_id, rect, direction_from_player))
            # Draw enemy marker if enemies present and room discovered
            if room["visited"]:
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
        for room in visible_rooms:
            if not room["visited"]:
                continue
            x, y = room["coords"]
            abbr = type_abbr.get(room["type"], room["type"][:2].upper())
            label = font.render(abbr, True, WHITE)
            screen.blit(label, (x*CELL_SIZE+20, y*CELL_SIZE+20))
        # Draw output area with border + tabs & search
        pygame.draw.rect(screen, output_color, output_area, border_radius=12)
        pygame.draw.rect(screen, ROOM_BORDER, output_area, 2, border_radius=12)
        tab_h = 28
        tab_w = 110
        scene_tab_rect = pygame.Rect(output_area.x + 8, output_area.y - tab_h + 6, tab_w, tab_h)
        combat_tab_rect = pygame.Rect(scene_tab_rect.right + 8, scene_tab_rect.y, tab_w, tab_h)
        search_rect = pygame.Rect(output_area.right - 210, scene_tab_rect.y, 202, tab_h)
        for rect, name in [(scene_tab_rect,'scene'), (combat_tab_rect,'combat')]:
            active = (active_log_tab == name)
            pygame.draw.rect(screen, (55,55,90) if active else (35,35,55), rect, border_radius=8)
            pygame.draw.rect(screen, (150,150,220) if active else (90,90,140), rect, 2, border_radius=8)
            t = output_font.render(name.title(), True, (235,235,255))
            screen.blit(t, (rect.centerx - t.get_width()//2, rect.centery - t.get_height()//2))
        # Search box
        pygame.draw.rect(screen, (45,45,65), search_rect, border_radius=8)
        pygame.draw.rect(screen, (110,110,160), search_rect, 2, border_radius=8)
        sq = log_search_query if log_search_query else ('filter...' if not search_focused else '')
        sq_color = (225,225,255) if log_search_query else (140,140,180)
        sq_surf = output_font.render(sq, True, sq_color)
        screen.blit(sq_surf, (search_rect.x + 8, search_rect.y + 4))
        # Select base lines
        if active_log_tab == 'scene':
            base_lines = scene_log
        else:
            base_lines = combat_log if combat_log else ['(no combat events yet)']
        # Collapse older scene lines for performance
        if active_log_tab == 'scene' and collapse_older and len(base_lines) > collapsed_visible_tail:
            hidden = len(base_lines) - collapsed_visible_tail
            working_lines = [f"[{hidden} earlier lines collapsed]"] + base_lines[-collapsed_visible_tail:]
        else:
            working_lines = list(base_lines)
        # Apply search filter
        if log_search_query:
            q = log_search_query.lower()
            filtered = [l for l in working_lines if q in l.lower()]
            working_lines = filtered if filtered else ['(no matches)']
        # Wrap
        available_width = output_area.width - 32
        # Use caching so only new unique lines are wrapped once per width
        wrapped = []
        for raw in working_lines:
            wrapped.extend(get_wrapped_cached(raw, available_width))
        total_wrapped_lines = len(wrapped)
        # Scroll bounds
        if len(wrapped) <= max_output_lines:
            output_scroll = 0
        else:
            output_scroll = max(0, min(output_scroll, len(wrapped) - max_output_lines))
        start = output_scroll
        end = start + max_output_lines
        top_pad = 12
        for i, line in enumerate(wrapped[start:end]):
            txt = output_font.render(line, True, output_text_color)
            screen.blit(txt, (output_area.x+16, output_area.y+top_pad + i*24))
        # Scroll bar
        if len(wrapped) > max_output_lines:
            hidden = len(wrapped) - max_output_lines
            proportion_visible = max_output_lines / len(wrapped)
            scroll_bar_height = max(32, int(proportion_visible * output_area.height))
            ratio = output_scroll / hidden if hidden>0 else 0
            scroll_bar_y = int(output_area.y + ratio * (output_area.height - scroll_bar_height))
            pygame.draw.rect(screen, (100,100,160), (output_area.right - 12, scroll_bar_y, 8, scroll_bar_height), border_radius=4)
        # --- Action Buttons Row (inside reserved gap) ---
        action_button_rects.clear()
        # Place buttons in the reserved ACTION_BAR area between output log and input box
        btn_y = output_area.bottom + 8
        btn_x = 8
        for lbl in action_labels:
            w = font.size(lbl)[0] + 24
            rect = pygame.Rect(btn_x, btn_y, w, 40)
            pygame.draw.rect(screen, (50, 70, 50), rect, border_radius=10)
            pygame.draw.rect(screen, (100, 180, 100), rect, 2, border_radius=10)
            t = output_font.render(lbl, True, (230, 255, 230))
            screen.blit(t, (rect.centerx - t.get_width()//2, rect.centery - t.get_height()//2))
            action_button_rects.append((lbl, rect))
            btn_x += w + 8

        # --- Battle Options Buttons ---
        battle_button_rects.clear()
        if battle_options:
            panel_width = min(480, output_area.width - 32)
            panel_rect = pygame.Rect(output_area.x + 16, output_area.y + output_area.height - 12 - 28 * (len(battle_options)+1), panel_width, 28 * (len(battle_options)+1))
            pygame.draw.rect(screen, (32, 32, 60), panel_rect, border_radius=12)
            pygame.draw.rect(screen, (140, 140, 220), panel_rect, 2, border_radius=12)
            title = output_font.render("Choose an action:", True, (210,210,255))
            screen.blit(title, (panel_rect.x + 12, panel_rect.y + 6))
            y_off = panel_rect.y + 6 + 24
            for opt in battle_options:
                opt_clean = opt.strip()
                btn = pygame.Rect(panel_rect.x + 12, y_off, panel_rect.width - 24, 24)
                pygame.draw.rect(screen, (60, 60, 100), btn, border_radius=6)
                pygame.draw.rect(screen, (150, 150, 230), btn, 1, border_radius=6)
                txtsurf = output_font.render(opt_clean, True, (240,240,255))
                screen.blit(txtsurf, (btn.x + 6, btn.y + 2))
                battle_button_rects.append((opt_clean, btn))
                y_off += 26

        # --- Tooltip for room hover ---
        if hover_room_id and hover_room_id in state.rooms:
            rdata = state.rooms[hover_room_id]
            if rdata.get("visited"):
                tooltip_lines = [hover_room_id, rdata["type"].replace('_',' ')]
                if rdata.get("enemies"):
                    enames = ", ".join(e['name'] for e in rdata['enemies'] if e.get('hp',0)>0)
                    if enames:
                        tooltip_lines.append(f"Enemies: {enames}")
                tw = max(font.size(l)[0] for l in tooltip_lines) + 24
                th = 8 + 24 * len(tooltip_lines)
                tx, ty = pygame.mouse.get_pos()
                tip_rect = pygame.Rect(tx + 18, ty + 18, tw, th)
                pygame.draw.rect(screen, (30,30,50), tip_rect, border_radius=10)
                pygame.draw.rect(screen, (160,160,240), tip_rect, 2, border_radius=10)
                for i,l in enumerate(tooltip_lines):
                    lsurf = output_font.render(l, True, (225,225,255))
                    screen.blit(lsurf, (tip_rect.x + 12, tip_rect.y + 6 + i*24))
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
        # Conditions (status effects)
        if getattr(state.player, 'conditions', None):
            if state.player.conditions:
                cond_label = output_font.render("Status:", True, (255,200,140))
                screen.blit(cond_label, (stats_x, stats_y))
                stats_y += 26
                icon_size = 24
                pad = 6
                x_off = stats_x
                for cond in sorted(state.player.conditions):
                    icon_rect = pygame.Rect(x_off, stats_y, icon_size, icon_size)
                    color = (140,200,60) if cond=='poisoned' else (200,120,60) if cond=='burning' else (120,160,220)
                    pygame.draw.rect(screen, color, icon_rect, border_radius=6)
                    pygame.draw.rect(screen, (20,20,30), icon_rect, 2, border_radius=6)
                    abbrev = ''.join([c for c in cond if c.isalpha()])[:3].upper()
                    its = output_font.render(abbrev, True, (10,10,20))
                    screen.blit(its, (icon_rect.centerx - its.get_width()//2, icon_rect.centery - its.get_height()//2))
                    x_off += icon_size + pad
                stats_y += icon_size + 8
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
            "Dim = Unexplored room",
            "Hidden rooms not shown",
        ]
        legend_line_height = 22  # Slightly smaller spacing for legend
        legend_y = stats_panel.bottom - 24 - legend_line_height * (len(legend_lines) - 1)
        for line in legend_lines:
            txt = output_font.render(line, True, (180, 220, 180))
            screen.blit(txt, (stats_x, legend_y))
            legend_y += legend_line_height

        # --- Inventory Panel ---
        if show_inventory_panel:
            panel_w = 420
            panel_h = 380
            inv_panel = pygame.Rect((WIDTH - panel_w)//2, (HEIGHT - panel_h)//2, panel_w, panel_h)
            pygame.draw.rect(screen, (32,32,48), inv_panel, border_radius=16)
            pygame.draw.rect(screen, (160,160,220), inv_panel, 3, border_radius=16)
            title = font.render("Inventory", True, (235,235,255))
            screen.blit(title, (inv_panel.x + 16, inv_panel.y + 12))
            close_rect = pygame.Rect(inv_panel.right - 40, inv_panel.y + 12, 28, 28)
            pygame.draw.rect(screen, (70,40,40), close_rect, border_radius=8)
            pygame.draw.rect(screen, (200,120,120), close_rect, 2, border_radius=8)
            x_txt = output_font.render("X", True, (255,200,200))
            screen.blit(x_txt, (close_rect.centerx - x_txt.get_width()//2, close_rect.centery - x_txt.get_height()//2))
            # Grid of items
            inventory_grid_rects.clear()
            cols = 5
            cell_size = 64
            grid_origin = (inv_panel.x + 20, inv_panel.y + 60)
            for idx, item in enumerate(state.player.inventory):
                gx = idx % cols
                gy = idx // cols
                cell_rect = pygame.Rect(grid_origin[0] + gx*(cell_size+10), grid_origin[1] + gy*(cell_size+10), cell_size, cell_size)
                pygame.draw.rect(screen, (50,50,70), cell_rect, border_radius=10)
                equipped = any(item == eq for eq in state.player.equipped.values())
                border_col = (120,200,120) if equipped else (120,120,180)
                pygame.draw.rect(screen, border_col, cell_rect, 2, border_radius=10)
                abbrev = item[:6]
                its = output_font.render(abbrev, True, (220,220,240))
                screen.blit(its, (cell_rect.centerx - its.get_width()//2, cell_rect.centery - its.get_height()//2))
                if cell_rect.collidepoint(pygame.mouse.get_pos()):
                    hovered_inventory_item = item
                    pygame.draw.rect(screen, (200,200,255), cell_rect, 3, border_radius=10)
                    if pygame.mouse.get_pressed()[0]:
                        selected_inventory_item = item
                inventory_grid_rects.append((item, cell_rect))
            # If clicked close
            if close_rect.collidepoint(pygame.mouse.get_pos()) and pygame.mouse.get_pressed()[0]:
                show_inventory_panel = False
                selected_inventory_item = None
            # Tooltip & actions
            if hovered_inventory_item:
                tip_lines = [hovered_inventory_item]
                cls = state.player.classify_item(hovered_inventory_item)
                tip_lines.append(f"Type: {cls}")
                if hovered_inventory_item in state.player.equipped.values():
                    tip_lines.append("(equipped)")
                bonus = state.player.compute_bonus(hovered_inventory_item)
                if bonus:
                    bonus_str = ", ".join(f"{k}+{v}" for k,v in bonus.items())
                    tip_lines.append("Bonus: " + bonus_str)
                tw = max(output_font.size(l)[0] for l in tip_lines) + 24
                th = 12 + 24 * len(tip_lines)
                mx,my = pygame.mouse.get_pos()
                tip_rect = pygame.Rect(mx + 18, my + 18, tw, th)
                pygame.draw.rect(screen, (40,40,60), tip_rect, border_radius=10)
                pygame.draw.rect(screen, (160,160,220), tip_rect, 2, border_radius=10)
                for i,l in enumerate(tip_lines):
                    lsurf = output_font.render(l, True, (225,225,255))
                    screen.blit(lsurf, (tip_rect.x + 12, tip_rect.y + 6 + i*24))
            # Equip / Use buttons
            if selected_inventory_item:
                actions = []
                cls = state.player.classify_item(selected_inventory_item)
                if cls == 'equipment':
                    # toggle equip
                    slot = state.player.detect_slot(selected_inventory_item)
                    if slot and state.player.equipped.get(slot) == selected_inventory_item:
                        actions.append(('Unequip', 'unequip'))
                    else:
                        actions.append(('Equip', 'equip'))
                if cls == 'consumable':
                    actions.append(('Use', 'use'))
                btn_x = inv_panel.x + 20
                btn_y = inv_panel.bottom - 60
                btn_rects = []
                for label, act in actions:
                    bw = 110
                    bh = 40
                    brect = pygame.Rect(btn_x, btn_y, bw, bh)
                    pygame.draw.rect(screen, (60,90,60), brect, border_radius=10)
                    pygame.draw.rect(screen, (120,180,120), brect, 2, border_radius=10)
                    ts = output_font.render(label, True, (230,255,230))
                    screen.blit(ts, (brect.centerx - ts.get_width()//2, brect.centery - ts.get_height()//2))
                    if brect.collidepoint(pygame.mouse.get_pos()) and pygame.mouse.get_pressed()[0]:
                        if act == 'equip':
                            msg = state.player.equip_item(selected_inventory_item)
                            output_lines.append(msg)
                            combat_log.append(msg)
                        elif act == 'unequip':
                            slot = state.player.detect_slot(selected_inventory_item)
                            if slot:
                                msg = state.player.unequip_slot(slot)
                                output_lines.append(msg)
                                combat_log.append(msg)
                        elif act == 'use':
                            msg = state.player.consume_item(selected_inventory_item)
                            output_lines.append(msg)
                            combat_log.append(msg)
                            if selected_inventory_item not in state.player.inventory:
                                selected_inventory_item = None
                        # Rebuild scene log
                        scene_log.append(output_lines[-1])
                        if len(scene_log) > 5000:
                            scene_log = scene_log[-5000:]
                        # simple click debounce
                        while pygame.mouse.get_pressed()[0]:
                            pygame.event.pump()
                    btn_x += bw + 12
        # --- Combat Panel (if enemies present in current room) ---
        current_room = state.rooms.get(state.player.location, {})
        living_enemies = [e for e in current_room.get("enemies", []) if e.get("hp",0) > 0]
        in_combat = bool(living_enemies)
        combat_panel_rect = None
        if in_combat:
            panel_width = stats_panel.width
            panel_height = 260
            combat_panel_rect = pygame.Rect(stats_panel.x, stats_panel.bottom - panel_height, panel_width, panel_height)
            pygame.draw.rect(screen, (24,24,50), combat_panel_rect)
            pygame.draw.rect(screen, (160,120,200), combat_panel_rect, 3)
            title = font.render("Combat", True, (250,230,255))
            screen.blit(title, (combat_panel_rect.x + 16, combat_panel_rect.y + 12))
            # Enemy cards
            card_y = combat_panel_rect.y + 56
            card_margin = 12
            card_x = combat_panel_rect.x + 12
            card_h = 72
            quick_buttons = []
            for enemy in living_enemies:
                card_w = panel_width - 24
                card_rect = pygame.Rect(card_x, card_y, card_w, card_h)
                pygame.draw.rect(screen, (40,40,80), card_rect, border_radius=10)
                pygame.draw.rect(screen, (130,130,200), card_rect, 2, border_radius=10)
                ename = enemy['name'].replace('_',' ').title()
                name_txt = output_font.render(ename, True, (230,230,255))
                screen.blit(name_txt, (card_rect.x + 12, card_rect.y + 8))
                # HP bar
                hp = max(0, enemy.get('hp',0))
                max_hp = enemy.get('max_hp', hp if hp>0 else 1)
                bar_w = card_w - 24
                bar_rect_bg = pygame.Rect(card_rect.x + 12, card_rect.y + 36, bar_w, 16)
                pygame.draw.rect(screen, (60,60,90), bar_rect_bg, border_radius=6)
                pct = hp / max_hp if max_hp else 0
                fg_w = int(bar_w * pct)
                hp_color = (200,60,60) if pct < 0.34 else (220,180,60) if pct < 0.67 else (80,200,120)
                pygame.draw.rect(screen, hp_color, (bar_rect_bg.x, bar_rect_bg.y, fg_w, bar_rect_bg.height), border_radius=6)
                hp_txt = output_font.render(f"{hp}/{max_hp}", True, (255,255,255))
                screen.blit(hp_txt, (bar_rect_bg.centerx - hp_txt.get_width()//2, bar_rect_bg.y - 20))
                card_y += card_h + card_margin
            # Quick action buttons (Attack / Flee / Ability if available)
            btns = ["attack", "flee"]
            if getattr(state.player, 'ability', None):
                btns.append(state.player.ability.lower())
            qb_y = combat_panel_rect.y + 16
            qb_x = combat_panel_rect.right - 12
            for btxt in reversed(btns):
                bw = 90
                bh = 32
                qb_x -= (bw + 8)
                brect = pygame.Rect(qb_x, qb_y, bw, bh)
                pygame.draw.rect(screen, (70,70,110), brect, border_radius=8)
                pygame.draw.rect(screen, (150,150,210), brect, 2, border_radius=8)
                t = output_font.render(btxt.title(), True, (240,240,255))
                screen.blit(t, (brect.centerx - t.get_width()//2, brect.centery - t.get_height()//2))
                quick_buttons.append((btxt, brect))
            # Handle quick button clicks
            if pygame.mouse.get_pressed()[0] and pending_command is None:
                mx, my = pygame.mouse.get_pos()
                for btxt, brect in quick_buttons:
                    if brect.collidepoint(mx, my):
                        pending_command = btxt
                        waiting = True
                        waiting_dots = 0
                        waiting_start_time = time.time()
                        break

            # Combat log (recent condensed messages)
            log_x = combat_panel_rect.x + 12
            log_y = combat_panel_rect.bottom - 12
            for log_line in reversed(combat_log[-6:]):
                surf = output_font.render(log_line, True, (210,210,240))
                log_y -= surf.get_height() + 2
                screen.blit(surf, (log_x, log_y))
            # Dice breakdown toggle hint
            hint = output_font.render("D: dice", True, (160,160,200))
            screen.blit(hint, (combat_panel_rect.right - hint.get_width() - 10, combat_panel_rect.bottom - hint.get_height() - 8))
            if show_dice_breakdown:
                box_h = 100
                box_rect = pygame.Rect(combat_panel_rect.x + 6, combat_panel_rect.bottom - box_h - 8, combat_panel_rect.width - 12, box_h)
                pygame.draw.rect(screen, (18,18,38), box_rect, border_radius=10)
                pygame.draw.rect(screen, (110,110,190), box_rect, 2, border_radius=10)
                lines = ["Dice Breakdown"]
                recent_rolls = [l for l in reversed(combat_log) if 'rolled a' in l][:3]
                if recent_rolls:
                    lines.extend(recent_rolls)
                else:
                    lines.append("(no recent rolls)")
                yb = box_rect.y + 8
                for l in lines:
                    ls = output_font.render(l, True, (220,220,255))
                    screen.blit(ls, (box_rect.x + 10, yb))
                    yb += 22

        # Draw Send button after stats panel so it's always visible
        send_btn_width, send_btn_height = 90, 44
        send_btn_rect = pygame.Rect(input_box.right - send_btn_width - 16, input_box.y + 10, send_btn_width, send_btn_height)
        # No need to check overlap, input_box now ends before stats panel
        pygame.draw.rect(screen, (60, 120, 60), send_btn_rect, border_radius=10)
        pygame.draw.rect(screen, (120, 200, 120), send_btn_rect, 2, border_radius=10)
        send_txt = font.render("Send", True, (255,255,255))
        screen.blit(send_txt, (send_btn_rect.centerx - send_txt.get_width()//2, send_btn_rect.centery - send_txt.get_height()//2))

        pygame.display.flip()
        # --- Adaptive frame cap ---
        now = time.time()
        # Consider user idle if no input events recently & not waiting for AI
        idle = (now - last_activity_time) > 3 and not waiting
        target_fps = 60 if not idle else 40
        # If a battle dialog or inventory is open, keep it smooth
        if battle_dialog or show_inventory_panel:
            target_fps = 60
        clock.tick(target_fps)

    # Handle Send button click
        if pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            # Tabs & search focus
            if 'scene_tab_rect' in locals():
                if scene_tab_rect.collidepoint(mx,my):
                    if active_log_tab != 'scene':
                        active_log_tab = 'scene'
                        output_scroll = 0
                elif combat_tab_rect.collidepoint(mx,my):
                    if active_log_tab != 'combat':
                        active_log_tab = 'combat'
                        output_scroll = 0
                if search_rect.collidepoint(mx,my):
                    search_focused = True
                    input_active = False
                else:
                    if not input_box.collidepoint(mx,my):
                        if search_focused:
                            search_focused = False
                            input_active = True
            if send_btn_rect.collidepoint(mx, my) and input_active and input_text.strip():
                raw_cmd_btn = input_text.strip()
                head_btn = raw_cmd_btn.split(' ')[0].lower()
                if head_btn in {"move","go","walk","run","flee","look"}:
                    raw_cmd_btn = f"[BRIEF] {raw_cmd_btn}"
                pending_command = raw_cmd_btn
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
                        atk_msg, roll_result_to_send = attack_enemy(state, target_enemy, screen, font)
                        combat_log.append(atk_msg)
                        for line in wrap_text(atk_msg, output_font, output_area.width-32):
                            output_lines.append(line)
                        if target_enemy["hp"] <= 0:
                            room["enemies"].remove(target_enemy)
                            state.player.give_xp(target_enemy.get("xp", 0))
                            defeat_msg = f"The {target_enemy['name'].replace('_', ' ')} is defeated!"
                            output_lines.append(defeat_msg)
                            combat_log.append(defeat_msg)
                    pending_command = "attack"
            try:
                import io
                import contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    result = handle_command(pending_command, state, "gpt-5-mini", roll_result_to_send, None)
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
            # Auto-scroll only if previously at bottom
            output_lines = output_lines[-output_history_limit:]
            # Append to scene log
            for ln in output_lines:
                scene_log.append(ln)
            if len(scene_log) > 5000:
                scene_log = scene_log[-5000:]
            if was_at_bottom:
                output_scroll = max(0, len(output_lines) - max_output_lines)
            input_text = ""  # Clear input after response
            # Only move/spawn enemies if not in battle dialog
            if not battle_options:
                state = move_non_boss_enemies(state, GRID_W, GRID_H)
                while count_non_boss_enemies(state) < 2:
                    state = spawn_enemy(state, enemy_sprites)
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
                action = game_over_dialog(screen, font, output_font, WIDTH, HEIGHT)
                if action == "play_again":
                    seed = random.randint(1, 999999)
                    rooms = generate_grid_dungeon(seed, GRID_W, GRID_H)
                    for room in rooms.values():
                        for enemy in room["enemies"]:
                            sprite_keys = [k for k in enemy_sprites if enemy["name"] in k]
                            enemy["sprite"] = random.choice(sprite_keys) if sprite_keys else None
                    player = Player(location="room_0")
                    state = GameState(seed=seed, rooms=rooms, player=player)
                    if isinstance(state.player, dict):
                        state.player = Player(**state.player)
                    selected_hero = select_hero(screen, hero_sprites, font, output_font, WIDTH, HEIGHT)
                    player_icon = hero_sprites[selected_hero]
                else:
                    running = False
                    # mark for exit after frame

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
                        atk_msg, roll_result_to_send = attack_enemy(state, target_enemy, screen, font)
                        combat_log.append(atk_msg)
                        for line in wrap_text(atk_msg, output_font, output_area.width-32):
                            output_lines.append(line)
                        if target_enemy["hp"] <= 0:
                            room["enemies"].remove(target_enemy)
                            state.player.give_xp(target_enemy.get("xp", 0))
                            defeat_msg = f"The {target_enemy['name'].replace('_', ' ')} is defeated!"
                            output_lines.append(defeat_msg)
                            combat_log.append(defeat_msg)
                    pending_command = "attack"
            try:
                import io
                import contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    result = handle_command(pending_command, state, "gpt-5-mini", roll_result_to_send, None)
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
            for ln in output_lines:
                scene_log.append(ln)
            if len(scene_log) > 5000:
                scene_log = scene_log[-5000:]
            if was_at_bottom:
                output_scroll = max(0, len(output_lines) - max_output_lines)
            input_text = ""
            if not battle_options:
                state = move_non_boss_enemies(state, GRID_W, GRID_H)
                while count_non_boss_enemies(state) < 2:
                    state = spawn_enemy(state, enemy_sprites)
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
                action = game_over_dialog(screen, font, output_font, WIDTH, HEIGHT)
                if action == "play_again":
                    seed = random.randint(1, 999999)
                    rooms = generate_grid_dungeon(seed, GRID_W, GRID_H)
                    for room in rooms.values():
                        for enemy in room["enemies"]:
                            sprite_keys = [k for k in enemy_sprites if enemy["name"] in k]
                            enemy["sprite"] = random.choice(sprite_keys) if sprite_keys else None
                    player = Player(location="room_0")
                    state = GameState(seed=seed, rooms=rooms, player=player)
                    if isinstance(state.player, dict):
                        state.player = Player(**state.player)
                    selected_hero = select_hero(screen, hero_sprites, font, output_font, WIDTH, HEIGHT)
                    player_icon = hero_sprites[selected_hero]
                else:
                    running = False
                    # will exit outer loop

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    run()
