import copy
import random
from collections import deque
import pygame

from roguelike_ai import ENEMIES


def move_non_boss_enemies(state, grid_w, grid_h):
    new_rooms = copy.deepcopy(state.rooms)
    coord_to_room = {room['coords']: rid for rid, room in state.rooms.items()}
    boss_coords = {room['coords'] for room in state.rooms.values() if room['type'] == 'boss_room'}
    occupied = {
        room['coords']
        for room in state.rooms.values()
        for e in room['enemies']
        if e['name'] != 'dungeon_boss'
    }
    player_coord = state.rooms[state.player.location]['coords']
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    def bfs(start, goal, blocked):
        if start == goal:
            return []
        queue = deque([start])
        came_from = {start: None}
        while queue:
            current = queue.popleft()
            if current == goal:
                break
            for dx, dy in directions:
                nx, ny = current[0] + dx, current[1] + dy
                if 0 <= nx < grid_w and 0 <= ny < grid_h:
                    nxt = (nx, ny)
                    if nxt not in came_from and nxt not in blocked:
                        queue.append(nxt)
                        came_from[nxt] = current
        if goal not in came_from:
            return None
        path = []
        cur = goal
        while cur != start:
            path.append(cur)
            cur = came_from[cur]
        path.reverse()
        return path

    for room_id, room in state.rooms.items():
        for enemy in room['enemies'][:]:
            if enemy['name'] == 'dungeon_boss':
                continue
            start = room['coords']
            occupied.discard(start)
            blocked = occupied | boss_coords
            path = bfs(start, player_coord, blocked)
            if path:
                next_step = path[0]
                dest_id = coord_to_room[next_step]
                if not new_rooms[dest_id]['enemies']:
                    new_rooms[room_id]['enemies'].remove(enemy)
                    new_rooms[dest_id]['enemies'].append(enemy)
                    occupied.add(next_step)
                else:
                    occupied.add(start)
            else:
                occupied.add(start)
    state.rooms = new_rooms
    return state


def count_non_boss_enemies(state):
    count = 0
    for room in state.rooms.values():
        for enemy in room['enemies']:
            if enemy['name'] != 'dungeon_boss':
                count += 1
    return count


def spawn_enemy(state, enemy_sprites):
    possible_rooms = [rid for rid, room in state.rooms.items()
                     if room['type'] != 'boss_room' and rid != state.player.location]
    if not possible_rooms:
        return state
    room_id = random.choice(possible_rooms)
    name = random.choice([k for k in ENEMIES if k != 'dungeon_boss'])
    enemy = {**ENEMIES[name], 'name': name}
    sprite_keys = [k for k in enemy_sprites if name in k]
    enemy['sprite'] = random.choice(sprite_keys) if sprite_keys else None
    new_rooms = copy.deepcopy(state.rooms)
    new_rooms[room_id]['enemies'].append(enemy)
    state.rooms = new_rooms
    return state


def roll_d20():
    return random.randint(1, 20)


def animate_d20_roll(screen, font, roll_result):
    roll_rect = pygame.Rect(screen.get_width() // 2 - 50, screen.get_height() // 2 - 50, 100, 100)
    pygame.draw.rect(screen, (30, 30, 60), roll_rect, border_radius=12)
    pygame.draw.rect(screen, (200, 200, 255), roll_rect, 4, border_radius=12)
    roll_text = font.render(f"D20: {roll_result}", True, (255, 255, 255))
    screen.blit(roll_text, (roll_rect.centerx - roll_text.get_width() // 2, roll_rect.centery - roll_text.get_height() // 2))
    pygame.display.flip()
    pygame.time.delay(1000)


def attack_enemy(state, enemy, screen, font):
    roll_result = roll_d20()
    animate_d20_roll(screen, font, roll_result)
    damage = roll_result + state.player.str
    enemy["hp"] -= damage
    msg = f"You rolled a {roll_result} and dealt {damage} damage to {enemy['name']}!"
    return msg, roll_result
