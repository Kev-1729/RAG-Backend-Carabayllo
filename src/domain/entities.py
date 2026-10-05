from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    text: str


@dataclass(frozen=True)
class Answer:
    text: str
