from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class NormalDist:
    mean: float
    sd: float
    clip: Optional[Tuple[float, float]] = None

    def sample(self, size=None):
        x = np.random.normal(self.mean, self.sd, size=size)
        if self.clip is not None:
            lo, hi = self.clip
            x = np.clip(x, lo, hi)
        return x