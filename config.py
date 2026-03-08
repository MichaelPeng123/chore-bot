"""
config.py — Load and validate config.json.
Exits the process with a clear message if the file is missing or malformed.
"""

import json
import os
import sys

CONFIG_PATH = "config.json"

REQUIRED_KEYS = ["roommates", "chores", "cycle_days", "remind_before_days", "timezone"]


def load_config() -> dict:
    """Read config.json and return the parsed dict. Exit on any error."""
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        sys.exit(f"[config] ERROR: {CONFIG_PATH} not found. Please create it before running the bot.")
    except json.JSONDecodeError as e:
        sys.exit(f"[config] ERROR: {CONFIG_PATH} is not valid JSON: {e}")

    # Validate required top-level keys are present
    for key in REQUIRED_KEYS:
        if key not in config:
            sys.exit(f"[config] ERROR: Missing required key '{key}' in {CONFIG_PATH}.")

    # Validate roommates is a non-empty list with the expected fields
    if not isinstance(config["roommates"], list) or len(config["roommates"]) == 0:
        sys.exit("[config] ERROR: 'roommates' must be a non-empty list.")
    for r in config["roommates"]:
        if "name" not in r or "discord_user_id" not in r:
            sys.exit("[config] ERROR: Each roommate must have 'name' and 'discord_user_id'.")
        # If the value looks like an env var name (no digits, all uppercase), resolve it
        uid = r["discord_user_id"]
        if not uid.isdigit():
            resolved = os.getenv(uid)
            if not resolved:
                sys.exit(f"[config] ERROR: Environment variable '{uid}' for roommate '{r['name']}' is not set.")
            r["discord_user_id"] = resolved

    # Validate chores is a non-empty list of strings
    if not isinstance(config["chores"], list) or len(config["chores"]) == 0:
        sys.exit("[config] ERROR: 'chores' must be a non-empty list.")

    return config
