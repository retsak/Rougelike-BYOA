"""Game object holding state, configuration and common helpers."""
from dataclasses import dataclass
from typing import Any, Dict
from collections import deque
import copy
import random

from roguelike_ai import GameState, ENEMIES
from . import config


@dataclass
class Game:
    """Container for game state and configuration.

    The UI layer interacts with a :class:`Game` instance rather than using
    global variables.  Helper methods that operate on the game state live
    here so they can be reused by different front ends.
    """

    state: GameState
    cfg: Any = config
    enemy_sprites: Dict[str, Any] | None = None

    def move_non_boss_enemies(self) -> None:
        """Move all non-boss enemies one step toward the player."""
        grid_w, grid_h = self.cfg.GRID_W, self.cfg.GRID_H
        state = self.state
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
                    continue  # Boss does not move
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
        self.state.rooms = new_rooms

    def count_non_boss_enemies(self) -> int:
        """Return the number of enemies excluding the dungeon boss."""
        count = 0
        for room in self.state.rooms.values():
            for enemy in room['enemies']:
                if enemy['name'] != 'dungeon_boss':
                    count += 1
        return count

    def spawn_enemy(self) -> None:
        """Spawn a new non-boss enemy in a random room."""
        state = self.state
        possible_rooms = [
            rid for rid, room in state.rooms.items()
            if room['type'] != 'boss_room' and rid != state.player.location
        ]
        if not possible_rooms:
            return
        room_id = random.choice(possible_rooms)
        name = random.choice([k for k in ENEMIES if k != 'dungeon_boss'])
        enemy = {**ENEMIES[name], 'name': name}
        sprite_keys = [k for k in (self.enemy_sprites or {}) if name in k]
        if sprite_keys:
            enemy['sprite'] = random.choice(sprite_keys)
        else:
            enemy['sprite'] = None
        new_rooms = copy.deepcopy(state.rooms)
        new_rooms[room_id]['enemies'].append(enemy)
        state.rooms = new_rooms

    def attack_enemy(self, enemy: dict, roll_result: int) -> str:
        """Apply attack damage to *enemy* given a D20 roll result."""
        damage = roll_result + self.state.player.str
        enemy['hp'] -= damage
        msg = f"You rolled a {roll_result} and dealt {damage} damage to {enemy['name']}!"
        return msg
