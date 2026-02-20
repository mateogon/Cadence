QSS = """
QWidget {
  background: #1f232a;
  color: #e6ebf2;
  font-size: 13px;
}

QWidget#RootWindow {
  background: transparent;
}

QFrame#WindowShell {
  background: #242a33;
  border: 1px solid #323c49;
  border-radius: 10px;
}

QLabel {
  background: transparent;
}

QCheckBox {
  background: transparent;
}

QFrame#Sidebar, QFrame#MainArea, QFrame#Footer {
  background: #242a33;
}

QWidget#LibraryPageRoot, QWidget#PlayerPageRoot, QWidget#PlayerContentRoot {
  background: #242a33;
}

QStackedWidget#MainViewStack {
  background: #242a33;
  border-bottom-left-radius: 10px;
  border-bottom-right-radius: 10px;
}

QFrame#BottomCornerCap {
  background: #242a33;
  border: 1px solid #323c49;
  border-top: none;
  border-bottom-left-radius: 10px;
  border-bottom-right-radius: 10px;
}

QFrame#BottomCapDivider {
  background: #3f4a5a;
  border: none;
}

QFrame#WindowTitleBar {
  background: #1b2430;
  border-bottom: 1px solid #323c49;
  border-top-left-radius: 10px;
  border-top-right-radius: 10px;
}

QFrame#Footer {
  border-bottom-left-radius: 10px;
  border-bottom-right-radius: 10px;
}

QLabel#WindowTitleLabel {
  color: #d7dee8;
  font-size: 14px;
  font-weight: 600;
  padding-bottom: 2px;
}

QPushButton#TitleBarButton, QPushButton#TitleBarMaxButton {
  color: #d7dee8;
  border: none;
  background: transparent;
  border-radius: 0px;
  min-width: 36px;
  max-width: 36px;
  min-height: 36px;
  max-height: 36px;
  padding: 0;
  font-size: 13px;
}

QPushButton#TitleBarButton:hover, QPushButton#TitleBarMaxButton:hover {
  background: rgba(215, 222, 232, 0.14);
}

QPushButton#TitleBarMaxButton {
  font-size: 20px;
  font-weight: 400;
  padding-bottom: 6px;
}

QPushButton#TitleBarCloseButton {
  color: #d7dee8;
  border: none;
  background: transparent;
  border-radius: 0px;
  border-top-right-radius: 10px;
  min-width: 40px;
  max-width: 40px;
  min-height: 36px;
  max-height: 36px;
  padding: 0;
  font-size: 20px;
  font-weight: 600;
}

QPushButton#TitleBarCloseButton:hover {
  background: #d9534f;
  color: #ffffff;
  border-top-right-radius: 10px;
}

QFrame#ControlsCard, QFrame#LogCard, QFrame#ListShell {
  background: #2b323d;
  border: 1px solid #3f4a5a;
  border-radius: 10px;
}

QFrame#BrandCard {
  background: #2b323d;
  border: 1px solid #3f4a5a;
  border-left: 4px solid #2CC985;
  border-radius: 10px;
}

QLabel#BrandTitle {
  font-size: 32px;
  font-weight: 700;
  color: #d7dee8;
}

QLabel#SectionLabel {
  color: #aeb7c3;
  font-size: 12px;
  font-weight: 600;
}

QLabel#MainTitle {
  font-size: 22px;
  font-weight: 600;
}

QLineEdit, QComboBox, QPlainTextEdit {
  background: #2b323d;
  border: 1px solid #3f4a5a;
  border-radius: 8px;
  padding: 6px;
}

QComboBox {
  padding-right: 26px;
}

QComboBox:hover {
  background: #343d4a;
}

QComboBox::drop-down {
  subcontrol-origin: padding;
  subcontrol-position: top right;
  width: 22px;
  border-left: 1px solid #3f4a5a;
  border-top-right-radius: 8px;
  border-bottom-right-radius: 8px;
  background: #343d4a;
}

QComboBox::drop-down:hover {
  background: #3c4656;
}

QComboBox::down-arrow {
  image: url(qt/assets/chevron_down_white.svg);
  width: 10px;
  height: 6px;
  margin-right: 7px;
  margin-left: 2px;
}

QComboBox::down-arrow:on {
  top: 0px;
  left: 0px;
}

QComboBox QAbstractItemView {
  background: #242a33;
  border: 1px solid #3f4a5a;
  selection-background-color: #343d4a;
  selection-color: #e6ebf2;
  outline: 0;
}

QPushButton {
  background: #2b323d;
  border: 1px solid #3f4a5a;
  border-radius: 8px;
  padding: 6px 10px;
  font-weight: 600;
}

QPushButton:hover {
  background: #343d4a;
}

QPushButton#ImportButton {
  background: #2CC985;
  color: #0e1612;
  border: 1px solid #2CC985;
  font-weight: 600;
}

QPushButton#ImportButton:hover {
  background: #229966;
}

QPushButton#ContinueButton {
  background: #8b6c2d;
  border: 1px solid #8b6c2d;
  color: #f2ead6;
}

QPushButton#ContinueButton:hover {
  background: #7a5e28;
}

QPushButton#ReadButton {
  background: #2CC985;
  border: 1px solid #2CC985;
  color: #0e1612;
  font-weight: 600;
}

QPushButton#ReadButton:hover {
  background: #229966;
}

QProgressBar {
  border: 1px solid #3f4a5a;
  border-radius: 8px;
  background: #2b323d;
  text-align: center;
  outline: none;
}

QProgressBar::chunk {
  background-color: #2CC985;
  border-radius: 7px;
}

QSlider::groove:horizontal {
  height: 8px;
  background: #242a33;
  border: none;
  border-radius: 5px;
}

QSlider:focus {
  outline: none;
}

QSlider {
  background: transparent;
  border: none;
}

QSlider::sub-page:horizontal {
  background: #2CC985;
  border: none;
  border-radius: 5px;
}

QSlider::add-page:horizontal {
  background: #242a33;
  border: none;
  border-radius: 5px;
}

QSlider::handle:horizontal {
  background: #d7dde8;
  border: 1px solid #7a8799;
  width: 16px;
  margin: -5px 0;
  border-radius: 8px;
}

QSlider::handle:horizontal:hover {
  background: #ffffff;
}

QScrollArea {
  border: none;
  background: #2b323d;
}

QScrollArea > QWidget > QWidget {
  background: #2b323d;
}

QFrame#BookCard {
  border: 1px solid #3f4a5a;
  border-radius: 10px;
  background: #2b323d;
}

QFrame#BookCard:hover {
  background: #343d4a;
}

QLabel#BookTitle {
  font-size: 16px;
  font-weight: 600;
}

QLabel#BookMeta {
  color: #aeb7c3;
}

QLabel#BookStatusComplete {
  color: #5ac18e;
  font-weight: 600;
}

QLabel#BookStatusIncomplete {
  color: #f0b34a;
  font-weight: 600;
}

QFrame#BookCardShell {
  border: none;
  background: transparent;
}

QFrame#BookCardShell > QWidget {
  border: 1px solid #3f4a5a;
  border-radius: 10px;
  background: #2b323d;
}

QFrame#PlayerPanel {
  background: #2b323d;
  border: 1px solid #3f4a5a;
  border-radius: 12px;
}

QListWidget {
  background: transparent;
  border: none;
  border-radius: 10px;
  outline: none;
}

QListWidget::item {
  padding: 6px 8px;
  border-radius: 8px;
}

QListWidget::item:hover {
  background: #3a4453;
}

QListWidget::item:selected {
  background: #343d4a;
  color: #e6ebf2;
}

QListWidget::item:selected:active,
QListWidget::item:selected:!active {
  background: #343d4a;
  color: #e6ebf2;
}

QScrollBar:vertical {
  background: #242a33;
  width: 12px;
  margin: 2px;
  border: none;
}

QScrollBar::handle:vertical {
  background: #4a5668;
  min-height: 30px;
  border-radius: 6px;
}

QScrollBar::handle:vertical:hover {
  background: #5a6880;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::up-arrow:vertical,
QScrollBar::down-arrow:vertical {
  height: 0px;
  background: transparent;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
  background: transparent;
}

QScrollBar:horizontal {
  background: #242a33;
  height: 12px;
  margin: 2px;
  border: none;
}

QScrollBar::handle:horizontal {
  background: #4a5668;
  min-width: 30px;
  border-radius: 6px;
}

QScrollBar::handle:horizontal:hover {
  background: #5a6880;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::left-arrow:horizontal,
QScrollBar::right-arrow:horizontal {
  width: 0px;
  background: transparent;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
  background: transparent;
}
"""
