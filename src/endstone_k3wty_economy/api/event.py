import typing
from typing import Callable, Dict, List, Tuple

class EconomyEvent:
    def __init__(self) -> None:
        self._cancelled = False
 
    @property
    def is_cancelled(self) -> bool:
        return self._cancelled
 
    @is_cancelled.setter
    def is_cancelled(self, value: bool) -> None:
        self._cancelled = bool(value)
 
    def cancel(self) -> None:
        self._cancelled = True

class DatabaseOpenEvent(EconomyEvent):
    pass

class DatabaseCloseEvent(EconomyEvent):
    pass

class PlayerBalanceChangeEvent(EconomyEvent):
    def __init__(self, player_name: str, old_balance: float, new_balance: float) -> None:
        super().__init__()
        self.player_name = player_name
        self.old_balance = old_balance
        self.new_balance = new_balance

class PlayerRegisteredInDatabaseEvent(EconomyEvent):
    def __init__(self, player_name: str) -> None:
        super().__init__()
        self.player_name = player_name

class PlayerTransactionEvent(EconomyEvent):
    def __init__(self, sender: str, getter: str, value: float) -> None:
        super().__init__()
        self.sender = sender
        self.getter = getter
        self.value = value

class PlayerUnregisteredInDatabaseEvent(EconomyEvent):
    def __init__(self, player_name: str) -> None:
        super().__init__()
        self.player_name = player_name

def economy_event_handler(func=None, *, priority: int = 0):
    def decorator(f):
        f._is_economy_handler = True
        f._economy_priority = priority
        return f
 
    return decorator(func) if func else decorator

class EventBus:
    def __init__(self, logger=None) -> None:
        self._logger = logger
        self._handlers: Dict[type, List[Tuple[int, Callable]]] = {}
 
    def subscribe(self, event_type: type, handler: Callable, priority: int = 0) -> None:
        lst = self._handlers.setdefault(event_type, [])
        lst.append((priority, handler))
        lst.sort(key=lambda x: x[0])
 
    def unsubscribe(self, handler: Callable) -> None:
        for lst in self._handlers.values():
            lst[:] = [(p, h) for p, h in lst if h != handler]
 
    def register_listener(self, obj) -> int:
        count = 0
        for name in dir(obj):
            method = getattr(obj, name, None)
            if not callable(method) or not getattr(method, "_is_economy_handler", False):
                continue
            hints = typing.get_type_hints(method)
            hints.pop("return", None)
            event_type = next(iter(hints.values()), None)
            if not (isinstance(event_type, type) and issubclass(event_type, EconomyEvent)):
                if self._logger:
                    self._logger.error(f"[EconomyAPI] {name}: first parameter must be annotated with an EconomyEvent")
                continue
            self.subscribe(event_type, method, getattr(method, "_economy_priority", 0))
            count += 1
        return count

    def call(self, event: EconomyEvent) -> EconomyEvent:
        for _, handler in list(self._handlers.get(type(event), [])):
            try:
                handler(event)
            except Exception as e:
                if self._logger:
                    self._logger.error(f"[EconomyAPI] Event handler error: {e}")
        return event