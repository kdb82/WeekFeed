"""Run the app: `uv run weekfeed` (or `uv run python -m weekfeed`) from backend/."""
import uvicorn

from .api.app import create_app
from .config import load_config


def main() -> None:
    config = load_config()
    print(f"WeekFeed running at http://127.0.0.1:{config.port}")
    uvicorn.run(create_app(config), host="127.0.0.1", port=config.port)


if __name__ == "__main__":
    main()
