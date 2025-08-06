from __future__ import annotations

"""Dataclasses representing player state and overall game state."""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List


@dataclass
class Player:
    hp: int = 20
    str: int = 4
    dex: int = 3
    ability: str | None = None
    level: int = 1
    xp: int = 0
    inventory: List[str] = field(default_factory=list)
    location: str = "room_0"
    torch_lit: bool = False

    def is_alive(self) -> bool:
        return self.hp > 0

    def give_xp(self, amount: int) -> None:
        self.xp += amount
        while self.xp >= self.level * 100:
            self.xp -= self.level * 100
            self.level += 1
            self.hp += 5
            self.str += 1
            self.dex += 1
            print(f"*** You reach level {self.level}! Stats increased. ***")


@dataclass
class GameState:
    seed: int
    rooms: Dict[str, dict]
    player: Player
    turn: int = 0
    history: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @staticmethod
    def from_json(txt: str) -> "GameState":
        d = json.loads(txt)
        return GameState(
            seed=d["seed"],
            rooms=d["rooms"],
            player=Player(**d["player"]),
            turn=d["turn"],
            history=d.get("history", []),
        )
