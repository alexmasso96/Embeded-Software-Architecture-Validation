"""
Symbol Matcher Module
=====================
Handles fuzzy matching between architecture port names and ELF symbols.
Uses fuzzywuzzy for scoring and ranking matches.
"""

from __future__ import annotations

from typing import List, Tuple, Dict, Optional

from fuzzywuzzy import fuzz, process
import logging

from core.elf_parser import ELFParser

logger = logging.getLogger(__name__)


class SymbolMatcher:
    """
    Handles fuzzy matching between architecture port names and ELF symbols.
    """

    def __init__(self, parser: ELFParser) -> None:
        self.parser: ELFParser = parser
        # Pre-calculate a list of all searchable names for speed
        self.all_function_names: List[str] = [f.name for f in self.parser.functions]
        self.all_variable_names: List[str] = list(self.parser.global_vars_dwarf.keys())
        self.search_pool: List[str] = self.all_function_names + self.all_variable_names

    def find_best_match(self, target_name: str, threshold: int = 70) -> Tuple[Optional[str], int]:
        """
        Finds the best matching symbol for a given name.
        Returns: (matched_name, confidence_score) or (None, 0)
        """
        if not target_name or not self.search_pool:
            return None, 0

        # Using extractOne to find the single best match in the pool
        # scorer=fuzz.token_sort_ratio is usually best for embedded names (underscores)
        result = process.extractOne(target_name, self.search_pool, scorer=fuzz.token_sort_ratio)

        if result:
            matched_name, score = result
            if score >= threshold:
                return matched_name, score

        return None, 0

    def find_top_matches(self, target_name: str, limit: int = 20) -> List[Tuple[str, int]]:
        """
        Returns a list of top N matching symbols.
        Returns: List of (name, score) tuples
        """
        if not target_name or not self.search_pool:
            return []

        # extractBests returns a list of matches sorted by score
        return process.extractBests(target_name, self.search_pool,
                                    scorer=fuzz.token_sort_ratio,
                                    limit=limit)

    def get_matches_for_list(self, port_list: List[str], threshold: int = 70) -> Dict[str, Tuple[Optional[str], int]]:
        """
        Batch process a list of port names.
        """
        results = {}
        for port in port_list:
            results[port] = self.find_best_match(port, threshold)
        return results