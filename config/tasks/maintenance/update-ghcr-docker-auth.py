#!/usr/bin/env python
# [MISE] description="Update the ghcr.io token in docker auth config"

"""Accepts a token on stdin, and updates the correct auth entry in docker config"""

import base64
import getpass
import json
import os
import sys
from pathlib import Path


def main():
    token = getpass.getpass("Enter the Github PAT here: ").strip()
    if not token:
        print("Error: no token provided on stdin", file=sys.stderr)
        sys.exit(1)

    docker_config_dir = os.environ.get("DOCKER_CONFIG", os.path.expanduser("~/.docker"))
    config_file = Path(docker_config_dir) / "config.json"

    config = {}
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
        except json.JSONDecodeError:
            print(f"Error: {config_file} contains invalid JSON", file=sys.stderr)
            sys.exit(1)

    if not isinstance(config, dict):
        print(f"Error: {config_file} does not contain a JSON object", file=sys.stderr)
        sys.exit(1)

    username = getpass.getuser()
    auth_value = base64.b64encode(f"{username}:{token}".encode()).decode()

    config.setdefault("auths", {})["ghcr.io"] = {"auth": auth_value}

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(config, indent=4) + "\n")


if __name__ == "__main__":
    main()
