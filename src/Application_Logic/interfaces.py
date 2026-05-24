"""
Interfaces Module
=================
Defines Protocol classes (structural typing) for the Architecture Validator Pro project.
These protocols serve as type contracts for AI agents and static type checkers,
without requiring inheritance changes in existing classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Optional, List, Dict, Tuple, Any

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QTableWidget, QListView
    from .Logic_Symbol_Matcher import SymbolMatcher
    from .Logic_Architecture_Models import ArchitectureManager, ArchitectureListModel
    from .Logic_Release_Manager import ReleaseManager
    from .Logic_Column_Types import TableColumn


class IArchitectureController(Protocol):
    """
    Protocol defining the public interface of ArchitectureTabController.
    
    Use this type for the `controller` parameter in column types and other modules
    that need to interact with the controller without creating circular imports.
    """
    
    # --- Attributes ---
    table: QTableWidget
    active_columns: List[TableColumn]
    matcher: Optional[SymbolMatcher]
    model_manager: ArchitectureManager
    release_manager: ReleaseManager
    list_model: ArchitectureListModel
    sidebar_list: QListView
    current_default_cyclicity: str
    show_retired: bool
    show_deleted: bool
    active_config: List[Tuple[str, str, Optional[bool]]]
    
    # --- Column Queries ---
    def get_column_index_by_type(self, type_name: str) -> int:
        """Returns the column index for the given column type string, or -1 if not found."""
        ...
    
    def get_column_index_by_name(self, name: str) -> int:
        """Returns the column index for the given column name, or -1 if not found."""
        ...
    
    # --- State Refresh ---
    def refresh_init_column_state(self) -> None:
        """Recalculates all Init column values based on current function matches."""
        ...
    
    def refresh_cyclic_column_state(self) -> None:
        """Recalculates all Cyclic column values based on current function matches."""
        ...
    
    def refresh_last_result_column(self) -> None:
        """Updates Last Result column from all Release Result columns."""
        ...
    
    # --- Data Operations ---
    def get_project_data(self) -> Dict[str, Any]:
        """Returns the full project data dict (config, settings, rows)."""
        ...
    
    def flush_current_data_to_model(self) -> None:
        """Saves current table state to the active model's data cache."""
        ...
    
    def load_active_model_to_table(self) -> None:
        """Loads the active model's data from cache into the QTableWidget."""
        ...
    
    # --- Parser Integration ---
    def populate_from_parser(self, parser: Any, release_name: Optional[str] = None) -> None:
        """Updates the symbol matcher and completer lists from a parser."""
        ...
