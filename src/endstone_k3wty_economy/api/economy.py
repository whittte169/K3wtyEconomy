import sqlite3
import os
from typing import Optional
from endstone.plugin import Plugin
import math
from endstone_k3wty_economy.api.event import EventBus, PlayerBalanceChangeEvent, PlayerTransactionEvent, PlayerRegisteredInDatabaseEvent, PlayerUnregisteredInDatabaseEvent, DatabaseCloseEvent, DatabaseOpenEvent

class EconomyAPI:
    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin
        self.data_folder = plugin.data_folder
        self.db_path = os.path.join(self.data_folder, "database.db")
        self.connect: Optional[sqlite3.Connection] = None
        self.events = EventBus(plugin.logger)

    def is_valid_amount(self, value) -> bool:
        return isinstance(value, (int, float)) and math.isfinite(value)

    def is_database_connected(self) -> bool:
        return self.connect is not None

    def call_event(self, event) -> bool:
        self.events.call(event)
        return not event.is_cancelled
    
    def database_open(self) -> bool:
        try:
            if not os.path.exists(self.data_folder):
                os.makedirs(self.data_folder, exist_ok=True)
            if not self.call_event(DatabaseOpenEvent()):
                return False
            self.connect = sqlite3.connect(self.db_path, check_same_thread=False)
            self.connect.execute("PRAGMA journal_mode=WAL")
            self.connect.execute("PRAGMA synchronous=NORMAL")
            with self.connect:
                self.connect.execute(
                    """
                    CREATE TABLE IF NOT EXISTS economy (
                        name TEXT PRIMARY KEY COLLATE NOCASE,
                        balance REAL NOT NULL DEFAULT 1000.0
                    )
                    """
                )
            return True
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            self.connect = None
            return False
    
    def database_close(self, force: bool = False) -> bool:
        if self.connect is None:
            return False
        if not force and not self.call_event(DatabaseCloseEvent()):
            return False
        try:
            self.connect.close()
            return True
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return False
        finally:
            self.connect = None
    
    def get_player_balance(self, name: str) -> float:
        if not self.is_database_connected():
            return 0.0
        try:
            row = self.connect.execute(
                "SELECT balance FROM economy WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
            return row[0] if row else 0.0
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return 0.0
    
    def set_player_balance(self, name: str, value: float) -> bool:
        if not self.is_database_connected() or not self.is_valid_amount(value):
            return False
        try:
            new_balance = round(max(0.0, value), 2)
            old_balance = self.get_player_balance(name)
            if not self.call_event(PlayerBalanceChangeEvent(name, old_balance, new_balance)):
                return False
            with self.connect:
                cur = self.connect.execute(
                    "UPDATE economy SET balance = ? WHERE name = ? COLLATE NOCASE",
                    (new_balance, name),
                )
            return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return False
    
    def add_player_balance(self, name: str, amount: float) -> bool:
        if not self.is_database_connected() or not self.is_valid_amount(amount) or amount <= 0:
            return False
        try:
            amount = round(amount, 2)
            old_balance = self.get_player_balance(name)
            if not self.call_event(PlayerBalanceChangeEvent(name, old_balance, old_balance + amount)):
                return False
            with self.connect:
                cur = self.connect.execute(
                    "UPDATE economy SET balance = balance + ? WHERE name = ? COLLATE NOCASE",
                    (amount, name),
                )
            return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return False

    def withdraw_player_balance(self, name: str, amount: float) -> bool:
        if not self.is_database_connected() or not self.is_valid_amount(amount) or amount <= 0:
            return False
        try:
            amount = round(amount, 2)
            old_balance = self.get_player_balance(name)
            if old_balance < amount:
                return False
            if not self.call_event(PlayerBalanceChangeEvent(name, old_balance, old_balance - amount)):
                return False
            with self.connect:
                cur = self.connect.execute(
                    "UPDATE economy SET balance = balance - ? "
                    "WHERE name = ? COLLATE NOCASE AND balance >= ?",
                    (amount, name, amount),
                )
            return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return False
    
    def money_transaction(self, sender: str, getter: str, value: float) -> bool:
        if not self.is_database_connected() or not self.is_valid_amount(value) or value <= 0:
            return False
        if sender.lower() == getter.lower():
            return False
        value = round(value, 2)
        try:
            if self.get_player_balance(sender) < value:
                return False
            if not self.call_event(PlayerTransactionEvent(sender, getter, value)):
                return False
            with self.connect:
                cur = self.connect.execute(
                    "UPDATE economy SET balance = balance - ? "
                    "WHERE name = ? COLLATE NOCASE AND balance >= ?",
                    (value, sender, value),
                )
                if cur.rowcount == 0:
                    return False
                cur = self.connect.execute(
                    "UPDATE economy SET balance = balance + ? WHERE name = ? COLLATE NOCASE",
                    (value, getter),
                )
                if cur.rowcount == 0:
                    raise ValueError("Getter isn't registered in DB!")
            return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return False
    
    def is_player_registered(self, name: str) -> bool:
        if not self.is_database_connected():
            self.plugin.logger.error("[EconomyAPI] Database isn't opened!")
            return False
        try:
            row = self.connect.execute(
                "SELECT 1 FROM economy WHERE name = ? COLLATE NOCASE LIMIT 1", (name,)
            ).fetchone()
            return row is not None
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return False
    
    def register_player(self, name: str) -> bool:
        if not self.is_database_connected():
            self.plugin.logger.error("[EconomyAPI] Database isn't opened!")
            return False
        try:
            if self.is_player_registered(name):
                return False
            if not self.call_event(PlayerRegisteredInDatabaseEvent(name)):
                return False
            with self.connect:
                cur = self.connect.execute(
                    "INSERT OR IGNORE INTO economy (name, balance) VALUES (?, ?)",
                    (name, 1000.0),
                )
            if cur.rowcount == 0:
                return False
            return True
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return False

    def unregister_player(self, name: str) -> bool:
        if not self.is_database_connected():
            self.plugin.logger.error("[EconomyAPI] Database isn't opened!")
            return False
        try:
            if not self.is_player_registered(name):
                return False
            if not self.call_event(PlayerUnregisteredInDatabaseEvent(name)):
                return False
            with self.connect:
                cur = self.connect.execute(
                    "DELETE FROM economy WHERE name = ? COLLATE NOCASE", (name,)
                )
            return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"[EconomyAPI] {e}")
            return False
