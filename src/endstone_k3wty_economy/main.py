import math
import os
from endstone.plugin import Plugin
from endstone import Player, ColorFormat
from endstone.command import Command, CommandSender
from endstone.event import event_handler, PlayerJoinEvent
from endstone_k3wty_economy.api.economy import EconomyAPI
from endstone_k3wty_economy.api.event import PlayerRegisteredInDatabaseEvent, PlayerTransactionEvent, economy_event_handler

def fmt(value: float) -> str:
    return f"${value:,.2f}"

class Main(Plugin):
    api_version = "0.11"
    commands = {
        "pay": {
            "description": "Send money for another player",
            "usages": ["/pay <player: str> <amount: float>"],
            "permissions": ["white.endstone.k3wtyeconomy.commands.pay"]
        },
        "eco": {
            "description": "Use economy api",
            "permissions": ["white.endstone.k3wtyeconomy.commands.eco"],
            "usages": [
                "/eco",
                "/eco <action: str>",
                "/eco <action: str> <player: str>",
                "/eco <action: str> <player: str> <vault: str>",
                "/eco <action: str> <player: str> <value: float>",
                "/eco <action: str> <player: str> <value: float> <vault: str>"
            ],
            "aliases": ["economy"]
        },
        "balance": {
            "description": "See my balance",
            "permissions": ["white.endstone.k3wtyeconomy.commands.balance"],
            "usages": ["/balance"],
            "aliases": ["bal", "money", "mybal", "mybalance", "mymoney"]
        },
        "vault": {
            "description": "Vault settings",
            "permissions": ["white.endstone.k3wtyeconomy.commands.vault"],
            "usages": ["/vault", "/vault <action: str> [name: str]"]
        }
    }
    permissions = {
        "white.endstone.k3wtyeconomy.commands.pay": {
            "description": "Allow player to use a pay command",
            "default": True
        },
        "white.endstone.k3wtyeconomy.commands.eco": {
            "description": "Allow player to use a eco command",
            "default": "op"
        },
        "white.endstone.k3wtyeconomy.commands.balance": {
            "description": "Allow player to use a balance command",
            "default": True
        },
        "white.endstone.k3wtyeconomy.commands.vault": {
            "description": "Allow player to use a vault command",
            "default": "op"
        }
    }

    def __new__(cls, *args, **kwargs) -> None:
        plugin_dir = os.path.join("plugins", "k3wty_economy")
        config_path = os.path.join(plugin_dir, "config.toml")
        if not os.path.exists(plugin_dir):
            os.makedirs(plugin_dir, exist_ok=True)
        if not os.path.exists(config_path):
            with open(config_path, "w") as f:
                pass
        return super().__new__(cls)

    def on_enable(self) -> None:
        self.api = EconomyAPI(self)
        self.api.database_open()
        if not self.api.is_database_connected():
            self.logger.error("Database wasn't opened!")
            self.server.plugin_manager.disable_plugin(self)
            return
        self.register_events(self)
        self.api.events.register_listener(self)
        self.logger.info("K3wtyEconomyAPI was successfully loaded!")
        self.logger.info(f"GitHub: {ColorFormat.GREEN}https://github.com{ColorFormat.RESET}")
        self.logger.info(f"{ColorFormat.GOLD}Made with Claude{ColorFormat.RESET}")

    def on_disable(self) -> None:
        if hasattr(self, "api") and self.api is not None:
            self.api.database_close(force=True)

    @event_handler
    def on_join(self, event: PlayerJoinEvent) -> None:
        self.api.register_player(event.player.name)

    @economy_event_handler
    def on_player_register(self, event: PlayerRegisteredInDatabaseEvent) -> None:
        self.logger.info(f"{event.player_name} was registered in database!")

    @economy_event_handler
    def on_transaction(self, event: PlayerTransactionEvent) -> None:
        self.logger.info(f"{event.sender} sent {fmt(event.value)} to {event.getter}")

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if not self.api.is_database_connected():
            sender.send_error_message("Economy database is unavailable!")
            return False
        if command.name == "pay":
            if not isinstance(sender, Player):
                sender.send_error_message("Only players can use this command!")
                return False
            if not self.api.is_player_registered(sender.name):
                sender.send_error_message("You aren't registered in database!")
                return False
            if len(args) < 2:
                sender.send_error_message("Use /pay <player> <amount>")
                return False
            getter = self.server.get_player(args[0])
            if getter is None or not self.api.is_player_registered(getter.name):
                sender.send_error_message("Player isn't found!")
                return False
            sender_balance = self.api.get_player_balance(sender.name)
            try:
                value = float(args[1])
            except ValueError:
                sender.send_error_message("Amount of money must be a number!")
                return False
            if getter.name.lower() == sender.name.lower():
                sender.send_error_message("You can't pay yourself!")
                return False
            if not math.isfinite(value) or round(value, 2) <= 0:
                sender.send_error_message("Amount must be greater than 0!")
                return False
            value = round(value, 2)
            if value > sender_balance:
                sender.send_error_message("You don't have enough money!")
                return False
            if not self.api.money_transaction(sender.name, getter.name, value):
                sender.send_error_message("Transaction failed!")
                return False
            sender.send_message(f"You sent {fmt(value)} to {getter.name}")
            getter.send_message(f"{sender.name} sent you {fmt(value)}")
            return True
        if command.name == "balance":
            if not isinstance(sender, Player):
                sender.send_error_message("Only players can check their balance!")
                return False
            balance = self.api.get_player_balance(sender.name)
            sender.send_message(f"Your balance: {fmt(balance)}")
            return True
        if command.name == "eco":
            if len(args) == 0 or args is None or args[0].lower() == "help":
                sender.send_message("=== Eco Help ===\n/eco get <player> [vault]\n/eco set <player> <value> [vault]\n/eco add <player> <value> [vault]\n/eco withdraw <player> <value> [vault]")
                return True
            action = args[0].lower()
            if action not in ["get", "set", "withdraw", "add"]:
                sender.send_error_message("Unknown action, use /eco help to more info")
                return False
            if len(args) < 2:
                sender.send_error_message(f"Use /eco {action} <player>" + (" [vault]" if action == "get" else " <value> [vault]"))
                return False
            player = args[1]
            if action == "get":
                vault = args[2] if len(args) > 2 else "main"
            else:
                vault = args[3] if len(args) > 3 else "main"
            vault = vault.lower()
            if not self.api.is_vault_valid(vault):
                sender.send_error_message(f"Vault '{vault}' doesn't exist!")
                return False
            if not self.api.is_player_registered(player):
                sender.send_error_message("Player isn't registered in database!")
                return False
            player_balance = self.api.get_player_balance(player, vault)
            if action == "get":
                sender.send_message(f"{player}'s balance: {fmt(player_balance)}")
                return True
            if len(args) < 3:
                sender.send_error_message(f"Use /eco {action} <player> <value> [vault]")
                return False
            try:
                value = float(args[2])
            except ValueError:
                sender.send_error_message("Amount of money must be a number!")
                return False
            if not math.isfinite(value):
                sender.send_error_message("Amount of money must be a valid number!")
                return False
            if action == "set":
                if len(args) < 3:
                    sender.send_error_message("Use /eco set [player: str] [value: int]")
                    return False
                if value < 0:
                    sender.send_error_message("Amount of money must be 0 or greater!")
                    return False
                if not self.api.set_player_balance(player, value, vault):
                    sender.send_error_message("Couldn't change the balance")
                    return False
                sender.send_message(f"You set {player}'s balance to {fmt(value)}")
                return True
            if action == "add":
                if round(value, 2) <= 0:
                    sender.send_error_message("Amount of money must be a positive number!")
                    return False
                if not self.api.add_player_balance(player, value, vault):
                    sender.send_error_message("Couldn't change the balance")
                    return False
                sender.send_message(f"You add to {player}'s balance {fmt(value)}")
                return True
            if action == "withdraw":
                value = round(value, 2)
                if value <= 0:
                    sender.send_error_message("Amount of money must be a positive number!")
                    return False
                if player_balance <= 0:
                    sender.send_error_message(f"{player} has nothing to withdraw!")
                    return False
                if player_balance < value:
                    value = player_balance
                if not self.api.withdraw_player_balance(player, value, vault):
                    sender.send_error_message("Couldn't change the balance")
                    return False
                sender.send_message(f"You withdraw {fmt(value)} from {player}'s balance")
                return True
        if command.name == "vault":
            if len(args) == 0 or args is None or args[0].lower() == "help":
                sender.send_message("=== Vault Help ===\n/vault create <name>\n/vault delete <name>")
                return True
            action = args[0].lower()
            if action not in ["create", "delete"]:
                sender.send_error_message("Unknown action, use /vault help to more info")
                return False
            if len(args) < 2:
                sender.send_error_message(f"Use /vault {action} <n>")
                return False
            if action == "create":
                name = args[1].lower()
                if name is None:
                    sender.send_error_message("Vault's name must be defined!")
                    return False
                if not self.api.register_vault(name):
                    sender.send_error_message("Error! Vault wasn't registered!")
                    return False
                sender.send_message(f"Vault '{name}' was created")
                return True
            if action == "delete":
                name = args[1].lower()
                if name is None:
                    sender.send_error_message("Vault's name must be defined!")
                    return False
                if name == "main":
                    sender.send_error_message("The main vault can't be deleted!")
                    return False
                if not self.api.unregister_vault(name):
                    sender.send_error_message("Error! Vault wasn't unregistered!")
                    return False
                sender.send_message(f"Vault '{name}' was deleted")
                return True
        return False
