"""Turns a noisy stream of class probabilities into stable commands.

Used only in continuous mode. The web app has an identical implementation in
web/src/lib/gate.ts; both are tested against the same vectors.
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CommandGate:
    n_classes: int = 3
    rest_index: int = 0
    alpha: float = 0.3
    threshold: float = 0.6
    dwell: int = 2
    release: float = 0.45
    smoothed: np.ndarray = field(init=False)
    active: int = field(init=False)
    _candidate: int = field(init=False)
    _count: int = field(init=False)

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.smoothed = np.full(self.n_classes, 1.0 / self.n_classes)
        self.active = self.rest_index
        self._candidate = self.rest_index
        self._count = 0

    def update(self, probs: np.ndarray) -> int:
        self.smoothed = (
            self.alpha * np.asarray(probs, dtype=float) + (1 - self.alpha) * self.smoothed
        )
        best = int(np.argmax(self.smoothed))

        if self.active != self.rest_index and self.smoothed[self.active] < self.release:
            self.active = self.rest_index

        if best != self.rest_index and self.smoothed[best] >= self.threshold:
            self._count = self._count + 1 if best == self._candidate else 1
            self._candidate = best
            if self._count >= self.dwell:
                self.active = best
        else:
            self._candidate = self.rest_index
            self._count = 0
        return self.active
