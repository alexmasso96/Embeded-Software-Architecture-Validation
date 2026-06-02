"""
Symbol Matcher Module
=====================
Handles fuzzy matching between architecture port names and ELF symbols.
Uses rapidfuzz for scoring and ranking matches.
"""

from __future__ import annotations

from typing import List, Tuple, Dict, Optional
from functools import lru_cache

from rapidfuzz import fuzz, process
import logging

from core.elf_parser import ELFParser

logger = logging.getLogger(__name__)


class SymbolMatcher:
    """
    Handles fuzzy matching between architecture port names and ELF symbols.
    Loads only symbol *names* into RAM — avoids the 7 GB spike from full objects.
    """

    def __init__(self, parser: ELFParser, db=None, elf_hash: Optional[str] = None) -> None:
        self.parser: ELFParser = parser

        if db is not None and elf_hash:
            # DB-backed path — load only name strings, not full objects
            self.all_function_names: List[str] = db.get_function_names(elf_hash)
            self.all_variable_names: List[str] = db.get_variable_names(elf_hash)
        else:
            # Legacy in-memory path
            self.all_function_names = [f.name for f in parser.functions]
            self.all_variable_names = list(parser.global_vars_dwarf.keys())

        self.search_pool: List[str] = self.all_function_names + self.all_variable_names

    def find_best_match(self, target_name: str,
                        threshold: int = 70) -> Tuple[Optional[str], int]:
        if not target_name or not self.search_pool:
            return None, 0
        return self._cached_best_match(target_name, threshold)

    @lru_cache(maxsize=512)
    def _cached_best_match(self, target_name: str,
                           threshold: int) -> Tuple[Optional[str], int]:
        result = process.extractOne(
            target_name, self.search_pool, scorer=fuzz.token_sort_ratio
        )
        if result:
            matched_name, score, _ = result
            score = int(score)
            if score >= threshold:
                return matched_name, score
        return None, 0

    def find_top_matches(self, target_name: str,
                         limit: int = 20) -> List[Tuple[str, int]]:
        if not target_name or not self.search_pool:
            return []
        return self._cached_top_matches(target_name, limit)

    @lru_cache(maxsize=512)
    def _cached_top_matches(self, target_name: str,
                            limit: int) -> List[Tuple[str, int]]:
        raw = process.extract(
            target_name, self.search_pool,
            scorer=fuzz.token_sort_ratio,
            limit=limit
        )
        return [(m, int(s)) for m, s, _ in raw]

    @lru_cache(maxsize=512)
    def find_top_function_matches(self, target_name: str, limit: int = 10) -> List[Tuple[str, int]]:
        if not target_name or not getattr(self, 'all_function_names', None):
            return []
        raw = process.extract(
            target_name, self.all_function_names,
            scorer=fuzz.token_sort_ratio,
            limit=limit
        )
        return [(m, int(s)) for m, s, _ in raw]

    @lru_cache(maxsize=512)
    def find_top_variable_matches(self, target_name: str, limit: int = 10) -> List[Tuple[str, int]]:
        if not target_name or not getattr(self, 'all_variable_names', None):
            return []
        raw = process.extract(
            target_name, self.all_variable_names,
            scorer=fuzz.token_sort_ratio,
            limit=limit
        )
        return [(m, int(s)) for m, s, _ in raw]

    def get_matches_for_list(self, port_list: List[str],
                             threshold: int = 70) -> Dict[str, Tuple[Optional[str], int]]:
        results = {}
        for port in port_list:
            results[port] = self.find_best_match(port, threshold)
        return results
