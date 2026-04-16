from unittest.mock import patch
from src.main import parse_args


def test_parse_args_default():
    args = parse_args([])
    assert args.command == "run"


def test_parse_args_fetch():
    args = parse_args(["fetch"])
    assert args.command == "fetch"


def test_parse_args_tui():
    args = parse_args(["tui"])
    assert args.command == "tui"


def test_parse_args_config():
    args = parse_args(["--config", "custom.yaml", "fetch"])
    assert args.config == "custom.yaml"
    assert args.command == "fetch"
