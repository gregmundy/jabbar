import argparse
import sys
import os


def parse_args(argv: list[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jabbar",
        description="Jabbar — Email Financial Intelligence",
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--data-dir", default="data",
        help="Path to data directory (default: data)",
    )
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["setup", "fetch", "extract", "analyze", "run", "tui"],
        help="Command to run (default: run)",
    )
    return parser.parse_args(argv)


def cmd_fetch(config: dict, data_dir: str) -> list[dict]:
    from src.auth.imap_auth import connect_imap
    from src.auth.oauth2_auth import get_oauth2_connection
    from src.fetch.email_fetcher import (
        search_financial_emails,
        fetch_and_cache,
        calculate_since_date,
    )

    since = calculate_since_date(config["scan"]["months_back"])
    keywords = config["scan"]["keywords"]
    all_emails = []

    for account in config["accounts"]:
        name = account["name"]
        print(f"\nConnecting to {name} ({account['email']})...")

        try:
            if account["auth"] == "app_password":
                conn = connect_imap(
                    account["imap_host"], account["imap_port"],
                    account["email"], account["password"],
                )
            elif account["auth"] == "oauth2":
                conn = get_oauth2_connection(account)
            else:
                print(f"  Unknown auth type: {account['auth']}")
                continue

            mailbox = account.get("mailbox", "INBOX")
            conn.select(mailbox, readonly=True)

            print(f"  Searching for financial emails since {since}...")
            msg_ids = search_financial_emails(conn, keywords, since)
            print(f"  Found {len(msg_ids)} financial emails")

            emails = fetch_and_cache(conn, msg_ids, name, data_dir)
            all_emails.extend(emails)

            conn.logout()
            print(f"  Done with {name}: {len(emails)} emails cached")

        except Exception as e:
            print(f"  Error with {name}: {e}")
            continue

    print(f"\nTotal: {len(all_emails)} emails across {len(config['accounts'])} accounts")
    return all_emails


def cmd_extract(config: dict, data_dir: str, emails: list[dict] = None) -> list[dict]:
    from src.extract.llm_extractor import extract_all
    import os
    import json

    if emails is None:
        emails = []
        raw_dir = os.path.join(data_dir, "raw")
        if os.path.exists(raw_dir):
            for provider in os.listdir(raw_dir):
                provider_dir = os.path.join(raw_dir, provider)
                if os.path.isdir(provider_dir):
                    for fname in os.listdir(provider_dir):
                        if fname.endswith(".eml"):
                            msg_id = fname[:-4]
                            emails.append({
                                "msg_id": msg_id,
                                "provider": provider,
                                "path": os.path.join(provider_dir, fname),
                            })

    if not emails:
        print("No emails to extract. Run 'jabbar fetch' first.")
        return []

    endpoint = config["extraction"]["llm_endpoint"]
    print(f"\nChecking LLM at {endpoint}...")
    try:
        import urllib.request
        req = urllib.request.Request(f"{endpoint.rsplit('/', 1)[0]}/models")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        print(f"Error: Local LLM not available at {endpoint}.")
        print("Start LM Studio and load Qwen2.5-7B-Instruct.")
        sys.exit(1)

    print(f"Extracting transactions from {len(emails)} emails...")
    return extract_all(emails, config, data_dir)


def cmd_analyze(config: dict, data_dir: str, transactions: list[dict] = None) -> dict:
    from src.analyze.claude_analyzer import analyze_transactions
    import json
    import os

    if transactions is None:
        tx_path = os.path.join(data_dir, "extracted", "transactions.json")
        if not os.path.exists(tx_path):
            print("No transactions found. Run 'jabbar extract' first.")
            return {}
        with open(tx_path) as f:
            transactions = json.load(f)

    return analyze_transactions(transactions, config, data_dir)


def cmd_tui(data_dir: str) -> None:
    from src.tui.app import JabbarApp
    app = JabbarApp(data_dir=data_dir)
    app.title = "Jabbar"
    app.sub_title = "Email Financial Intelligence"
    app.run()


def main(argv: list[str] = None) -> None:
    args = parse_args(argv)

    if args.command == "tui":
        cmd_tui(args.data_dir)
        return

    from src.config import load_config, ConfigError
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    if args.command == "fetch":
        cmd_fetch(config, args.data_dir)
    elif args.command == "extract":
        cmd_extract(config, args.data_dir)
    elif args.command == "analyze":
        cmd_analyze(config, args.data_dir)
    elif args.command == "run":
        emails = cmd_fetch(config, args.data_dir)
        transactions = cmd_extract(config, args.data_dir, emails)
        try:
            cmd_analyze(config, args.data_dir, transactions)
        except Exception as e:
            print(f"Analysis skipped: {e}")
        cmd_tui(args.data_dir)


if __name__ == "__main__":
    main()
