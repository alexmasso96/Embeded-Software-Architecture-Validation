from fuzzywuzzy import fuzz, process
import logging

logger = logging.getLogger(__name__)


class SymbolMatcher:
    """
    Handles fuzzy matching between architecture port names and ELF symbols.
    """

    def __init__(self, parser):
        self.parser = parser
        # Pre-calculate a list of all searchable names for speed
        self.all_function_names = [f.name for f in self.parser.functions]
        self.all_variable_names = list(self.parser.global_vars_dwarf.keys())
        self.search_pool = self.all_function_names + self.all_variable_names

    def find_best_match(self, target_name, threshold=70):
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

    def find_top_matches(self, target_name, limit=20):
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

    def get_matches_for_list(self, port_list, threshold=70):
        """
        Batch process a list of port names.
        """
        results = {}
        for port in port_list:
            results[port] = self.find_best_match(port, threshold)
        return results