"""Settings for reading beats from photos: provider, model and API keys."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..ai import keys
from ..ai.providers import PROVIDERS, TranscriptionError, friendly_message, provider_says
from ..settings import Settings
from . import theme
from .worker import run_in_background

PRIVACY = (
    "When you read a photo, only the cropped image is sent to the provider you choose, "
    "using your own API key. Nothing is sent until you press Read notes. "
    "Keys are kept in your computer's secure password store, never in a file."
)


def chosen_model(settings: Settings, provider: str) -> str:
    models = PROVIDERS[provider].models
    model = settings.ai_models.get(provider, models[0])
    return model or models[0]


class AISettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings: reading beats from photos")
        self.setMinimumWidth(520)
        self._settings = settings
        self._job = None

        column = QVBoxLayout(self)
        column.setSpacing(14)
        heading = QLabel("Reading beats from photos")
        heading.setObjectName("sectionHeading")
        column.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)
        self._provider = QComboBox()
        for name, cls in PROVIDERS.items():
            self._provider.addItem(cls.label, name)
        self._provider.setCurrentIndex(max(0, self._provider.findData(settings.ai_provider)))
        self._provider.currentIndexChanged.connect(self._load_provider)
        form.addRow("AI provider", self._provider)

        self._model = QComboBox()
        self._model.setEditable(True)  # a newer model name can be typed in
        self._model.currentTextChanged.connect(self._on_model)
        form.addRow("Model", self._model)

        key_row = QHBoxLayout()
        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.Password)
        self._key.setPlaceholderText("Paste your API key")
        save = QPushButton("Save key")
        save.clicked.connect(self._save_key)
        key_row.addWidget(self._key, 1)
        key_row.addWidget(save)
        form.addRow("API key", key_row)

        buttons = QHBoxLayout()
        self._test = QPushButton("Test key")
        self._test.clicked.connect(self._test_key)
        self._remove = QPushButton("Remove key")
        self._remove.setObjectName("danger")
        self._remove.clicked.connect(self._remove_key)
        buttons.addWidget(self._test)
        buttons.addWidget(self._remove)
        buttons.addStretch()
        form.addRow("", buttons)
        column.addLayout(form)

        self._status = QLabel()
        self._status.setWordWrap(True)
        column.addWidget(self._status)

        privacy = QLabel(PRIVACY)
        privacy.setObjectName("meta")
        privacy.setWordWrap(True)
        column.addWidget(privacy)

        close = QPushButton("Done")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        column.addLayout(row)

        self._load_provider()

    def _provider_name(self) -> str:
        return self._provider.currentData()

    def _load_provider(self) -> None:
        name = self._provider_name()
        self._settings.ai_provider = name
        self._settings.save()
        self._model.blockSignals(True)
        self._model.clear()
        self._model.addItems(PROVIDERS[name].models)
        self._model.setCurrentText(chosen_model(self._settings, name))
        self._model.blockSignals(False)
        self._key.clear()
        self._show_key_state()

    def _on_model(self, text: str) -> None:
        if text.strip():
            self._settings.ai_models[self._provider_name()] = text.strip()
            self._settings.save()

    def _show_key_state(self) -> None:
        stored = keys.has_key(self._provider_name())
        self._remove.setEnabled(stored)
        self._test.setEnabled(stored)
        label = PROVIDERS[self._provider_name()].label
        self._say("A key is saved for " + label + "." if stored else "No key saved for " + label + " yet.", theme.TEXT_DIM)

    def _save_key(self) -> None:
        key = self._key.text().strip()
        if not key:
            self._say("Paste a key first.", theme.BAD)
            return
        keys.set_key(self._provider_name(), key)
        self._key.clear()
        self._show_key_state()
        self._test_key()

    def _remove_key(self) -> None:
        keys.delete_key(self._provider_name())
        self._show_key_state()

    def _test_key(self) -> None:
        name = self._provider_name()
        key = keys.get_key(name)
        if not key:
            return
        provider = PROVIDERS[name]()
        self._test.setEnabled(False)
        self._say("Checking the key…", theme.TEXT_DIM)

        def done(_):
            self._test.setEnabled(True)
            self._say(f"The key works with {provider.label}.", theme.OK)

        def failed(error):
            self._test.setEnabled(True)
            if isinstance(error, TranscriptionError) and error.kind == TranscriptionError.RATE_LIMIT:
                # Checking a key only lists models (free); it doesn't use any model's quota.
                self._say(
                    f"The key is saved, but {provider.label} is limiting requests right now, so it couldn't be "
                    "checked. This doesn't use your model quota. Try Test key again in a minute."
                    + provider_says(error),
                    theme.BAD,
                )
            elif isinstance(error, TranscriptionError):
                self._say(friendly_message(error, provider.label), theme.BAD)
            else:
                self._say(f"Couldn't check the key: {error}", theme.BAD)

        self._job = run_in_background(lambda: provider.check_key(key), done, failed)

    def _say(self, text: str, color: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color};")
        self._status.setTextFormat(Qt.PlainText)
