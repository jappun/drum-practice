"""Scoring a transcription against a hand-checked answer (for comparing providers)."""

from dataclasses import dataclass

from ..model import Beat


@dataclass(frozen=True)
class Score:
    expected: int  # notes in the answer
    found: int  # right drum at the right position
    missed: int  # in the answer but not transcribed
    invented: int  # transcribed but not in the answer

    @property
    def precision(self) -> float:
        transcribed = self.found + self.invented
        return self.found / transcribed if transcribed else (1.0 if not self.expected else 0.0)

    @property
    def recall(self) -> float:
        return self.found / self.expected if self.expected else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def score(transcribed: list[Beat], answer: list[Beat]) -> Score:
    """Compare note sets groove by groove (in order). A note counts when the
    drum and exact position match; velocity isn't scored yet."""
    found = missed = invented = expected = 0
    for i in range(max(len(transcribed), len(answer))):
        got = {(n.at, n.drum) for n in transcribed[i].notes} if i < len(transcribed) else set()
        want = {(n.at, n.drum) for n in answer[i].notes} if i < len(answer) else set()
        expected += len(want)
        found += len(got & want)
        missed += len(want - got)
        invented += len(got - want)
    return Score(expected, found, missed, invented)


def total(scores: list[Score]) -> Score:
    return Score(
        sum(s.expected for s in scores),
        sum(s.found for s in scores),
        sum(s.missed for s in scores),
        sum(s.invented for s in scores),
    )
