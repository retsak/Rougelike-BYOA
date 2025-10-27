from web.story_engine import StoryEngine


def test_story_creation_is_deterministic_with_seed():
    engine = StoryEngine(seed=42)
    state_a = engine.create_story("abc", "lyra", "ranger", "fearless")
    engine.reset("abc")
    engine = StoryEngine(seed=42)
    state_b = engine.create_story("abc", "lyra", "ranger", "fearless")
    assert state_a.as_dict() == state_b.as_dict()


def test_story_advances_and_tracks_history():
    engine = StoryEngine(seed=1)
    state = engine.create_story("session", "kai", "artificer", "curious")
    assert len(state.history) == 1
    updated = engine.advance("session", "investigate the signal")
    assert len(updated.history) == 2
    assert updated.progress == 1
    assert "investigate the signal" in updated.history[-1]
