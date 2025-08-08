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
    # Equipment management
    equipped: dict = field(default_factory=dict)  # slot -> item name
    equipped_bonuses: dict = field(default_factory=dict)  # slot -> {stat: delta}
    # Use list for JSON friendliness (was set). Ensure uniqueness manually if needed.
    conditions: list = field(default_factory=list)  # e.g., ['poisoned','burning']

    def is_alive(self) -> bool:
        return self.hp > 0

    def give_xp(self, amount: int) -> None:
        """Add XP and handle level ups. Returns list of event messages."""
        messages: list[str] = []
        self.xp += amount
        messages.append(f"You gain {amount} XP.")
        # Level threshold: level * 100 (can be tuned later to exponential)
        leveled = False
        while self.xp >= self.level * 100:
            self.xp -= self.level * 100
            self.level += 1
            leveled = True
            # Stat gains on level up
            self.hp += 5
            self.str += 1
            self.dex += 1
            messages.append(f"*** You reach level {self.level}! (+5 HP, +1 STR, +1 DEX) ***")
        if not leveled:
            needed = self.level * 100 - self.xp
            messages.append(f"{needed} XP to level {self.level + 1}.")
        for m in messages:
            try:
                print(m)
            except Exception:
                pass
        return messages

    def xp_to_next(self) -> int:
        return self.level * 100 - self.xp

    # ---- Equipment & Items ----
    @staticmethod
    def classify_item(item: str) -> str:
        it = item.lower()
        if 'potion' in it:
            return 'consumable'
        if any(k in it for k in ['boots','sword','axe','dagger','shield','torch']):
            return 'equipment'
        return 'misc'

    @staticmethod
    def detect_slot(item: str) -> str | None:
        it = item.lower()
        if 'boots' in it:
            return 'boots'
        if any(k in it for k in ['sword','axe','dagger']):
            return 'weapon'
        if 'shield' in it:
            return 'offhand'
        if 'torch' in it:
            return 'utility'
        return None

    @staticmethod
    def compute_bonus(item: str) -> dict:
        it = item.lower()
        bonus = {}
        if 'boots' in it:
            bonus['dex'] = 1
        if any(k in it for k in ['sword','axe','dagger']):
            bonus['str'] = 2
        if 'shield' in it:
            bonus['hp'] = 5
        # torch gives no direct stat bonus; handled via torch_lit flag
        return bonus

    def equip_item(self, item: str) -> str:
        if item not in self.inventory:
            return f"You don't have {item}."
        if self.classify_item(item) != 'equipment':
            return f"{item.title()} cannot be equipped."
        slot = self.detect_slot(item)
        if not slot:
            return f"{item.title()} cannot be equipped."
        # Unequip existing
        prev_item = self.equipped.get(slot)
        if prev_item:
            prev_bonus = self.equipped_bonuses.get(slot, {})
            for stat, delta in prev_bonus.items():
                setattr(self, stat, getattr(self, stat) - delta)
        # Torch special case
        if 'torch' in item.lower():
            self.torch_lit = True
        bonus = self.compute_bonus(item)
        for stat, delta in bonus.items():
            setattr(self, stat, getattr(self, stat) + delta)
        self.equipped[slot] = item
        self.equipped_bonuses[slot] = bonus
        if prev_item and prev_item != item:
            return f"You swap your {prev_item} for {item}."
        return f"You equip {item}."

    def unequip_slot(self, slot: str) -> str:
        if slot not in self.equipped:
            return "Nothing equipped there."
        item = self.equipped.pop(slot)
        bonus = self.equipped_bonuses.pop(slot, {})
        for stat, delta in bonus.items():
            setattr(self, stat, getattr(self, stat) - delta)
        if 'torch' in item.lower():
            self.torch_lit = False
        return f"You unequip {item}."

    def consume_item(self, item: str) -> str:
        if item not in self.inventory:
            return f"You don't have {item}."
        if self.classify_item(item) != 'consumable':
            return f"{item.title()} is not consumable."
        # Health potion effect
        if 'potion' in item.lower():
            self.hp += 10
            # Remove single instance
            self.inventory.remove(item)
            return f"You drink the {item} and recover 10 HP."
        return f"You use the {item}."


@dataclass
class GameState:
    seed: int
    rooms: Dict[str, dict]
    player: Player
    turn: int = 0
    history: list = field(default_factory=list)
    # Per-ability remaining cooldown turns (0 or missing means ready)
    ability_cooldowns: dict = field(default_factory=dict)

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
            ability_cooldowns=d.get("ability_cooldowns", {}),
        )
