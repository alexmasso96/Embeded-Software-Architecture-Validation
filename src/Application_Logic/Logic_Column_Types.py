from PyQt6 import QtWidgets, QtCore, QtGui
import re
from fuzzywuzzy import process, fuzz
from .Logic_User_Interaction import UserInteractionLogic

class TableColumn:
    """Base class for all table column behaviors."""

    def __init__(self, name, width=100):
        self.name = name
        self.width = width
        self.user_visible = None  # None = Auto/Default, True = Force Show, False = Force Hide

    def on_change(self, table, row, col, text, controller):
        pass


class PortSearchColumn(TableColumn):
    """Generic Search logic that triggers a match across ALL symbols."""
    def __init__(self, name, width=250):
        super().__init__(name, width)

    def on_change(self, table, row, col, text, controller):
        if not text or not controller.matcher: return
        matches = controller.matcher.find_top_matches(text, limit=10)
        self._update_dropdown(table, row, col + 1, text, controller, matches)

    def _update_dropdown(self, table, row, target_col, text, controller, matches):
        # Ensure the table has enough columns if this is a paired type
        if target_col >= table.columnCount():
            return
        # This helper applies the UI results to the cell
        if matches:
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            for name, score in matches:
                combo.addItem(f"{name} ({score}%)", name)

            # Connect to selection changes to trigger Init column logic
            combo.currentIndexChanged.connect(lambda: (
                controller.refresh_init_column_state(), 
                controller.refresh_cyclic_column_state(),
                UserInteractionLogic.reset_review_status(table, row, controller)
            ))

            best_score = matches[0][1]
            color = "#ccffcc" if best_score >= 80 else "#ffffcc" if best_score >= 60 else "#ffcccc"

            # Check Review Status for Purple highlight override
            status = UserInteractionLogic.get_review_status(table, row, controller)
            if status == "Reviewed":
                color = "#ccffcc" # Green for Reviewed
                # Strip percentage text for Reviewed state
                if combo.count() > 0:
                    combo.setCurrentText(combo.itemData(0)) # Set to clean name
            elif status == "Broken Link":
                color = UserInteractionLogic.PURPLE_COLOR_HEX

            combo.setStyleSheet(f"background-color: {color};")
            table.setCellWidget(row, target_col, combo)

            # Trigger the scan immediately after creating the widget
            controller.refresh_init_column_state()
            controller.refresh_cyclic_column_state()


class FunctionSearchColumn(TableColumn):
    """Search logic restricted only to Functions."""

    def __init__(self, name, width=250):
        super().__init__(name, width)

    def on_change(self, table, row, col, text, controller):
        if not text or not controller.matcher: return
        matches = process.extractBests(text, controller.matcher.all_function_names,
                                       scorer=fuzz.token_sort_ratio, limit=10)
        self._update_dropdown(table, row, col + 1, text, controller, matches)

    def _update_dropdown(self, table, row, target_col, text, controller, matches):
        # Ensure the table has enough columns if this is a paired type
        if target_col >= table.columnCount():
            return
        # This helper applies the UI results to the cell
        if matches:
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            for name, score in matches:
                combo.addItem(f"{name} ({score}%)", name)

            # Connect to selection changes to trigger Init column logic
            combo.currentIndexChanged.connect(lambda: (
                controller.refresh_init_column_state(), 
                controller.refresh_cyclic_column_state(),
                UserInteractionLogic.reset_review_status(table, row, controller)
            ))

            best_score = matches[0][1]
            color = "#ccffcc" if best_score >= 80 else "#ffffcc" if best_score >= 60 else "#ffcccc"

            # Check Review Status for Purple highlight override
            status = UserInteractionLogic.get_review_status(table, row, controller)
            if status == "Reviewed":
                color = "#ccffcc" # Green for Reviewed
                # Strip percentage text for Reviewed state
                if combo.count() > 0:
                    combo.setCurrentText(combo.itemData(0))
            elif status == "Broken Link":
                color = UserInteractionLogic.PURPLE_COLOR_HEX

            combo.setStyleSheet(f"background-color: {color};")
            table.setCellWidget(row, target_col, combo)

            # trigger the scan immediately after creating the widget
            controller.refresh_init_column_state()
            controller.refresh_cyclic_column_state()

class VariableSearchColumn(TableColumn):
    """Search logic restricted to Global Variables and Structures."""

    def __init__(self, name, width=250):
        super().__init__(name, width)

    def on_change(self, table, row, col, text, controller):
        if not text or not controller.matcher: return
        matches = process.extractBests(text, controller.matcher.all_variable_names,
                                       scorer=fuzz.token_sort_ratio, limit=10)
        self._update_dropdown(table, row, col + 1, text, controller, matches)

    def _update_dropdown(self, table, row, target_col, text, controller, matches):
        # Ensure the table has enough columns if this is a paired type
        if target_col >= table.columnCount():
            return
        # This helper applies the UI results to the cell
        if matches:
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            for name, score in matches:
                combo.addItem(f"{name} ({score}%)", name)
            
            # Connect to selection changes
            combo.currentIndexChanged.connect(lambda: UserInteractionLogic.reset_review_status(table, row, controller))

            best_score = matches[0][1]
            color = "#ccffcc" if best_score >= 80 else "#ffffcc" if best_score >= 60 else "#ffcccc"
            
            # Check Review Status
            status = UserInteractionLogic.get_review_status(table, row, controller)
            if status == "Reviewed":
                color = "#ccffcc"
                if combo.count() > 0:
                    combo.setCurrentText(combo.itemData(0))
            elif status == "Broken Link":
                color = UserInteractionLogic.PURPLE_COLOR_HEX

            combo.setStyleSheet(f"background-color: {color};")
            table.setCellWidget(row, target_col, combo)

class ReviewColumn(TableColumn):
    """
    Column for displaying the review status of a symbol.

    The Broken Link status is hidden from the dropdown it is used to mark when a
    function changes in the elf from the Reviewed one. Called by the Elf Comparison algorithm.
    """
    def __init__(self, name, width=150):
        super().__init__(name, width)
        self.status_map = {
            "Not Reviewed" : "#ffcccc", # Red
            "In Review" : "#ffffcc", # Yellow
            "Reviewed" : "#ccffcc", # Green
            "Broken Link": "#E6E6FA"  # Lavender Purple (Hidden from dropdown)
        }

    def on_change(self, table, row, col, text, controller):
        # Determine if row has any content (text in any cell)
        has_content = False
        for c in range(table.columnCount()):
            item = table.item(row, c)
            if item and item.text().strip():
                has_content = True
                break

        current_widget = table.cellWidget(row, col)

        if not has_content:
            if current_widget:
                table.removeCellWidget(row, col)
            return

        # If we have content but no widget, create it
        if not current_widget:
            combo = QtWidgets.QComboBox()
            user_options = ["Not Reviewed", "In Review", "Reviewed"]
            combo.addItems(user_options)

            # Default to Not Reviewed
            combo.currentTextChanged.connect(lambda t, r=row, c=col: self._handle_status_change(table, r, c, t))
            table.setCellWidget(row, col, combo)
            combo.setStyleSheet(f"background-color: {self.status_map['Not Reviewed']};")

    def _handle_status_change(self, table, row, col, status):
        color = self.status_map.get(status, "#ffffff")
        widget = table.cellWidget(row, col)

        if widget:
            """
            If we programmatically set "Broken Link", we must add it to the combo first 
            or it won't show the text, but the color will still apply.
            """
            if status == "Broken Link" and widget.findText("Broken Link") == -1:
                widget.addItem("Broken Link")
                widget.setCurrentText("Broken Link")

            widget.setStyleSheet(f"background-color: {color};")

        # If status "Reviewed", the search color will be overwritten (Green) to avoid confusion, and the percentage will be removed from the search
        # If status "Broken Link", the search color will be overwritten (Lavender) to avoid confusion
        for c in range(table.columnCount()):
            other_widget = table.cellWidget(row, c)
            if isinstance(other_widget, QtWidgets.QComboBox) and other_widget != widget:
                
                if status == "Reviewed":
                    other_widget.setStyleSheet("background-color: #ccffcc;") # Green
                    # Remove match percentage
                    current_text = other_widget.currentText()
                    if " (" in current_text and current_text.endswith("%)"):
                        clean_name = current_text.rsplit(" (", 1)[0]
                        other_widget.blockSignals(True)
                        other_widget.setCurrentText(clean_name)
                        other_widget.blockSignals(False)
                
                elif status == "Broken Link":
                    other_widget.setStyleSheet(f"background-color: {UserInteractionLogic.PURPLE_COLOR_HEX};")
                    self._restore_search_widget_text(other_widget)

                else:
                    # Restore text and color based on percentage
                    self._restore_search_widget_text(other_widget)
                    self._apply_score_color(other_widget)

    def _restore_search_widget_text(self, combo):
        """Restores the full text (Name (XX%)) if it was stripped."""
        current_text = combo.currentText()
        if " (" in current_text and current_text.endswith("%)"):
            return

        for i in range(combo.count()):
            item_text = combo.itemText(i)
            if item_text.startswith(current_text + " ("):
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)
                return

    def _apply_score_color(self, combo):
        """Calculates color based on the percentage in the text."""
        text = combo.currentText()
        match = re.search(r'\((\d+)%\)$', text)
        if match:
            score = int(match.group(1))
            color = "#ccffcc" if score >= 80 else "#ffffcc" if score >= 60 else "#ffcccc"
            combo.setStyleSheet(f"background-color: {color};")
        else:
            combo.setStyleSheet("background-color: #ffffff;")

class InitColumn(TableColumn):
    """Column that handles the 'init' status logic."""
    def __init__(self, name, width=60):
        super().__init__(name, width)

    def on_change(self, table, row, col, text, controller):
        """
        Handles user interaction with the Init cell.
        Case 3: User types a new value -> mark as override.
        Case 8: User clicks a purple cell -> clear purple.
        Case 9: User clears the cell -> clear override.

        NOTE: This method should NOT call controller.refresh_init_column_state()
        to avoid recursion. The refresh is triggered by the Search columns
        when the function dropdown changes.
        """
        item = table.item(row, col)
        if not item:
            # If called during init with no item, just create one and exit.
            # The refresh_init_column_state will populate it correctly.
            item = QtWidgets.QTableWidgetItem()
            table.setItem(row, col, item)
            return # Exit early, let refresh handle the initial value

        # Case 8: If cell is purple and user interacts, clear purple.
        if UserInteractionLogic.is_purple(item):
            UserInteractionLogic.clear_purple(item)

        # Determine the expected value based on the function column
        res_idx = col - 1
        current_func_name = ""
        if res_idx >= 0:
            widget = table.cellWidget(row, res_idx)
            if isinstance(widget, QtWidgets.QComboBox):
                current_func_name = widget.currentText()

        func_is_init = "init" in current_func_name.lower()
        expected_val = "1" if func_is_init else "0"

        if not text.strip():
            # Case 9: User deleted content -> Clear override.
            UserInteractionLogic.clear_manual_override(item)

            # Issue 1: If the row below is empty (no function), keep Init empty.
            # Otherwise, auto-populate with the default.
            if not current_func_name:
                item.setText("")
            else:
                item.setText(expected_val)
        else:
            # User typed a value
            # Issue 2.2: If input matches the function logic, clear the override.
            if text.strip() == expected_val:
                UserInteractionLogic.clear_manual_override(item)
            else:
                # Issue 2.1: Value differs -> Mark as user override (Bold)
                UserInteractionLogic.mark_manual_override(item)

class CyclicColumn(TableColumn):
    """Column that handles the 'cyclic' status logic (10 or XXms)."""
    def __init__(self, name, width=60):
        super().__init__(name, width)

    @staticmethod
    def get_expected_value(func_name):
        """Parses function name for 'Cyclic' (10) or 'XXms' (XX)."""
        if not func_name: return "0"
        lower = func_name.lower()
        
        # Check for XXms (e.g., 100ms, 5ms)
        match = re.search(r'(\d+)ms', lower)
        if match:
            return match.group(1)
        
        # Check for generic Cyclic tag
        if "cyclic" in lower:
            return "10"
            
        return "0"

    def on_change(self, table, row, col, text, controller):
        item = table.item(row, col)
        if not item:
            item = QtWidgets.QTableWidgetItem()
            table.setItem(row, col, item)
            return

        # Clear purple if clicked/edited
        if UserInteractionLogic.is_purple(item):
            UserInteractionLogic.clear_purple(item)

        # Determine associated Match column (Handle case where Init column might exist)
        res_idx = col - 1
        if col > 0 and isinstance(controller.active_columns[col-1], InitColumn):
            res_idx = col - 2

        current_func_name = ""
        if res_idx >= 0:
            widget = table.cellWidget(row, res_idx)
            if isinstance(widget, QtWidgets.QComboBox):
                current_func_name = widget.currentText()

        expected_val = CyclicColumn.get_expected_value(current_func_name)

        if not text.strip():
            UserInteractionLogic.clear_manual_override(item)
            if not current_func_name:
                item.setText("")
            else:
                item.setText(expected_val)
        else:
            if text.strip() == expected_val:
                UserInteractionLogic.clear_manual_override(item)
            else:
                UserInteractionLogic.mark_manual_override(item)