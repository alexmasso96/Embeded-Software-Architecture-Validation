from PyQt6 import QtWidgets, QtCore, QtGui
from fuzzywuzzy import process, fuzz

class TableColumn:
    """Base class for all table column behaviors."""

    def __init__(self, name, width=100):
        self.name = name
        self.width = width

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

            # CHANGE: Ensure selection changes trigger the init logic
            combo.currentIndexChanged.connect(lambda: controller.refresh_init_column_state())

            best_score = matches[0][1]
            color = "#ccffcc" if best_score >= 80 else "#ffffcc" if best_score >= 60 else "#ffcccc"
            combo.setStyleSheet(f"background-color: {color};")
            table.setCellWidget(row, target_col, combo)

            # Trigger the scan immediately after creating the widget
            controller.refresh_init_column_state()


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
            combo.currentIndexChanged.connect(lambda: controller.refresh_init_column_state())

            best_score = matches[0][1]
            color = "#ccffcc" if best_score >= 80 else "#ffffcc" if best_score >= 60 else "#ffcccc"
            combo.setStyleSheet(f"background-color: {color};")
            table.setCellWidget(row, target_col, combo)

            # trigger the scan immediately after creating the widget
            controller.refresh_init_column_state()

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

            best_score = matches[0][1]
            color = "#ccffcc" if best_score >= 80 else "#ffffcc" if best_score >= 60 else "#ffcccc"
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
        if status in ["Reviewed", "Broken Link"]:
            for c in range(table.columnCount()):
                other_widget = table.cellWidget(row, c)
                if isinstance(other_widget, QtWidgets.QComboBox) and other_widget != widget:
                    other_widget.setStyleSheet(f"background-color: {color};")

                    # Remove match percentage for Reviewed status
                    if status == "Reviewed":
                        current_text = other_widget.currentText()
                        # If text contains " (80%)", split it and take the first part
                        if " (" in current_text and current_text.endswith("%)"):
                            clean_name = current_text.rsplit(" (", 1)[0]
                            # We use blockSignals to avoid re-triggering logic during cleanup
                            other_widget.blockSignals(True)
                            other_widget.setCurrentText(clean_name)
                            other_widget.blockSignals(False)

class InitColumn(TableColumn):
    """Column that triggers the initial search logic when the cell is edited."""
    def __init__(self, name, width=60):
        super().__init__(name, width)
    def on_change(self, table, row, col, text, controller):
        # Values are managed by controller.refresh_init_column_state()
        pass