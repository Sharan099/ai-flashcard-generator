import logging 
from dataclasses import dataclass, field 
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

@dataclass
class Flashcard:
    question:str
    answer:str 
    difficulty : str = "medium"
    times_reviewed :int = 0
    created_at :str = field(default_factory=lambda:datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = "manual"

    def mark_reviewed(self) -> None:
        self.times_reviewed += 1
        logger.debug("card_reviewed: %s (total: %)",self.question, self.times_reviewed)

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "difficulty": self.difficulty,
            "times_reviewed": self.times_reviewed,
            "created_at": self.created_at,
            "id": self.id,
            "source": self.source
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Flashcard":
        return cls(
        question=data["question"],
        answer=data["answer"],
        difficulty=data.get("difficulty", "medium"),
        times_reviewed=data.get("times_reviewed", 0),
        created_at=data.get("created_at", datetime.now().isoformat()),
        id=data.get("id", str(uuid.uuid4())),
        source=data.get("source", "manual")
    )
