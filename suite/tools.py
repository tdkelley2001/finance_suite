from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SuiteTool:
    name: str
    title: str
    caption: str
    render: Callable[["SuiteTool"], None]
    icon: str = ""
    advice_warning: bool = False

    @property
    def nav_label(self) -> str:
        if not self.icon:
            return self.name
        return f"{self.icon} {self.name}"
