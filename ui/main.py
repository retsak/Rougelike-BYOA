"""Application entry point."""

from . import game_loop


def main() -> None:
    """Run the game loop."""
    game_loop.run()


if __name__ == "__main__":
    main()
