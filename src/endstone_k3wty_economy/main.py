import math
from endstone.plugin import Plugin
from endstone import Player
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
            "usages": ["/eco <action: str> [player: str] [amount: float]"],
            "aliases": ["economy"]
        },
        "balance": {
            "description": "See my balance",
            "permissions": ["white.endstone.k3wtyeconomy.commands.balance"],
            "usages": ["/balance"],
            "aliases": ["bal", "money", "mybal", "mybalance", "mymoney"]
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
        }
    }

    def on_enable(self) -> None:
        self.api = EconomyAPI(self)
        self.api.database_open()
        if not self.api.is_database_connected():
            self.logger.error("[EconomyAPI] Database wasn't opened!")
            return
        self.register_events(self)
        self.logger.info("[EconomyAPI] K3wtyEconomyAPI was successfuly loaded!")
        self.logger.info("[EconomyAPI] GitHub: https://github.com/whittte169/K3wtyEconomy")

    def on_disable(self) -> None:
        self.api.database_close(force=True)

    @event_handler
    def on_join(self, event: PlayerJoinEvent) -> None:
        self.api.register_player(event.player.name)

    @economy_event_handler
    def on_player_register(self, event: PlayerRegisteredInDatabaseEvent) -> None:
        self.logger.info(f"[EconomyAPI] {event.player_name} was registered in database!")

    @economy_event_handler
    def on_transaction(self, event: PlayerTransactionEvent) -> None:
        self.logger.info(f"[EconomyAPI] {event.sender} has sended {fmt(event.value)} for {event.getter}")

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
            if value > sender_balance:
                sender.send_error_message("You hasn't enough money!")
                return False
            if not math.isfinite(value) or value <= 0:
                sender.send_error_message("Amount must be greater than 0!")
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
                sender.send_message("=== Eco Help ===\n/eco get [player]\n/eco set [player] [value]\n/eco add [player] [value]\n/eco withdraw [player] [value]")
                return False
            action = args[0].lower()
            if action not in ["get", "set", "withdraw", "add"]:
                sender.send_error_message("Unknown action, use /eco help to more info")
                return False
            if len(args) < 2:
                sender.send_error_message(f"Use /eco {action} <player>" + ("" if action == "get" else " <value>"))
                return False
            player = args[1]
            if not self.api.is_player_registered(player):
                sender.send_error_message("Player isn't registered in database!")
                return False
            if action == "get":
                player_balance = self.api.get_player_balance(player)
                sender.send_message(f"{player}'s balance: {fmt(player_balance)}")
                return True
            if len(args) < 3:
                sender.send_error_message(f"Use /eco {action} <player> <value>")
                return False
            try:
                value = float(args[2])
            except ValueError:
                sender.send_error_message("Amount of money must be a number!")
                return False
            if not math.isfinite(value):
                sender.send_error_message("Amount of money must be a valid number!")
                return False
            if args[0] == "set":
                if len(args) < 3:
                    sender.send_error_message("Use /eco set [player: str] [value: int]")
                    return False
                if value < 0:
                    sender.send_error_message("Amount of money must be 0 or greater!")
                    return False
                if not self.api.set_player_balance(player, value):
                    sender.send_error_message("Couldn't change the balance")
                    return False
                player_balance = self.api.get_player_balance(player)
                sender.send_message(f"You set {player}'s balance to {fmt(value)}")
                return True
            if args[0] == "add":
                if value <= 0:
                    sender.send_error_message("Amount of money must be a positive number!")
                    return False
                if not self.api.add_player_balance(player, value):
                    sender.send_error_message("Couldn't change the balance")
                    return False
                sender.send_message(f"You add to {player}'s balance {fmt(value)}")
                return True
            if args[0] == "withdraw":
                value = math.abs(value)
                player_balance = self.api.get_player_balance(player)
                if value <= 0:
                    sender.send_error_message("Nothing to withdraw!")
                    return False
                if player_balance < value:
                    value = player_balance
                self.api.withdraw_player_balance(player, value)
                sender.send_message(f"You withdraw {fmt(value)} from {player}'s balance")
                return True
        return False