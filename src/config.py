import os
import yaml


class ConfigError(Exception):
    pass


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}. Copy config.example.yaml to config.yaml and fill in your credentials.")

    with open(path) as f:
        config = yaml.safe_load(f)

    if not config or "accounts" not in config or not config["accounts"]:
        raise ConfigError("Config must contain at least one account under 'accounts'.")

    for account in config["accounts"]:
        if "auth" not in account:
            raise ConfigError(f"Account '{account.get('name', '?')}' missing 'auth' field. Must be 'app_password' or 'oauth2'.")
        if account["auth"] == "app_password" and "password" not in account:
            raise ConfigError(f"Account '{account.get('name', '?')}' uses app_password auth but missing 'password' field.")
        if account["auth"] == "oauth2" and "client_id" not in account:
            raise ConfigError(f"Account '{account.get('name', '?')}' uses oauth2 auth but missing 'client_id' field.")

    required_sections = ["scan", "extraction", "analysis"]
    for section in required_sections:
        if section not in config:
            raise ConfigError(f"Config missing required section: '{section}'.")

    return config
