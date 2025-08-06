"""Tests for dungeon generation."""

import os
import sys

import pytest

# Ensure project root is on sys.path for direct imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.dungeon import generate_dungeon


def test_boss_room_contains_single_dungeon_boss():
    seed = 4
    dungeon = generate_dungeon(seed)
    boss_rooms = [room for room in dungeon.values() if room["type"] == "boss_room"]
    assert len(boss_rooms) == 1
    boss_room = boss_rooms[0]
    assert len(boss_room["enemies"]) == 1
    assert boss_room["enemies"][0]["name"] == "dungeon_boss"
