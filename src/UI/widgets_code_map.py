from PyQt6.QtCore import Qt, QPointF, QRegularExpression, QTimer
from PyQt6.QtGui import QColor, QBrush, QPen, QFont, QPainter, QPainterPath, QSyntaxHighlighter, QTextCharFormat
from PyQt6.QtWidgets import QGraphicsView, QGraphicsRectItem, QGraphicsSimpleTextItem, QGraphicsPathItem, QGraphicsItem

class CSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        
        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#FF79C6")) # pink
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "char", "class", "const", "double", "enum", "float", "int", "long",
            "short", "signed", "struct", "union", "unsigned", "void", "volatile",
            "if", "else", "for", "while", "do", "switch", "case", "default",
            "break", "continue", "return", "typedef", "extern", "static"
        ]
        for word in keywords:
            pattern = QRegularExpression(f"\\b{word}\\b")
            self.highlighting_rules.append((pattern, keyword_format))
            
        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6272A4")) # grey-blue
        self.highlighting_rules.append((QRegularExpression("//[^\n]*"), comment_format))
        self.highlighting_rules.append((QRegularExpression("/\\*.*?\\*/"), comment_format))
        
        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#F1FA8C")) # yellow
        self.highlighting_rules.append((QRegularExpression("\".*?\""), string_format))
        
        # Preprocessor directives
        preproc_format = QTextCharFormat()
        preproc_format.setForeground(QColor("#FF5555")) # red
        self.highlighting_rules.append((QRegularExpression("#[^\n]*"), preproc_format))
        
    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            expression = QRegularExpression(pattern)
            iterator = expression.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)


class GraphView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor("#1E1A29"))
        # Optimized viewport update mode to prevent CPU lag on complex graph renders
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        
    def wheelEvent(self, event):
        zoom_factor = 1.15
        if event.angleDelta().y() < 0:
            zoom_factor = 1.0 / zoom_factor
        self.scale(zoom_factor, zoom_factor)


class NodeItem(QGraphicsRectItem):
    def __init__(self, x, y, width, height, label, node_type, controller):
        super().__init__(-width/2, -height/2, width, height)
        self.setPos(x, y)
        self.label = label
        self.node_type = node_type
        self.controller = controller
        self.setAcceptHoverEvents(True)
        
        # Use device coordinate caching to prevent redundant paint calls during panning
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        
        # Colors
        if node_type == "center":
            self.bg_color = QColor("#1E293B")
            self.border_color = QColor("#00F2FE")
            self.border_width = 3.0
            self.text_color = QColor("#FFFFFF")
        elif node_type == "caller":
            self.bg_color = QColor("#0F172A")
            self.border_color = QColor("#0072FF")
            self.border_width = 1.5
            self.text_color = QColor("#CBD5E1")
        else: # callee
            self.bg_color = QColor("#0F172A")
            self.border_color = QColor("#D383FC")
            self.border_width = 1.5
            self.text_color = QColor("#CBD5E1")
            
        self.setBrush(QBrush(self.bg_color))
        self.setPen(QPen(self.border_color, self.border_width))
        
        # Text
        self.text_item = QGraphicsSimpleTextItem(label, self)
        font = QFont("Outfit", 9)
        if node_type == "center":
            font.setBold(True)
        self.text_item.setFont(font)
        self.text_item.setBrush(QBrush(self.text_color))
        
        # Center the text inside the rectangle bounding box
        text_rect = self.text_item.boundingRect()
        self.text_item.setPos(-text_rect.width()/2, -text_rect.height()/2)
        self.setToolTip(f"Double-click to center on {label}")

    def mouseDoubleClickEvent(self, event):
        # focus_function() rebuilds the scene via scene.clear(), which deletes THIS
        # node while its event is still on the call stack — calling it inline (and
        # then super()) is a use-after-free that crashes when navigating to a
        # caller/callee node. Capture the target into locals (so the deferred call
        # never touches the soon-to-be-deleted node) and run it after the event
        # unwinds via a 0ms timer.
        ctrl = self.controller
        label = self.label
        if ctrl:
            QTimer.singleShot(0, lambda: ctrl.focus_function(label))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, start_pos, end_pos, color):
        super().__init__()
        
        # Device coordinate caching for optimized panning
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        
        path = QPainterPath()
        path.moveTo(start_pos)
        
        dx = end_pos.x() - start_pos.x()
        control1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
        control2 = QPointF(end_pos.x() - dx * 0.5, end_pos.y())
        path.cubicTo(control1, control2, end_pos)
        
        # Arrowhead pointing right
        path.moveTo(end_pos.x(), end_pos.y())
        path.lineTo(end_pos.x() - 8, end_pos.y() - 4)
        path.moveTo(end_pos.x(), end_pos.y())
        path.lineTo(end_pos.x() - 8, end_pos.y() + 4)
        
        self.setPath(path)
        pen = QPen(color, 1.5)
        self.setPen(pen)
