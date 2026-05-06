from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Iterator


@dataclass(slots=True)
class QueueItem:
    title: str
    webpage_url: str
    stream_url: str | None
    requester_id: int
    duration: int
    source: str
    thumbnail: str | None = None
    uploader: str = "Unknown Artist"

    @classmethod
    def from_track(cls, track: dict, requester_id: int | None = None) -> QueueItem:
        return cls(
            title=track.get("title", "Unknown Title"),
            webpage_url=track.get("webpage_url", ""),
            stream_url=track.get("url"),
            requester_id=int(requester_id if requester_id is not None else track.get("requester_id", 0)),
            duration=int(track.get("duration") or 0),
            source=track.get("platform", "Unknown"),
            thumbnail=track.get("thumbnail"),
            uploader=track.get("uploader", "Unknown Artist"),
        )

    def to_track(self) -> dict:
        return {
            "title": self.title,
            "webpage_url": self.webpage_url,
            "url": self.stream_url,
            "requester_id": self.requester_id,
            "duration": self.duration,
            "platform": self.source,
            "thumbnail": self.thumbnail,
            "uploader": self.uploader,
        }

    def to_saved_record(self, position: int) -> dict:
        return {
            "position": position,
            "title": self.title,
            "webpage_url": self.webpage_url,
            "duration": self.duration,
            "source": self.source,
        }


class MusicQueue:
    """Deque-backed queue with capacity and small mutation helpers."""

    def __init__(self, max_size: int, items: Iterable[dict] | None = None) -> None:
        self.max_size = max_size
        self._items: Deque[dict] = deque(items or [])

    def __bool__(self) -> bool:
        return bool(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[dict]:
        return iter(self._items)

    def __getitem__(self, index: int) -> dict:
        return list(self._items)[index]

    def add(self, item: dict) -> bool:
        if len(self._items) >= self.max_size:
            return False
        self._items.append(item)
        return True

    def append(self, item: dict) -> None:
        self._items.append(item)

    def appendleft(self, item: dict) -> None:
        self._items.appendleft(item)

    def popleft(self) -> dict:
        return self._items.popleft()

    def clear(self) -> None:
        self._items.clear()

    def shuffle(self) -> None:
        items = list(self._items)
        random.shuffle(items)
        self._items = deque(items)

    def remove_at(self, index: int) -> dict:
        items = list(self._items)
        item = items.pop(index)
        self._items = deque(items)
        return item

    def move(self, source_index: int, target_index: int) -> None:
        items = list(self._items)
        item = items.pop(source_index)
        items.insert(target_index, item)
        self._items = deque(items)

    def to_saved_items(self, current: dict | None = None) -> list[QueueItem]:
        tracks = ([current] if current else []) + list(self._items)
        return [QueueItem.from_track(track) for track in tracks if track]

