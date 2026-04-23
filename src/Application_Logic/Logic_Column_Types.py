from PyQt6 import QtWidgets, QtCore, QtGui
import re
from fuzzywuzzy import process, fuzz
from .Logic_User_Interaction import UserInteractionLogic

class LazyComboBox(QtWidgets.QComboBox):
    def __init__(self, controller, search_func, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.search_func = search_func
        self.setEditable(True)
        self._loaded = False
        self.maxVisibleItems = 20
        self.currentTextChanged.connect(self._apply_score_color)
        
    def showPopup(self):
        if not self._loaded:
            self.load_items()
        super().showPopup()

    def mousePressEvent(self, e):
        if not self._loaded:
            self.load_items()
        # Ensure we call super via QComboBox to handle the event
        QtWidgets.QComboBox.mousePressEvent(self, e)
        
    def keyPressEvent(self, e):
        # Trigger load on typing? 
        # Actually typing usually goes to the QLineEdit lineEdit().
        # We can hook lineEdit().textEdited?
        if not self._loaded:
             self.load_items()
        super().keyPressEvent(e)

    def load_items(self):
        text = self.currentText()
        matches = self.search_func(text)
        
        self.blockSignals(True)
        self.clear()
        for name, score in matches:
            self.addItem(f"{name} ({score}%)", name)
        
        self.setCurrentText(text)
        
        # Apply coloring based on the *current* text, which might be "FuncA (90%)" or "FuncB (50%)"
        self._apply_score_color(text)
        
        self.blockSignals(False)
        self._loaded = True

    def _apply_score_color(self, text):
        """Calculates color based on the percentage in the text."""
        match = re.search(r'\((\d+)%\)$', text)
        color = "#353535" # Default
        
        if match:
            score = int(match.group(1))
            color = "#2e8b57" if score >= 80 else "#b8860b" if score >= 60 else "#8b0000"
        
        self.setStyleSheet(f"background-color: {color}; color: white;")


class TableColumn:
    """Base class for all table column behaviors."""

    def __init__(self, name, width=100):
        self.name = name
        self.width = width
        self.user_visible = None  # None = Auto/Default, True = Force Show, False = Force Hide

    def on_change(self, table, row, col, text, controller, lazy=False):
        pass


class PortSearchColumn(TableColumn):
    """Generic Search logic that triggers a match across ALL symbols."""
    def __init__(self, name, width=250):
        super().__init__(name, width)

    def on_change(self, table, row, col, text, controller, lazy=False):
        if not text: return
        
        # Optimization: Lazy Load
        if lazy:
            self._create_lazy_widget(table, row, col + 1, controller, text)
            return

        if not controller.matcher: return
        matches = controller.matcher.find_top_matches(text, limit=10)
        self._update_dropdown(table, row, col + 1, text, controller, matches)

    def _create_lazy_widget(self, table, row, target_col, controller, text):
        if target_col >= table.columnCount():
            return
            
        def search_logic(text):
            if not controller.matcher: return []
            return controller.matcher.find_top_matches(text, limit=10)
            
        combo = LazyComboBox(controller, search_logic)
        combo.setCurrentText(text)
        
        # Re-attach signals
        combo.currentIndexChanged.connect(lambda: (
             controller.refresh_init_column_state(), 
             controller.refresh_cyclic_column_state(),
             UserInteractionLogic.reset_review_status(table, row, controller)
        ))
        
        table.setCellWidget(row, target_col, combo)

    def _update_dropdown(self, table, row, target_col, text, controller, matches):
        if target_col >= table.columnCount():
            return
        if matches:
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            for name, score in matches:
                combo.addItem(f"{name} ({score}%)", name)

            # Signal Connections
            combo.currentIndexChanged.connect(lambda: (
                controller.refresh_init_column_state(), 
                controller.refresh_cyclic_column_state(),
                UserInteractionLogic.reset_review_status(table, row, controller)
            ))

            best_score = matches[0][1]
            color = "#2e8b57" if best_score >= 80 else "#b8860b" if best_score >= 60 else "#8b0000"

            status = UserInteractionLogic.get_review_status(table, row, controller)
            if status == "Reviewed":
                color = "#2e8b57" # Dark Green
                if combo.count() > 0:
                    combo.setCurrentText(combo.itemData(0))
            elif status == "Broken Link":
                color = "#483d8b"

            combo.setStyleSheet(f"background-color: {color}; color: white;")
            combo.setStyleSheet(f"background-color: {color}; color: white;")
            table.setCellWidget(row, target_col, combo)


class FunctionSearchColumn(TableColumn):
    """Search logic restricted only to Functions."""

    def __init__(self, name, width=250):
        super().__init__(name, width)

    def on_change(self, table, row, col, text, controller, lazy=False):
        if not text: return
        
        if lazy:
             if col + 1 < table.columnCount():
                 def search_logic(text):
                     if not controller.matcher: return []
                     return process.extractBests(text, controller.matcher.all_function_names,
                                            scorer=fuzz.token_sort_ratio, limit=10)
                 
                 combo = LazyComboBox(controller, search_logic)
                 combo.setCurrentText(text)
                 
                 combo.currentIndexChanged.connect(lambda: (
                    controller.refresh_init_column_state(), 
                    controller.refresh_cyclic_column_state(),
                    UserInteractionLogic.reset_review_status(table, row, controller)
                 ))
                 table.setCellWidget(row, col + 1, combo)
             return

        if not controller.matcher: return
        matches = process.extractBests(text, controller.matcher.all_function_names,
                                       scorer=fuzz.token_sort_ratio, limit=10)
        self._update_dropdown(table, row, col + 1, text, controller, matches)

    def _update_dropdown(self, table, row, target_col, text, controller, matches):
        if target_col >= table.columnCount(): return
        if matches:
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            for name, score in matches:
                combo.addItem(f"{name} ({score}%)", name)

            combo.currentIndexChanged.connect(lambda: (
                controller.refresh_init_column_state(), 
                controller.refresh_cyclic_column_state(),
                UserInteractionLogic.reset_review_status(table, row, controller)
            ))

            best_score = matches[0][1]
            color = "#2e8b57" if best_score >= 80 else "#b8860b" if best_score >= 60 else "#8b0000"

            status = UserInteractionLogic.get_review_status(table, row, controller)
            if status == "Reviewed":
                color = "#2e8b57"
                if combo.count() > 0:
                    combo.setCurrentText(combo.itemData(0))
            elif status == "Broken Link":
                color = "#483d8b"

            combo.setStyleSheet(f"background-color: {color}; color: white;")
            combo.setStyleSheet(f"background-color: {color}; color: white;")
            table.setCellWidget(row, target_col, combo)

class VariableSearchColumn(TableColumn):
    """Search logic restricted to Global Variables and Structures."""

    def __init__(self, name, width=250):
        super().__init__(name, width)

    def on_change(self, table, row, col, text, controller, lazy=False):
        if not text: return
        
        if lazy:
             if col + 1 < table.columnCount():
                 def search_logic(text):
                     if not controller.matcher: return []
                     return process.extractBests(text, controller.matcher.all_variable_names,
                                            scorer=fuzz.token_sort_ratio, limit=10)
                 
                 combo = LazyComboBox(controller, search_logic)
                 combo.setCurrentText(text)
                 
                 combo.currentIndexChanged.connect(lambda: UserInteractionLogic.reset_review_status(table, row, controller))
                 table.setCellWidget(row, col + 1, combo)
             return

        if not controller.matcher: return
        matches = process.extractBests(text, controller.matcher.all_variable_names,
                                       scorer=fuzz.token_sort_ratio, limit=10)
        self._update_dropdown(table, row, col + 1, text, controller, matches)

    def _update_dropdown(self, table, row, target_col, text, controller, matches):
        if target_col >= table.columnCount(): return
        if matches:
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            for name, score in matches:
                combo.addItem(f"{name} ({score}%)", name)
            
            combo.currentIndexChanged.connect(lambda: UserInteractionLogic.reset_review_status(table, row, controller))

            best_score = matches[0][1]
            color = "#2e8b57" if best_score >= 80 else "#b8860b" if best_score >= 60 else "#8b0000"
            
            status = UserInteractionLogic.get_review_status(table, row, controller)
            if status == "Reviewed":
                color = "#2e8b57"
                if combo.count() > 0:
                    combo.setCurrentText(combo.itemData(0))
            elif status == "Broken Link":
                color = "#483d8b"

            combo.setStyleSheet(f"background-color: {color}; color: white;")
            table.setCellWidget(row, target_col, combo)

class ReviewColumn(TableColumn):
    """
    Column for displaying the review status of a symbol.

    The Broken Link status is hidden from the dropdown it is used to mark when a
    function changes in the elf from the Reviewed one. Called by the Elf Comparison algorithm.
    """
    def __init__(self, name, width=150):
        super().__init__(name, width)
        # Darker colors for better contrast with white text
        self.status_map = {
            "Not Reviewed" : "#8b0000", # Dark Red
            "In Review" : "#b8860b", # Dark Goldenrod (Yellow-ish)
            "Reviewed" : "#2e8b57", # Sea Green
            "Broken Link": "#483d8b"  # Dark Slate Blue
        }

    def on_change(self, table, row, col, text, controller, lazy=False):
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
            combo.setStyleSheet(f"background-color: {self.status_map['Not Reviewed']}; color: white;")


    def _handle_status_change(self, table, row, col, status):
        color = self.status_map.get(status, "#353535") # Default to button color
        widget = table.cellWidget(row, col)

        if widget:
            """
            If we programmatically set "Broken Link", we must add it to the combo first 
            or it won't show the text, but the color will still apply.
            """
            if status == "Broken Link" and widget.findText("Broken Link") == -1:
                widget.addItem("Broken Link")
                widget.setCurrentText("Broken Link")

            widget.setStyleSheet(f"background-color: {color}; color: white;")

        # If status "Reviewed", the search color will be overwritten (Green) to avoid confusion, and the percentage will be removed from the search
        # If status "Broken Link", the search color will be overwritten (Lavender) to avoid confusion
        for c in range(table.columnCount()):
            other_widget = table.cellWidget(row, c)
            if isinstance(other_widget, QtWidgets.QComboBox) and other_widget != widget:

                if status == "Reviewed":
                    other_widget.setStyleSheet("background-color: #2e8b57; color: white;") # Dark Green
                    # Remove match percentage
                    current_text = other_widget.currentText()
                    if " (" in current_text and current_text.endswith("%)"):
                        clean_name = current_text.rsplit(" (", 1)[0]
                        other_widget.blockSignals(True)
                        other_widget.setCurrentText(clean_name)
                        other_widget.blockSignals(False)
                
                elif status == "Broken Link":
                    other_widget.setStyleSheet(f"background-color: #483d8b; color: white;") # Dark Slate Blue
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
            # Darker colors for better contrast with white text
            color = "#2e8b57" if score >= 80 else "#b8860b" if score >= 60 else "#8b0000"
            combo.setStyleSheet(f"background-color: {color}; color: white;")
        else:
            combo.setStyleSheet("background-color: #353535; color: white;")

class InitColumn(TableColumn):
    """Column that handles the 'init' status logic."""
    def __init__(self, name, width=60):
        super().__init__(name, width)

    def on_change(self, table, row, col, text, controller, lazy=False):
        """
        Handles user interaction with the Init cell.
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
        self.default_cyclicity = "10"

    def get_expected_value(self, func_name):
        """Parses function name for 'Cyclic' (10) or 'XXms' (XX)."""
        if not func_name: return "0"
        lower = func_name.lower()
        
        # Check for XXms (e.g., 100ms, 5ms)
        match = re.search(r'(\d+)ms', lower)
        if match:
            return match.group(1)
        
        # Check for generic Cyclic tag
        if "cyclic" in lower:
            return self.default_cyclicity
            
        return "0"

    def on_change(self, table, row, col, text, controller, lazy=False):
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

        expected_val = self.get_expected_value(current_func_name)

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

class PortStateColumn(TableColumn):
    """
    Column for managing the lifecycle state of a port.
    Options: Released, In Work, Retired, Deleted.
    """
    def __init__(self, name, width=120):
        super().__init__(name, width)
        self.state_colors = {
            "Released": "#2e8b57",  # Sea Green
            "In Work": "#b8860b",   # Dark Goldenrod
            "Retired": "#808080",   # Grey
            "Deleted": "#8b0000"    # Dark Red
        }

    def on_change(self, table, row, col, text, controller, lazy=False):
        # Check if row has any content (text or widget selection)
        has_content = False
        for c in range(table.columnCount()):
            if c == col: continue
            
            # Check Item Text
            item = table.item(row, c)
            if item and item.text().strip():
                has_content = True
                break
            
            # Check Widget Text
            widget = table.cellWidget(row, c)
            if isinstance(widget, QtWidgets.QComboBox):
                if widget.currentText().strip():
                    has_content = True
                    break

        # Ensure widget exists
        current_widget = table.cellWidget(row, col)
        
        if not has_content:
            if current_widget:
                table.removeCellWidget(row, col)
            return

        if not current_widget:
            combo = QtWidgets.QComboBox()
            combo.addItems(["Released", "In Work", "Retired", "Deleted"])
            combo.setCurrentText("In Work") # Default
            
            # Connect signal
            combo.currentTextChanged.connect(lambda t, r=row, c=col: self._handle_state_change(table, r, c, t, controller))
            
            table.setCellWidget(row, col, combo)
            self._handle_state_change(table, row, col, "In Work", controller)
        else:
             # If widget exists, ensure visual state is correct (e.g. after scroll/restore)
             self._handle_state_change(table, row, col, current_widget.currentText(), controller)


    def _handle_state_change(self, table, row, col, state, controller):
        widget = table.cellWidget(row, col)
        if widget:
            color = self.state_colors.get(state, "#353535")
            widget.setStyleSheet(f"background-color: {color}; color: white;")

        # Apply Visual Effects to the Row
        self._apply_row_visuals(table, row, state, controller)
        
        # Handle "Deleted" timer logic
        if state == "Deleted":
            QtCore.QTimer.singleShot(5000, lambda: self._hide_deleted_row(table, row, controller))

    def _apply_row_visuals(self, table, row, state, controller):
        # Iterate over all items/widgets in the row
        for c in range(table.columnCount()):
            # Handle Widgets (ComboBoxes)
            widget = table.cellWidget(row, c)
            if widget:
                # Issue: If this is a ReleaseResultColumn with "No Result", we removed the widget.
                # But here we are iterating widgets. If widget exists, it's not "No Result".
                if state == "Retired":
                    widget.setEnabled(False)
                elif state == "Deleted":
                    widget.setEnabled(False)
                else:
                    widget.setEnabled(True)

            # Handle Items (Static Text, Init, Cyclic)
            item = table.item(row, c)
            if not item:
                item = QtWidgets.QTableWidgetItem()
                table.setItem(row, c, item)
            
            # Check if this column is a ReleaseResultColumn and has "No Result"
            is_no_result_static = False
            if c < len(controller.active_columns):
                col_obj = controller.active_columns[c]
                if isinstance(col_obj, ReleaseResultColumn):
                     if item.text() == "No Result":
                         is_no_result_static = True

            font = item.font()
            
            if state == "Retired":
                # Don't override "No Result" white text with grey
                if not is_no_result_static:
                    item.setForeground(QtGui.QColor("grey"))
                font.setStrikeOut(False)
            elif state == "Deleted":
                # Deleted should probably still be red? "No Result" in red?
                # User complaint was about "No Result" matching background.
                # If Deleted, background is default? No result background is Grey.
                # Red on Grey is visible. Grey on Grey is not.
                item.setForeground(QtGui.QColor("red"))
                font.setStrikeOut(True)
            else:
                # Restore default
                # If No Result, restore to White (handled by ReleaseResult logic, but safe to force here?)
                if is_no_result_static:
                     item.setForeground(QtGui.QColor("white"))
                else:
                     item.setForeground(QtGui.QColor("white")) # Assuming dark theme
                font.setStrikeOut(False)
            
            item.setFont(font)

    def _hide_deleted_row(self, table, row, controller):
        # Check if state is still Deleted (user might have changed it back quickly)
        # We need to find the Port State column index again as it might have moved? 
        # Actually, we have 'col' from closure but let's be safe.
        # However, 'row' index might shift if other rows are deleted. 
        # This is tricky with QTableWidget row indices.
        # A safer way is to check the item at the specific cell if we can track it.
        # For now, we will re-check the widget at the row.
        
        # Note: If rows are inserted/removed, 'row' index becomes stale.
        # A robust solution requires persistent row objects or searching.
        # Given the constraints, we will check if the row still exists and has "Deleted" state.
        
        if row < table.rowCount():
            # Find the Port State column index dynamically
            state_col_idx = -1
            for i, col_obj in enumerate(controller.active_columns):
                if isinstance(col_obj, PortStateColumn):
                    state_col_idx = i
                    break
            
            if state_col_idx != -1:
                widget = table.cellWidget(row, state_col_idx)
                if widget and widget.currentText() == "Deleted":
                    table.setRowHidden(row, True)

class LastResultColumn(TableColumn):
    """
    Column for displaying the consolidated result from the latest release.
    Read-only, updated automatically.
    """
    def __init__(self, name, width=100):
        super().__init__(name, width)
        self.state_colors = {
            "Passed": "#2e8b57",   # Sea Green
            "Failed": "#8b0000",   # Dark Red
            "Block": "#b8860b",    # Dark Goldenrod
            "Block": "#b8860b",    # Dark Goldenrod
            "Not Run": "#4a90e2",  # Blue
            "No Result": "#808080" # Grey
        }

    def on_change(self, table, row, col, text, controller, lazy=False):
        # Read-Only logic
        item = table.item(row, col)
        if not item:
            item = QtWidgets.QTableWidgetItem()
            table.setItem(row, col, item)
            
        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        
        # Apply Color
        if text in self.state_colors:
            item.setBackground(QtGui.QColor(self.state_colors[text]))
            item.setForeground(QtGui.QColor("white"))
        else:
            # Clear or Default
            item.setBackground(QtGui.QColor("#353535")) # Default background
            item.setForeground(QtGui.QColor("white"))


class ReleaseResultColumn(TableColumn):
    """
    Column for managing release-specific validation results.
    Options: Not Run, Block, Failed, Passed.
    """
    def __init__(self, name, width=120):
        super().__init__(name, width)
        self.state_colors = {
            "Passed": "#2e8b57",   # Sea Green
            "Failed": "#8b0000",   # Dark Red
            "Block": "#b8860b",    # Dark Goldenrod
            "Not Run": "#4a90e2",  # Blue
            "No Result": "#808080" # Grey
        }
        self.is_initialized = False # Req 8: Track initialization status

    def on_change(self, table, row, col, text, controller, lazy=False):
        # Determine if row has content
        has_content = False
        for c in range(table.columnCount()):
            if c == col: continue
            item = table.item(row, c)
            if item and item.text().strip():
                has_content = True
                break
            widget = table.cellWidget(row, c)
            if isinstance(widget, QtWidgets.QComboBox) and widget.currentText().strip():
                has_content = True
                break

        current_widget = table.cellWidget(row, col)
        
        # 1. Handle Empty Rows -> Clean up
        if not has_content:
            if current_widget:
                table.removeCellWidget(row, col)
            return

        # 2. Logic Initialization / Default
        if not text:
            text = "No Result"

        # 3. Handle "No Result" as Static Text (No Widget)
        if text == "No Result":
            # Remove existing widget if any
            if current_widget:
                table.removeCellWidget(row, col)
            
            # Configure Item
            item = table.item(row, col)
            if not item:
                item = QtWidgets.QTableWidgetItem()
                table.setItem(row, col, item)
            
            item.setText("No Result")
            item.setBackground(QtGui.QColor(self.state_colors["No Result"]))
            item.setForeground(QtGui.QColor("white"))
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            # Make Read-Only
            item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            
            # Trigger Last Result Update (No Result usually ignores, but consistent)
            self._update_last_result(table, row, controller)
            return

        # 4. Handle Active States (Not Run, Block, Failed, Passed) -> Widget
        # Ensure Item is editable/normal so widget works properly
        item = table.item(row, col)
        if not item:
            item = QtWidgets.QTableWidgetItem()
            table.setItem(row, col, item)
        item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable)
        item.setText("") # Clear text behind widget

        if not current_widget or not isinstance(current_widget, QtWidgets.QComboBox):
            combo = QtWidgets.QComboBox()
            # "No Result" is NOT in the list, so user cannot select it
            combo.addItems(["Not Run", "Block", "Failed", "Passed"])
            
            # Connect
            combo.currentTextChanged.connect(lambda t, r=row, c=col: self._handle_state_change(table, r, c, t, controller))
            
            table.setCellWidget(row, col, combo)
            
            # Set Value
            index = combo.findText(text)
            if index != -1:
                combo.setCurrentIndex(index)
            else:
                # Fallback? Should probably default to Not Run or Block?
                if text in ["Not Run", "Block", "Failed", "Passed"]:
                     combo.setCurrentText(text)
                else:
                     combo.setCurrentText("Not Run")

            # Force color update
            self._handle_state_change(table, row, col, combo.currentText(), controller)
        else:
             if current_widget.currentText() != text:
                 current_widget.blockSignals(True)
                 index = current_widget.findText(text)
                 if index != -1:
                     current_widget.setCurrentIndex(index)
                 current_widget.blockSignals(False)
                 self._handle_state_change(table, row, col, text, controller)

    def _handle_state_change(self, table, row, col, state, controller):
        widget = table.cellWidget(row, col)
        if widget:
            color = self.state_colors.get(state, "#353535")
            widget.setStyleSheet(f"background-color: {color}; color: white;")
        
        self._update_last_result(table, row, controller)

    def _update_last_result(self, table, row, controller):
        """Updates the Last Result column based on all release columns."""
        last_res_idx = -1
        for i, col_obj in enumerate(controller.active_columns):
            if isinstance(col_obj, LastResultColumn):
                last_res_idx = i
                break
        
        if last_res_idx != -1:
            latest_status = "Not Run"
            found_any = False
            
            for c in range(table.columnCount()):
                if c < len(controller.active_columns):
                    col_def = controller.active_columns[c]
                    if isinstance(col_def, ReleaseResultColumn):
                        # Check Widget
                        w = table.cellWidget(row, c)
                        if w and isinstance(w, QtWidgets.QComboBox):
                            latest_status = w.currentText()
                            found_any = True
                        else:
                            # Check Item (for No Result)
                            it = table.item(row, c)
                            if it and it.text() == "No Result":
                                # If validation has "No Result", does it affect Last Result?
                                # Usually we ignore it or take the last valid one?
                                # User spec says: "No Result"
                                # Let's assume No Result overrides? Or is ignored?
                                # Current logic was overwriting latest_status.
                                # If we encounter a "No Result", should we treat it as valid status?
                                # If all are No Result -> No Result.
                                # If mixed -> probably last non-NoResult?
                                pass

            if found_any:
                item = table.item(row, last_res_idx)
                if not item:
                    item = QtWidgets.QTableWidgetItem()
                    table.setItem(row, last_res_idx, item)
                item.setText(latest_status)
                controller.active_columns[last_res_idx].on_change(table, row, last_res_idx, latest_status, controller)