from dataclasses import dataclass

from fastapi import Query


@dataclass
class Pagination:
    limit: int = Query(default=50, ge=1, le=100)
    offset: int = Query(default=0, ge=0)
