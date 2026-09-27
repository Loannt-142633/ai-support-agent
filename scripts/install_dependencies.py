"""Install dependency groups from pyproject.toml before copying application code."""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


def requirements_for(group: str) -> list[str]:
    with Path("pyproject.toml").open("rb") as source:
        metadata = tomllib.load(source)

    if group == "base":
        return [
            *metadata["build-system"]["requires"],
            *metadata["project"]["dependencies"],
        ]
    if group == "embeddings":
        return list(metadata["project"]["optional-dependencies"]["embeddings"])
    raise ValueError(f"Unknown dependency group: {group}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=("base", "embeddings"))
    args = parser.parse_args()
    subprocess.run(
        [sys.executable, "-m", "pip", "install", *requirements_for(args.group)],
        check=True,
    )


if __name__ == "__main__":
    main()
