import argparse
import os
import secrets
from pathlib import Path

from requests.exceptions import ConnectionError
from rich.console import Console
from rich.table import Table
from rich.text import Text
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bridger.emqx import EMQXClient
from bridger.gateway import GatewayError, GatewayManagerEMQX

console = Console()

EMQX_API_KEY = os.getenv("EMQX_API_KEY")
EMQX_SECRET_KEY = os.getenv("EMQX_SECRET_KEY")
EMQX_URL = os.getenv("EMQX_URL")

emqx = EMQXClient(EMQX_URL, EMQX_API_KEY, EMQX_SECRET_KEY)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type((ConnectionError, OSError)),
    reraise=True,
)
def create_user_command(args):
    class SimpleUser:
        def __init__(self, user_id: int):
            self.id = user_id

    user = SimpleUser(int(args.user_id))
    manager = GatewayManagerEMQX(emqx)

    try:
        gateway, password = manager.create_gateway_user(args.gateway_id, user)
        console.print("Gateway user created successfully!", style="bold green")

        table = Table(title="Gateway Credentials")
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="magenta")

        table.add_row("Username", gateway.user_string)
        table.add_row("Password", password)

        console.print(table)
    except GatewayError as e:
        console.print(f"Error creating gateway user: {e}", style="bold red")


def delete_user_command(args):
    manager = GatewayManagerEMQX(emqx)

    try:
        success = manager.delete_gateway_user(args.gateway_id)
        if success:
            console.print("Gateway user deleted successfully!", style="bold green")
        else:
            console.print("Failed to delete gateway user", style="bold red")
            exit(1)
    except Exception as e:
        console.print(f"Error deleting gateway user: {e}", style="bold red")
        exit(1)


def list_users_command(args):
    manager = GatewayManagerEMQX(emqx)

    try:
        gateways = list(manager.list_gateways())
        if not gateways:
            console.print("No gateway users found", style="yellow")
        else:
            table = Table(title="Gateway Users")
            table.add_column("Username", style="cyan", no_wrap=True)
            table.add_column("Node ID", style="magenta")

            for gateway in gateways:
                table.add_row(gateway.user_string, f"!{gateway.node_hex_id_without_bang}")

            console.print(table)
    except Exception as e:
        console.print(f"Error listing gateway users: {e}", style="bold red")
        exit(1)


def generate_apikey_command(args):
    bootstrap_file = Path(args.bootstrap_file) if args.bootstrap_file else Path("/opt/emqx/etc/api_key.bootstrap")
    env_file = Path(".env")

    # Check if bootstrap file exists and not forcing
    if bootstrap_file.exists() and not args.force:
        console.print(f"Bootstrap file already exists at {bootstrap_file}. Use -f to force overwrite.", style="bold red")
        return

    # Check if keys already exist in .env file
    emqx_api_key_exists = False
    emqx_secret_key_exists = False
    influxdb_token_exists = False

    if env_file.exists() and not args.force:
        with open(env_file, "r") as f:
            content = f.read()
            if "EMQX_API_KEY=" in content:
                emqx_api_key_exists = True
            if "EMQX_SECRET_KEY=" in content:
                emqx_secret_key_exists = True
            if "INFLUXDB_V2_TOKEN=" in content:
                influxdb_token_exists = True

    if (emqx_api_key_exists or emqx_secret_key_exists or influxdb_token_exists) and not args.force:
        console.print("Some keys already exist in .env file:", style="bold red")
        if emqx_api_key_exists:
            console.print("  - EMQX_API_KEY", style="red")
        if emqx_secret_key_exists:
            console.print("  - EMQX_SECRET_KEY", style="red")
        if influxdb_token_exists:
            console.print("  - INFLUXDB_V2_TOKEN", style="red")
        console.print("Use -f to force overwrite.", style="bold red")
        return

    # Generate keys
    api_key = f"bridger-{secrets.token_hex(8)}"
    secret_key = secrets.token_hex(32)
    influxdb_token = secrets.token_urlsafe(48)

    # Create bootstrap file
    bootstrap_file.parent.mkdir(parents=True, exist_ok=True)
    with open(bootstrap_file, "w") as f:
        f.write(f"{api_key}:{secret_key}:administrator\n")

    console.print("Generated API and secret keys!", style="bold green")

    table = Table(title="Generated Keys")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("API Key", api_key)
    table.add_row("Secret Key", secret_key)
    table.add_row("InfluxDB Token", influxdb_token)

    console.print(table)

    console.print("\n[bold cyan]Add these to your .env file:[/bold cyan]")
    env_vars = Text()
    env_vars.append(f'EMQX_API_KEY="{api_key}"\n', style="green")
    env_vars.append(f'EMQX_SECRET_KEY="{secret_key}"\n', style="green")
    env_vars.append(f'INFLUXDB_V2_TOKEN="{influxdb_token}"', style="green")
    console.print(env_vars)

    console.print(f"\nBootstrap file created at: [bold]{bootstrap_file}[/bold]", style="green")


def main():
    parser = argparse.ArgumentParser(description="Bridger CLI - MQTT gateway management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create user command
    create_parser = subparsers.add_parser("create-user", help="Create a new gateway user")
    create_parser.add_argument("gateway_id", help="Gateway ID (8 character hex, with or without ! prefix)")
    create_parser.add_argument("user_id", help="User ID (numeric)")
    create_parser.set_defaults(func=create_user_command)

    # Delete user command
    delete_parser = subparsers.add_parser("delete-user", help="Delete a gateway user")
    delete_parser.add_argument("gateway_id", help="Gateway ID (8 character hex, with or without ! prefix)")
    delete_parser.set_defaults(func=delete_user_command)

    # List users command
    list_parser = subparsers.add_parser("list-users", help="List all gateway users")
    list_parser.set_defaults(func=list_users_command)

    # Generate API key command
    apikey_parser = subparsers.add_parser("generate-apikey", help="Generate API keys and bootstrap file")
    apikey_parser.add_argument(
        "--bootstrap-file", "-b", help="Path to bootstrap file (default: /opt/emqx/etc/api_key.bootstrap)"
    )
    apikey_parser.add_argument("--force", "-f", action="store_true", help="Force overwrite existing files")
    apikey_parser.set_defaults(func=generate_apikey_command)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
