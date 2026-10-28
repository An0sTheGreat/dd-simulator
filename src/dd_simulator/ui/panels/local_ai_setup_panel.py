"""First-run local AI setup screen."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLineEdit, QProgressBar, QSpinBox, QVBoxLayout,
)

from dd_simulator.local_ai import (
    GEMMA_4_E4B_DISPLAY_NAME,
    LocalAiConfiguration,
    QWEN3_4B,
)
from dd_simulator.ui.panels.common import DashboardPanel, semantic_label
from dd_simulator.ui.widgets.semantic_button import SemanticButton


class LocalAiSetupPanel(DashboardPanel):
    configuration_requested = Signal(str, str, str)
    cancellation_requested = Signal()
    operation_cancel_requested = Signal()

    def __init__(self, configuration: LocalAiConfiguration) -> None:
        super().__init__("localAiSetupPanel", "LOCAL AI SETUP")
        self.configuration = configuration
        self.content_layout.addWidget(semantic_label(
            "Choose how D&D Simulator should generate narration. This setup is required once "
            "and remains available from Settings.",
            text_role="secondary", word_wrap=True,
        ))
        self.content_layout.addWidget(semantic_label("BEFORE YOU START", text_role="heading"))
        self.content_layout.addWidget(semantic_label(
            "1. Choose the recommended 2.5 GB model for most systems, or connect Unsloth Studio\n"
            "   (LM Studio is also supported as a secondary option).\n"
            "2. Keep at least 5 GB of storage free and close other GPU-heavy applications.\n"
            "3. After setup, run the 3-sample evaluation in Settings before creating a campaign.",
            text_role="secondary", word_wrap=True,
        ))
        self.content_layout.addWidget(semantic_label("MODEL STORAGE", text_role="heading"))
        folder_row = QHBoxLayout()
        self.model_directory = QLineEdit(configuration.model_directory)
        self.model_directory.setObjectName("localAiModelDirectory")
        self.model_directory.setAccessibleName("Local AI model storage folder")
        folder_row.addWidget(self.model_directory, 1)
        self.browse_button = SemanticButton("Browse", role="secondary")
        self.browse_button.setObjectName("browseLocalAiModelDirectory")
        self.browse_button.clicked.connect(self._browse_directory)
        folder_row.addWidget(self.browse_button)
        self.content_layout.addLayout(folder_row)

        self.content_layout.addWidget(semantic_label(
            "Recommended: Qwen3-4B Q4_K_M (2.5 GB GGUF). This is the best starting "
            "choice for lower-memory systems. Downloads resume after cancellation.",
            text_role="secondary", word_wrap=True,
        ))
        choices = QVBoxLayout()
        self.recommended_button = SemanticButton(
            "Install Qwen3-4B Q4_K_M — Recommended", role="primary"
        )
        self.recommended_button.setObjectName("installRecommendedLocalAiButton")
        self.recommended_button.clicked.connect(
            lambda: self.configuration_requested.emit(
                f"recommended:{QWEN3_4B.key}", self.model_directory.text().strip(), ""
            )
        )
        self.large_model_button = SemanticButton(
            f"Use {GEMMA_4_E4B_DISPLAY_NAME} via Unsloth Studio — Suggested",
            role="secondary",
        )
        self.large_model_button.setObjectName("installLargeLocalAiButton")
        self.large_model_button.clicked.connect(
            lambda: self.configuration_requested.emit(
                "unsloth", self.model_directory.text().strip(), ""
            )
        )
        self.existing_button = SemanticButton("Select Existing GGUF Model", role="secondary")
        self.existing_button.setObjectName("selectExistingGgufButton")
        self.existing_button.clicked.connect(self._select_existing_model)
        self.unsloth_button = SemanticButton("Connect to Unsloth Studio", role="secondary")
        self.unsloth_button.setObjectName("connectUnslothButton")
        self.unsloth_button.clicked.connect(
            lambda: self.configuration_requested.emit(
                "unsloth", self.model_directory.text().strip(), ""
            )
        )
        self.lm_studio_button = SemanticButton(
            "Connect to LM Studio — Secondary Option", role="secondary"
        )
        self.lm_studio_button.setObjectName("connectLmStudioButton")
        self.lm_studio_button.clicked.connect(
            lambda: self.configuration_requested.emit(
                "lm_studio", self.model_directory.text().strip(), ""
            )
        )
        self.choice_buttons = (
            self.recommended_button, self.existing_button, self.unsloth_button,
            self.large_model_button, self.lm_studio_button,
        )
        unsloth_row = QHBoxLayout()
        self.unsloth_port = QSpinBox()
        self.unsloth_port.setObjectName("unslothPort")
        self.unsloth_port.setAccessibleName("Unsloth Studio port")
        self.unsloth_port.setRange(1, 65535)
        self.unsloth_port.setValue(configuration.unsloth_port)
        unsloth_row.addWidget(self.unsloth_port)
        self.api_key = QLineEdit(configuration.api_key)
        self.api_key.setObjectName("unslothApiKey")
        self.api_key.setAccessibleName("Unsloth Studio API key")
        self.api_key.setPlaceholderText("API key from Unsloth Studio (Settings -> API)")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        unsloth_row.addWidget(self.api_key, 1)
        for button in self.choice_buttons[:3]:
            choices.addWidget(button)
        choices.addLayout(unsloth_row)
        for button in self.choice_buttons[3:]:
            choices.addWidget(button)
        self.content_layout.addLayout(choices)

        self.progress = QProgressBar()
        self.progress.setObjectName("localAiSetupProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setAccessibleName("Local AI setup progress")
        self.progress.hide()
        self.content_layout.addWidget(self.progress)
        self.operation_cancel_button = SemanticButton("Cancel Current Operation", role="destructive")
        self.operation_cancel_button.setObjectName("cancelLocalAiOperationButton")
        self.operation_cancel_button.clicked.connect(self.operation_cancel_requested)
        self.operation_cancel_button.hide()
        self.content_layout.addWidget(self.operation_cancel_button)
        self.status = semantic_label(
            "Choose one option to continue.", object_name="localAiSetupStatus",
            text_role="secondary", word_wrap=True,
        )
        self.status.setAccessibleName("Local AI setup status")
        self.content_layout.addWidget(self.status)
        self.content_layout.addStretch(1)
        self.cancel_button = SemanticButton("Return to Campaign Selection", role="secondary")
        self.cancel_button.setObjectName("cancelLocalAiSetupButton")
        self.cancel_button.setVisible(configuration.setup_complete)
        self.cancel_button.clicked.connect(self.cancellation_requested)
        self.content_layout.addWidget(self.cancel_button)

    def _browse_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose Model Storage Folder", self.model_directory.text()
        )
        if selected:
            self.model_directory.setText(selected)

    def _select_existing_model(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self, "Select GGUF Model", self.model_directory.text(), "GGUF models (*.gguf)"
        )
        if selected:
            self.configuration_requested.emit(
                "llama_cpp", self.model_directory.text().strip(), selected
            )

    def set_busy(self, busy: bool, message: str, *, downloading: bool = False) -> None:
        self.model_directory.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.unsloth_port.setEnabled(not busy)
        self.api_key.setEnabled(not busy)
        for button in self.choice_buttons:
            button.setEnabled(not busy)
        self.progress.setVisible(downloading)
        self.operation_cancel_button.setVisible(busy)
        self.show_status(message)

    def show_status(self, message: str, *, error: bool = False) -> None:
        self.status.setProperty("textRole", "danger" if error else "secondary")
        self.status.setText(message)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
