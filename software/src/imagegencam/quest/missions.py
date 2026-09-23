"""Stable mission IDs: the original three keep their existing saved IDs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Mission:
    title: str
    symbol: str
    hint: str


MISSIONS = (
    Mission("Something yellow", "sun", "Look together for yellow"),
    Mission("Something round", "circle", "Can you spot a circle?"),
    Mission("Funny family pose", "family", "Make a silly pose together"),
    Mission("A leaf", "leaf", "Look without picking it"),
    Mission("A cloud", "cloud", "What shape can you see?"),
    Mission("A shadow", "shadow", "Try your own shadow"),
    Mission("A reflection", "reflection", "Find a mirror with family"),
    Mission("Matching colors", "colors", "Spot two matching colors"),
    Mission("Something tiny", "tiny", "Look closely together"),
    Mission("Something on wheels", "wheels", "Look from a safe place"),
    Mission("A favorite snack", "snack", "Which snack do you like?"),
    Mission("A favorite place", "place", "Choose a spot with family"),
)
