"""Story generation engine for the web-based DungeonGPT experience."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class StoryState:
    """Lightweight container tracking the evolving story."""

    hero_name: str
    archetype: str
    trait: str
    companion: str
    setting: str
    goal: str
    complication: str
    progress: int = 0
    history: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, str | int | List[str]]:
        return {
            "hero": self.hero_name,
            "archetype": self.archetype,
            "trait": self.trait,
            "companion": self.companion,
            "setting": self.setting,
            "goal": self.goal,
            "complication": self.complication,
            "progress": self.progress,
            "history": list(self.history),
        }


class StoryEngine:
    """Tiny narrative generator used by the web UI.

    The goal is not to replace the full roguelike systems but to provide a
    playful, deterministic “AI" companion that reacts to player prompts.
    """

    _COMPANIONS = [
        "a clockwork fox", "an excitable sprite", "a reformed goblin",
        "a wandering bard", "an ancient automaton", "a spectral guide",
    ]
    _SETTINGS = [
        "the twilight bazaar of Luminara",
        "the floating archives of Aerolith",
        "the subterranean bloom caverns",
        "a city balanced on colossal tree roots",
        "a mirror desert where dunes reflect the sky",
    ]
    _GOALS = [
        "recover the lost heartstone",
        "broker peace between rival clans",
        "discover the origin of the midnight sun",
        "rescue the lighthouse of whispers",
        "seal the breach spilling dreams into reality",
    ]
    _COMPLICATIONS = [
        "time fractures that rewind missteps",
        "echo beasts that feed on spoken lies",
        "a rival guild tracing your every move",
        "storms of living ink that rewrite memory",
        "a chorus of futures arguing in your head",
    ]
    _TURN_BEATS = [
        "You and {companion} navigate {setting_part}.",
        "A whisper of {complication_part} brushes past, urging caution.",
        "Together you improvise a plan to {goal} before the chance fades.",
    ]

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)
        self._sessions: Dict[str, StoryState] = {}

    def _choice(self, options: List[str]) -> str:
        return self._random.choice(options)

    def create_story(
        self,
        session_id: str,
        hero_name: str,
        archetype: str,
        trait: str,
    ) -> StoryState:
        companion = self._choice(self._COMPANIONS)
        setting = self._choice(self._SETTINGS)
        goal = self._choice(self._GOALS)
        complication = self._choice(self._COMPLICATIONS)
        state = StoryState(
            hero_name=hero_name.title().strip() or "Nameless",
            archetype=archetype.strip() or "Drifter",
            trait=trait.strip() or "resourceful",
            companion=companion,
            setting=setting,
            goal=goal,
            complication=complication,
        )
        intro = self._build_intro(state)
        state.history.append(intro)
        self._sessions[session_id] = state
        return state

    def _build_intro(self, state: StoryState) -> str:
        return (
            f"{state.hero_name}, a {state.trait} {state.archetype}, arrives in {state.setting}. "
            f"They are joined by {state.companion} and sworn to {state.goal}."
            f" Yet rumours of {state.complication} lurk at every turn."
        )

    def advance(self, session_id: str, action: str) -> StoryState:
        state = self._sessions.get(session_id)
        if not state:
            raise KeyError(f"Unknown session: {session_id}")
        beat = self._generate_beat(state, action)
        state.history.append(beat)
        state.progress += 1
        return state

    def _generate_beat(self, state: StoryState, action: str) -> str:
        action_clean = action.strip()
        if not action_clean:
            action_clean = "listen to the city's pulse"
        template = self._choice(self._TURN_BEATS)
        setting_part = self._random.choice([
            f"the layered markets of {state.setting}",
            f"a hidden alley within {state.setting}",
            f"the shimmering bridges of {state.setting}",
        ])
        complication_part = self._random.choice([
            state.complication,
            f"shards of {state.complication}",
            f"rumours about {state.complication}",
        ])
        beat = template.format(
            companion=state.companion,
            setting_part=setting_part,
            complication_part=complication_part,
            goal=state.goal,
        )
        resolution = self._random.choice([
            f"Inspired, you {action_clean}, shifting the story's rhythm.",
            f"{state.companion.capitalize()} echoes your choice to {action_clean}, and the city responds.",
            f"Every step to {action_clean} drags {state.goal} closer—yet {state.complication} feels nearer too.",
        ])
        return f"{beat} {resolution}"

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get_state(self, session_id: str) -> StoryState | None:
        return self._sessions.get(session_id)


# A module-level engine for convenience in the FastAPI app.
def get_engine() -> StoryEngine:
    global _ENGINE
    try:
        engine = _ENGINE
    except NameError:
        engine = StoryEngine()
        _ENGINE = engine
    return engine
