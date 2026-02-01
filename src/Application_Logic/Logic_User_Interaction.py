from PyQt6 import QtWidgets, QtCore, QtGui

class UserInteractionLogic:
    """
    Handles logic for user interactions, specifically change tracking and highlighting.
    """
    USER_CHANGE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
    LAST_FUNC_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2  # Stores the last function name
    IS_PURPLE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 3  # Tracks if the cell is purple
    PURPLE_COLOR_HEX = "#E6E6FA"
    PURPLE_STYLE = f"background-color: {PURPLE_COLOR_HEX};"
    PURPLE_BRUSH = QtGui.QBrush(QtGui.QColor(PURPLE_COLOR_HEX))
    TRANSPARENT_BRUSH = QtGui.QBrush(QtCore.Qt.GlobalColor.transparent)

    @staticmethod
    def mark_manual_override(item: QtWidgets.QTableWidgetItem):
        """
        User manually changed value.
        Set Flag = True, Color = Transparent, Font = Bold.
        """
        if not item: return
        item.setData(UserInteractionLogic.USER_CHANGE_ROLE, True)
        item.setBackground(UserInteractionLogic.TRANSPARENT_BRUSH)
        
        # Issue 2.1: Mark with BOLD
        font = item.font()
        font.setBold(True)
        item.setFont(font)

    @staticmethod
    def mark_conflict(item: QtWidgets.QTableWidgetItem):
        """
        External context (Function) changed while override exists.
        Keep Flag = True, Set Color = Purple (Warning).
        """
        if not item: return
        # Ensure flag is there
        item.setData(UserInteractionLogic.USER_CHANGE_ROLE, True)
        item.setBackground(UserInteractionLogic.PURPLE_BRUSH)
        
        # Conflict implies override exists, so ensure Bold
        font = item.font()
        font.setBold(True)
        item.setFont(font)

    @staticmethod
    def clear_manual_override(item: QtWidgets.QTableWidgetItem):
        """
        User deleted value/reset.
        Clear Flag, Clear Color, Reset Font.
        """
        if not item: return
        item.setData(UserInteractionLogic.USER_CHANGE_ROLE, None)
        item.setBackground(UserInteractionLogic.TRANSPARENT_BRUSH)
        
        # Reset to normal font
        font = item.font()
        font.setBold(False)
        item.setFont(font)

    @staticmethod
    def is_item_user_changed(item: QtWidgets.QTableWidgetItem) -> bool:
        """Checks if the item has been modified by the user."""
        if not item: return False
        return item.data(UserInteractionLogic.USER_CHANGE_ROLE) is True

    @staticmethod
    def get_review_status(table, row, controller):
        """Helper to find the review status text for a given row."""
        review_col_idx = controller.get_column_index_by_type("ReviewColumn")
        if review_col_idx != -1:
            widget = table.cellWidget(row, review_col_idx)
            if isinstance(widget, QtWidgets.QComboBox):
                return widget.currentText()
        return None

    @staticmethod
    def reset_review_status(table, row, controller):
        """Resets the review status to 'Not Reviewed' if it isn't already."""
        review_col_idx = controller.get_column_index_by_type("ReviewColumn")
        if review_col_idx != -1:
            widget = table.cellWidget(row, review_col_idx)
            if isinstance(widget, QtWidgets.QComboBox):
                if widget.currentText() != "Not Reviewed":
                    widget.setCurrentText("Not Reviewed")

    # --- New methods for Init column logic ---

    @staticmethod
    def set_last_function(item: QtWidgets.QTableWidgetItem, func_name: str):
        """Stores the function name associated with the current init state."""
        if item:
            item.setData(UserInteractionLogic.LAST_FUNC_ROLE, func_name)

    @staticmethod
    def get_last_function(item: QtWidgets.QTableWidgetItem) -> str | None:
        """Gets the last stored function name."""
        if not item: return None
        return item.data(UserInteractionLogic.LAST_FUNC_ROLE)

    @staticmethod
    def mark_purple(item: QtWidgets.QTableWidgetItem):
        """Marks the item as purple (conflict)."""
        if not item: return
        item.setData(UserInteractionLogic.IS_PURPLE_ROLE, True)
        item.setBackground(UserInteractionLogic.PURPLE_BRUSH)

    @staticmethod
    def clear_purple(item: QtWidgets.QTableWidgetItem):
        """Clears the purple status and background."""
        if not item: return
        item.setData(UserInteractionLogic.IS_PURPLE_ROLE, False)
        item.setBackground(UserInteractionLogic.TRANSPARENT_BRUSH)

    @staticmethod
    def is_purple(item: QtWidgets.QTableWidgetItem) -> bool:
        """Checks if the item is currently marked as purple."""
        if not item: return False
        return item.data(UserInteractionLogic.IS_PURPLE_ROLE) is True