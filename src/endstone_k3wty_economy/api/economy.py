import sqlite3
import os
from typing import Optional
from endstone.plugin import Plugin
import math
import re
import threading
from endstone_k3wty_economy.api.event import (
    EventBus, PlayerBalanceChangeEvent, PlayerTransactionEvent, PlayerRegisteredInDatabaseEvent,
    PlayerUnregisteredInDatabaseEvent, DatabaseCloseEvent, DatabaseOpenEvent,
    VaultRegisteredEvent, VaultUnregisteredEvent
)

MAIN = "main"
DEFAULT_BALANCE = 1000.0
VAULT_RE = re.compile(r"[A-Za-z0-9_]+")

class EconomyAPI:
    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin
        self.logger = plugin.logger
        self.data_folder = plugin.data_folder
        self.db_path = os.path.join(self.data_folder, "database.db")
        self.connect: Optional[sqlite3.Connection] = None
        self.events = EventBus(plugin.logger)
        self.lock = threading.RLock()
        self.vaults: set[str] = set()

    def is_valid_amount(self, value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def is_database_connected(self) -> bool:
        return self.connect is not None

    def call_event(self, event) -> bool:
        self.events.call(event)
        return not event.is_cancelled

    @staticmethod
    def normalize_vault(vault) -> Optional[str]:
        if not isinstance(vault, str) or not VAULT_RE.fullmatch(vault):
            return None
        return vault.lower()

    def is_vault_valid(self, vault: str) -> bool:
        v = self.normalize_vault(vault)
        return v is not None and v in self.vaults

    def table(self, vault: str) -> Optional[str]:
        v = self.normalize_vault(vault)
        if v is None:
            self.logger.error(f"Invalid vault name format: {vault!r}")
            return None
        if v not in self.vaults:
            self.logger.error(f"Vault {v} doesn't exist in database!")
            return None
        return f"economy_{v}"

    def select_balance(self, table: str, name: str) -> Optional[float]:
        row = self.connect.execute(
            f"SELECT balance FROM {table} WHERE name = ?", (name,)
        ).fetchone()
        return row[0] if row else None

    def _ensure_account(self, table: str, name: str) -> bool:
        if not self.is_player_registered(name):
            return False
        if table != f"economy_{MAIN}":
            with self.connect:
                self.connect.execute(
                    f"INSERT OR IGNORE INTO {table} (name, balance) VALUES (?, ?)",
                    (name, DEFAULT_BALANCE),
                )
        return True

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
                    f"""
                    CREATE TABLE IF NOT EXISTS economy_{MAIN} (
                        name TEXT PRIMARY KEY COLLATE NOCASE,
                        balance REAL NOT NULL DEFAULT {DEFAULT_BALANCE}
                    )
                    """
                )
            rows = self.connect.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            self.vaults = {
                r[0][8:].lower() for r in rows
                if r[0].startswith("economy_") and VAULT_RE.fullmatch(r[0][8:])
            }
            return True
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            if self.connect is not None:
                try:
                    self.connect.close()
                except Exception:
                    pass
            self.connect = None
            return False

    def database_close(self, force: bool = False) -> bool:
        if self.connect is None:
            return False
        if not force and not self.call_event(DatabaseCloseEvent()):
            return False
        with self.lock:
            try:
                self.connect.close()
                return True
            except Exception as e:
                self.plugin.logger.error(f"{e}")
                return False
            finally:
                self.connect = None
                self.vaults.clear()

    def get_player_balance(self, name: str, vault: str="main") -> float:
        if not self.is_database_connected():
            return 0.0
        table = self.table(vault)
        if table is None:
            return 0.0
        try:
            with self.lock:
                if not self._ensure_account(table, name):
                    return 0.0
                balance = self.select_balance(table, name)
            return balance if balance is not None else 0.0
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return 0.0

    def set_player_balance(self, name: str, value: float, vault: str="main") -> bool:
        if not self.is_database_connected() or not self.is_valid_amount(value):
            return False
        table = self.table(vault)
        if table is None:
           return False
        new_balance = round(max(0.0, value), 2)
        try:
            with self.lock:
                if not self._ensure_account(table, name):
                    return False
                old_balance = self.select_balance(table, name)
                if old_balance is None:
                    return False
                if not self.call_event(PlayerBalanceChangeEvent(name, old_balance, new_balance, vault.lower())):
                    return False
                with self.connect:
                    cur = self.connect.execute(
                        f"UPDATE {table} SET balance = ? WHERE name = ?",
                        (new_balance, name),
                    )
                return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False

    def add_player_balance(self, name: str, amount: float, vault: str="main") -> bool:
        if not self.is_database_connected() or not self.is_valid_amount(amount):
            return False
        amount = round(amount, 2)
        if amount <= 0:
            return False
        table = self.table(vault)
        if table is None:
            return False
        try:
            with self.lock:
                if not self._ensure_account(table, name):
                    return False
                old_balance = self.select_balance(table, name)
                if old_balance is None:
                    return False
                if not self.call_event(PlayerBalanceChangeEvent(name, old_balance, round(old_balance + amount, 2), vault.lower())):
                    return False
                with self.connect:
                    cur = self.connect.execute(
                        f"UPDATE {table} SET balance = balance + ? WHERE name = ?",
                        (amount, name),
                    )
                return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False

    def withdraw_player_balance(self, name: str, amount: float, vault: str="main") -> bool:
        if not self.is_database_connected() or not self.is_valid_amount(amount):
            return False
        amount = round(amount, 2)
        if amount <= 0:
            return False
        table = self.table(vault)
        if table is None:
            return False
        try:
            with self.lock:
                if not self._ensure_account(table, name):
                    return False
                old_balance = self.select_balance(table, name)
                if old_balance is None or old_balance < amount:
                    return False
                if not self.call_event(PlayerBalanceChangeEvent(name, old_balance, round(old_balance - amount, 2), vault.lower())):
                    return False
                with self.connect:
                    cur = self.connect.execute(
                        f"UPDATE {table} SET balance = balance - ? WHERE name = ? AND balance >= ?",
                        (amount, name, amount),
                    )
                return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False

    def money_transaction(self, sender: str, getter: str, value: float, vault: str="main") -> bool:
        if not self.is_database_connected() or not self.is_valid_amount(value):
            return False
        value = round(value, 2)
        if value <= 0:
            return False
        if sender.lower() == getter.lower():
            return False
        table = self.table(vault)
        if table is None:
            return False
        try:
            with self.lock:
                if not self._ensure_account(table, sender) or not self._ensure_account(table, getter):
                    return False
                sender_balance = self.select_balance(table, sender)
                if sender_balance is None or sender_balance < value:
                    return False
                if not self.call_event(PlayerTransactionEvent(sender, getter, value, vault.lower())):
                    return False
                with self.connect:
                    cur = self.connect.execute(
                        f"UPDATE {table} SET balance = balance - ? WHERE name = ? AND balance >= ?",
                        (value, sender, value),
                    )
                    if cur.rowcount == 0:
                        return False
                    cur = self.connect.execute(
                        f"UPDATE {table} SET balance = balance + ? WHERE name = ?",
                        (value, getter),
                    )
                    if cur.rowcount == 0:
                        raise ValueError("Getter isn't registered in DB!")
                return True
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False

    def is_player_registered(self, name: str) -> bool:
        if not self.is_database_connected():
            self.plugin.logger.error("Database isn't opened!")
            return False
        try:
            with self.lock:
                row = self.connect.execute(
                    f"SELECT 1 FROM economy_{MAIN} WHERE name = ? LIMIT 1", (name,)
                ).fetchone()
            return row is not None
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False

    def register_player(self, name: str) -> bool:
        if not self.is_database_connected():
            self.plugin.logger.error("Database isn't opened!")
            return False
        try:
            with self.lock:
                if self.is_player_registered(name):
                    return False
                if not self.call_event(PlayerRegisteredInDatabaseEvent(name)):
                    return False
                with self.connect:
                    cur = self.connect.execute(
                        f"INSERT OR IGNORE INTO economy_{MAIN} (name, balance) VALUES (?, ?)",
                        (name, DEFAULT_BALANCE),
                    )
                return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False

    def unregister_player(self, name: str) -> bool:
        if not self.is_database_connected():
            self.plugin.logger.error("Database isn't opened!")
            return False
        try:
            with self.lock:
                if not self.is_player_registered(name):
                    return False
                if not self.call_event(PlayerUnregisteredInDatabaseEvent(name)):
                    return False
                with self.connect:
                    cur = self.connect.execute(
                        f"DELETE FROM economy_{MAIN} WHERE name = ?", (name,)
                    )
                    for v in self.vaults - {MAIN}:
                        self.connect.execute(f"DELETE FROM economy_{v} WHERE name = ?", (name,))
                return cur.rowcount > 0
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False

    def register_vault(self, vault: str) -> bool:
        if not self.is_database_connected():
            self.plugin.logger.error("Database isn't opened!")
            return False
        v = self.normalize_vault(vault)
        if v is None:
            self.plugin.logger.error(f"Invalid vault name format: {vault!r}")
            return False
        try:
            with self.lock:
                if v in self.vaults:
                    self.plugin.logger.error(f"Vault {v} is already registered in database!")
                    return False
                if not self.call_event(VaultRegisteredEvent(v)):
                    return False
                with self.connect:
                    self.connect.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS economy_{v} (
                            name TEXT PRIMARY KEY COLLATE NOCASE,
                            balance REAL NOT NULL DEFAULT {DEFAULT_BALANCE}
                        )
                        """
                    )
                self.vaults.add(v)
                return True
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False

    def unregister_vault(self, vault: str) -> bool:
        if not self.is_database_connected():
            self.plugin.logger.error("Database isn't opened!")
            return False
        v = self.normalize_vault(vault)
        if v is None:
            self.plugin.logger.error(f"Invalid vault name format: {vault!r}")
            return False
        if v == MAIN:
            self.plugin.logger.error("The main vault can't be removed!")
            return False
        try:
            with self.lock:
                if v not in self.vaults:
                    self.plugin.logger.error(f"Vault {v} isn't registered in database!")
                    return False
                if not self.call_event(VaultUnregisteredEvent(v)):
                    return False
                with self.connect:
                    self.connect.execute(f"DROP TABLE IF EXISTS economy_{v}")
                self.vaults.discard(v)
                return True
        except Exception as e:
            self.plugin.logger.error(f"{e}")
            return False
