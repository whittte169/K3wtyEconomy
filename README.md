# K3wtyEconomy

Lightweight and fast economy system for [Endstone](https://github.com/EndstoneMC/endstone) (Minecraft Bedrock) servers.

K3wtyEconomy is a standalone plugin that stores player balances in a local SQLite database and exposes a small, synchronous **Python API** and an **event system** so other plugins can read and modify balances, send money between players and react to economy activity.

> **Package:** `endstone-k3wty-economy` · **Version:** `1.0.0` · **Requires:** `endstone >= 0.11.0` · **Plugin name:** `k3wty_economy`
>
> **GitHub:** <https://github.com/whittte169/K3wtyEconomy>

---

## Table of contents

- [Features](#features)
- [Installation](#installation)
  - [For server owners](#for-server-owners)
  - [For plugin developers](#for-plugin-developers)
- [Quick start](#quick-start)
- [Getting the API](#getting-the-api)
  - [Hard dependency](#hard-dependency)
  - [Optional (soft) dependency](#optional-soft-dependency)
- [API reference](#api-reference)
  - [Balance methods](#balance-methods)
  - [Player registration](#player-registration)
  - [Database lifecycle](#database-lifecycle)
- [Events](#events)
  - [Event list](#event-list)
  - [Listening to events](#listening-to-events)
  - [Cancelling events](#cancelling-events)
  - [Priorities](#priorities)
  - [Manual subscription](#manual-subscription)
- [Behaviour notes and gotchas](#behaviour-notes-and-gotchas)
- [Full example plugin](#full-example-plugin)
- [Commands and permissions](#commands-and-permissions)
- [Project layout](#project-layout)

---

## Features

- Simple name-based balance storage in SQLite (WAL mode, no external services required).
- Automatic player registration on first join (starting balance: `1000.00`).
- Atomic money transfers between players.
- Cancellable events for every important action (balance changes, transactions, registration, database open/close).
- Built-in `/balance`, `/pay` and `/eco` commands.
- Zero configuration.

---

## Installation

K3wtyEconomy is **not published on PyPI**. Install it from GitHub.

### For server owners

1. Download the latest `.whl` file from the [GitHub repository](https://github.com/whittte169/K3wtyEconomy) (Releases page), or build it yourself (see below).
2. Put the file into your Endstone server's `plugins/` folder.
3. Restart the server.

The database is created automatically at `plugins/k3wty_economy/database.db` (the plugin's data folder).

### For plugin developers

You need the package installed in your development environment so that your IDE can resolve imports and type hints, and so that you can import the event classes at runtime.

Install straight from GitHub:

```bash
pip install git+https://github.com/whittte169/K3wtyEconomy.git
```

Or clone and install in editable mode:

```bash
git clone https://github.com/whittte169/K3wtyEconomy.git
cd K3wtyEconomy
pip install -e .
```

Or build a wheel and install that:

```bash
git clone https://github.com/whittte169/K3wtyEconomy.git
cd K3wtyEconomy
pip install build
python -m build --wheel
pip install dist/endstone_k3wty_economy-1.0.0-py3-none-any.whl
```

If you want to declare it in your own `pyproject.toml`, use a direct reference:

```toml
[project]
dependencies = [
    "endstone>=0.11.0",
    "endstone-k3wty-economy @ git+https://github.com/whittte169/K3wtyEconomy.git",
]
```

> **Note:** PyPI rejects packages that contain direct-URL dependencies. If you plan to publish your own plugin to PyPI, leave K3wtyEconomy out of `dependencies` and tell your users to install it separately.

**Important:** your plugin only *uses* the API. The K3wtyEconomy plugin itself must also be installed on the server (in `plugins/`) and enabled, because it owns the database and runs the API instance.

---

## Quick start

```python
from endstone.plugin import Plugin
from endstone_k3wty_economy.api.economy import EconomyAPI


class MyPlugin(Plugin):
    api_version = "0.11"
    depend = ["k3wty_economy"]          # load after K3wtyEconomy

    def on_enable(self) -> None:
        economy_plugin = self.server.plugin_manager.get_plugin("k3wty_economy")
        self.economy: EconomyAPI = economy_plugin.api

        # Give a player 50 coins
        if self.economy.add_player_balance("Steve", 50):
            self.logger.info("Steve received 50 coins")
```

---

## Getting the API

K3wtyEconomy creates an `EconomyAPI` instance in its `on_enable()` and stores it on the plugin object as the `api` attribute. Other plugins obtain it through Endstone's plugin manager.

The plugin name is `k3wty_economy`.

### Hard dependency

Use this when your plugin cannot work without the economy.

```python
from endstone.plugin import Plugin
from endstone_k3wty_economy.api.economy import EconomyAPI


class ShopPlugin(Plugin):
    api_version = "0.11"
    depend = ["k3wty_economy"]

    def on_enable(self) -> None:
        eco_plugin = self.server.plugin_manager.get_plugin("k3wty_economy")
        self.economy: EconomyAPI = eco_plugin.api

        if not self.economy.is_database_connected():
            self.logger.error("Economy database is not available, disabling.")
            self.server.plugin_manager.disable_plugin(self)
            return
```

### Optional (soft) dependency

Use this when the economy is a bonus feature.

```python
from endstone.plugin import Plugin

try:
    from endstone_k3wty_economy.api.economy import EconomyAPI
except ImportError:          # package is not installed in this environment
    EconomyAPI = None


class MyPlugin(Plugin):
    api_version = "0.11"
    soft_depend = ["k3wty_economy"]

    economy = None

    def on_enable(self) -> None:
        eco_plugin = self.server.plugin_manager.get_plugin("k3wty_economy")
        if eco_plugin is not None and eco_plugin.is_enabled:
            self.economy = eco_plugin.api
            self.logger.info("Economy support enabled")
        else:
            self.logger.warning("K3wtyEconomy not found, economy features disabled")

    def charge(self, player_name: str, price: float) -> bool:
        if self.economy is None:
            return True          # free if there is no economy
        return self.economy.withdraw_player_balance(player_name, price)
```

---

## API reference

All methods live on `endstone_k3wty_economy.api.economy.EconomyAPI`.

- Player names are **case-insensitive** (`"Steve"` and `"steve"` are the same account).
- Money is stored as a `float` and **rounded to 2 decimal places**.
- Amounts must be finite numbers (`NaN` and `inf` are rejected).
- Methods never raise on failure. They log the error to the server console and return `False` / `0.0`.

### Balance methods

| Method | Returns | Description |
|---|---|---|
| `get_player_balance(name: str)` | `float` | Current balance. Returns `0.0` if the player is not registered **or** if the database is unavailable. |
| `set_player_balance(name: str, value: float)` | `bool` | Sets the balance to `value`. Negative values are clamped to `0.0`. Fires `PlayerBalanceChangeEvent`. |
| `add_player_balance(name: str, amount: float)` | `bool` | Adds `amount` (must be `> 0`). Fires `PlayerBalanceChangeEvent`. |
| `withdraw_player_balance(name: str, amount: float)` | `bool` | Removes `amount` (must be `> 0`). Returns `False` if the player does not have enough money; the balance is never driven below zero. Fires `PlayerBalanceChangeEvent`. |
| `money_transaction(sender: str, getter: str, value: float)` | `bool` | Atomically moves `value` from `sender` to `getter`. Fires `PlayerTransactionEvent`. Fails if `sender == getter`, if the sender cannot afford it, or if either account is not registered. |
| `is_valid_amount(value)` | `bool` | `True` if `value` is an `int`/`float` and finite. |

```python
eco = self.economy

balance = eco.get_player_balance("Steve")        # 1000.0

eco.set_player_balance("Steve", 250)             # True
eco.add_player_balance("Steve", 99.999)          # True  -> adds 100.0 (rounded)
eco.withdraw_player_balance("Steve", 1_000_000)  # False (not enough money)

if eco.money_transaction("Steve", "Alex", 30):
    print("Steve paid Alex 30")
```

### Player registration

| Method | Returns | Description |
|---|---|---|
| `is_player_registered(name: str)` | `bool` | Whether the player has an account. |
| `register_player(name: str)` | `bool` | Creates an account with a starting balance of `1000.0`. Returns `False` if the player already exists. Fires `PlayerRegisteredInDatabaseEvent`. |
| `unregister_player(name: str)` | `bool` | Deletes the account and its balance. Fires `PlayerUnregisteredInDatabaseEvent`. |

K3wtyEconomy automatically calls `register_player()` on every `PlayerJoinEvent`, so you normally don't have to. Use `is_player_registered()` when you need to tell "balance is zero" apart from "no account", because `get_player_balance()` returns `0.0` in both cases.

```python
if not eco.is_player_registered("Steve"):
    return  # unknown player, don't touch the economy
```

### Database lifecycle

| Method | Returns | Description |
|---|---|---|
| `is_database_connected()` | `bool` | `True` if the SQLite connection is open. |
| `database_open()` | `bool` | Opens the database and creates the table. Fires `DatabaseOpenEvent`. |
| `database_close(force: bool = False)` | `bool` | Closes the connection. With `force=False`, fires a cancellable `DatabaseCloseEvent`. |

K3wtyEconomy opens the database in its own `on_enable()` and force-closes it in `on_disable()`. **Other plugins should not open or close the database.** Always check `is_database_connected()` instead.

---

## Events

K3wtyEconomy has its **own** event system, separate from Endstone's. It lives in `endstone_k3wty_economy.api.event`, and the event bus is available as `economy.events`.

### Event list

| Event | Fired by | Fields |
|---|---|---|
| `PlayerBalanceChangeEvent` | `set_player_balance`, `add_player_balance`, `withdraw_player_balance` | `player_name`, `old_balance`, `new_balance` |
| `PlayerTransactionEvent` | `money_transaction` | `sender`, `getter`, `value` |
| `PlayerRegisteredInDatabaseEvent` | `register_player` | `player_name` |
| `PlayerUnregisteredInDatabaseEvent` | `unregister_player` | `player_name` |
| `DatabaseOpenEvent` | `database_open` | none |
| `DatabaseCloseEvent` | `database_close` (when `force=False`) | none |

All events inherit from `EconomyEvent` and have:

- `event.is_cancelled` (read/write property)
- `event.cancel()`

Events are fired **before** the change is written. If any handler cancels the event, the operation is aborted and the API method returns `False`.

### Listening to events

Decorate a method with `@economy_event_handler`, annotate the first parameter with the event class, then register the object with `economy.events.register_listener(...)`.

```python
from endstone.plugin import Plugin
from endstone_k3wty_economy.api.economy import EconomyAPI
from endstone_k3wty_economy.api.event import (
    PlayerBalanceChangeEvent,
    PlayerTransactionEvent,
    economy_event_handler,
)


class AuditPlugin(Plugin):
    api_version = "0.11"
    depend = ["k3wty_economy"]

    def on_enable(self) -> None:
        self.economy: EconomyAPI = (
            self.server.plugin_manager.get_plugin("k3wty_economy").api
        )
        count = self.economy.events.register_listener(self)
        self.logger.info(f"Registered {count} economy handlers")

    @economy_event_handler
    def on_balance_change(self, event: PlayerBalanceChangeEvent) -> None:
        self.logger.info(
            f"{event.player_name}: {event.old_balance} -> {event.new_balance}"
        )

    @economy_event_handler
    def on_transaction(self, event: PlayerTransactionEvent) -> None:
        self.logger.info(f"{event.sender} -> {event.getter}: {event.value}")
```

`register_listener()` returns the number of handlers it registered. Methods whose first parameter is not annotated with an `EconomyEvent` subclass are skipped and an error is logged.

> The event type is read from the method's **type annotation**, so the annotation is mandatory and must be resolvable at runtime (import the event class normally, not only under `TYPE_CHECKING`).

You can use Endstone's `@event_handler` and K3wtyEconomy's `@economy_event_handler` on methods of the same class. They are independent systems, and each must be registered separately (`self.register_events(self)` for Endstone, `economy.events.register_listener(self)` for the economy).

### Cancelling events

```python
@economy_event_handler
def limit_transfers(self, event: PlayerTransactionEvent) -> None:
    if event.value > 10_000:
        event.cancel()       # money_transaction() will return False
```

```python
@economy_event_handler
def protect_account(self, event: PlayerBalanceChangeEvent) -> None:
    if event.player_name.lower() == "bank" and event.new_balance < event.old_balance:
        event.is_cancelled = True
```

Cancelling does not send any message to the player. Your handler (or the code that called the API) is responsible for explaining why the action failed.

### Priorities

```python
@economy_event_handler(priority=-10)
def runs_first(self, event: PlayerBalanceChangeEvent) -> None: ...

@economy_event_handler(priority=10)
def runs_later(self, event: PlayerBalanceChangeEvent) -> None: ...
```

Handlers run in **ascending** priority order (lowest number first, default `0`). A cancelled event is **still delivered** to the remaining handlers, so check `event.is_cancelled` if you want to ignore events cancelled earlier. An exception inside a handler is caught and logged, and does not stop other handlers.

### Manual subscription

If you prefer not to use decorators:

```python
def my_handler(event: PlayerBalanceChangeEvent) -> None:
    ...

economy.events.subscribe(PlayerBalanceChangeEvent, my_handler, priority=0)

# later
economy.events.unsubscribe(my_handler)
```

Handlers are **not** removed automatically when your plugin is disabled. If your plugin can be reloaded, unsubscribe in `on_disable()`:

```python
def on_disable(self) -> None:
    self.economy.events.unsubscribe(self.on_balance_change)
```

---

## Behaviour notes and gotchas

- **Accounts are keyed by player name, not UUID.** If a player changes their gamertag, they get a new account.
- **Starting balance is `1000.0`** and is currently hard-coded.
- **`get_player_balance()` returns `0.0` on any failure** (unknown player, closed database, SQL error). Use `is_player_registered()` and `is_database_connected()` to distinguish.
- **Events fire before validation of the account.** For example, `add_player_balance("Nobody", 10)` fires `PlayerBalanceChangeEvent` (with `old_balance = 0.0`) and then returns `False` because no such account exists. Check `is_player_registered()` first if this matters.
- **`money_transaction()` fires only `PlayerTransactionEvent`**, not two `PlayerBalanceChangeEvent`s. If you track all balance movements, listen to both events.
- **`money_transaction()` is atomic.** If the receiver is not registered, the sender is not charged.
- **`set_player_balance()` clamps negatives to `0.0`**, whereas `withdraw_player_balance()` refuses to overdraw and returns `False`.
- **Amounts are rounded to 2 decimals** before they are stored. Don't rely on sub-cent precision.
- **Everything is synchronous** and uses a single SQLite connection (`check_same_thread=False`) without a lock. Call the API from Endstone's main thread or scheduler callbacks, and avoid calling it from your own worker threads.
- **Database events and plugin load order.** The database is opened inside K3wtyEconomy's `on_enable()`, so `DatabaseOpenEvent` is fired before other plugins can attach listeners. Listeners are mainly useful for `DatabaseCloseEvent`.

---

## Full example plugin

A tiny shop plugin with a `/buy` command that charges the player and lets other plugins veto purchases through the economy event system.

```python
from endstone import Player
from endstone.command import Command, CommandSender
from endstone.plugin import Plugin

from endstone_k3wty_economy.api.economy import EconomyAPI
from endstone_k3wty_economy.api.event import (
    PlayerBalanceChangeEvent,
    economy_event_handler,
)


class ShopPlugin(Plugin):
    api_version = "0.11"
    depend = ["k3wty_economy"]

    commands = {
        "buy": {
            "description": "Buy a diamond for 25 coins",
            "usages": ["/buy"],
            "permissions": ["myshop.commands.buy"],
        }
    }
    permissions = {
        "myshop.commands.buy": {
            "description": "Allow players to use /buy",
            "default": True,
        }
    }

    PRICE = 25.0

    def on_enable(self) -> None:
        eco_plugin = self.server.plugin_manager.get_plugin("k3wty_economy")
        self.economy: EconomyAPI = eco_plugin.api
        self.economy.events.register_listener(self)

    def on_disable(self) -> None:
        self.economy.events.unsubscribe(self.log_change)

    @economy_event_handler
    def log_change(self, event: PlayerBalanceChangeEvent) -> None:
        if event.is_cancelled:
            return
        self.logger.info(
            f"[Shop] {event.player_name}: "
            f"{event.old_balance:.2f} -> {event.new_balance:.2f}"
        )

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if command.name != "buy":
            return False

        if not isinstance(sender, Player):
            sender.send_error_message("Only players can use this command!")
            return False

        if not self.economy.is_database_connected():
            sender.send_error_message("Economy is currently unavailable.")
            return False

        if not self.economy.is_player_registered(sender.name):
            sender.send_error_message("You don't have an economy account yet.")
            return False

        if not self.economy.withdraw_player_balance(sender.name, self.PRICE):
            sender.send_error_message(
                f"Not enough money! You need {self.PRICE:.2f}, "
                f"you have {self.economy.get_player_balance(sender.name):.2f}."
            )
            return False

        sender.inventory.add_item(...)  # give the item here
        sender.send_message(f"You bought a diamond for {self.PRICE:.2f}!")
        return True
```

---

## Commands and permissions

These are provided by K3wtyEconomy itself.

| Command | Aliases | Description | Permission | Default |
|---|---|---|---|---|
| `/balance` | `bal`, `money`, `mybal`, `mybalance`, `mymoney` | Show your own balance. | `white.endstone.k3wtyeconomy.commands.balance` | everyone |
| `/pay <player> <amount>` | none | Send money to another online player. | `white.endstone.k3wtyeconomy.commands.pay` | everyone |
| `/eco <get\|set\|add\|withdraw> <player> [amount]` | `/economy` | Administrative balance management. Use `/eco help` for usage. | `white.endstone.k3wtyeconomy.commands.eco` | operators |

---

## Project layout

```
src/endstone_k3wty_economy/
├── main.py          # Plugin entry point (commands, auto-registration on join)
└── api/
    ├── economy.py   # EconomyAPI: balances, registration, database
    └── event.py     # EconomyEvent classes, @economy_event_handler, EventBus
```

The plugin entry point is declared in `pyproject.toml`:

```toml
[project.entry-points."endstone"]
k3wty_economy = "endstone_k3wty_economy.main:Main"
```

---

## Links

- Repository: <https://github.com/whittte169/K3wtyEconomy>
- Endstone: <https://github.com/EndstoneMC/endstone>
