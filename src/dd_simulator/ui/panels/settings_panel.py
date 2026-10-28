"""In-application settings panel for Phase 4 UI preferences."""

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QVBoxLayout

from dd_simulator.lm_studio import LMStudioModelInfo, ModelEvaluation
from dd_simulator.ui.panels.common import DashboardPanel, semantic_label
from dd_simulator.ui.themes.theme_schema import ThemeDefinition
from dd_simulator.ui.widgets.semantic_button import SemanticButton


class SettingsPanel(DashboardPanel):
    theme_requested = Signal(str)
    font_size_requested = Signal(int)
    reduced_motion_requested = Signal(bool)
    reset_requested = Signal()
    back_requested = Signal()
    checkpoint_create_requested = Signal()
    checkpoint_load_requested = Signal()
    repair_requested = Signal()
    replay_requested = Signal()
    model_refresh_requested = Signal()
    model_requested = Signal(str)
    model_load_requested = Signal(str)
    model_evaluation_requested = Signal(str)
    local_ai_setup_requested = Signal()
    diagnostic_export_requested = Signal()

    def __init__(self, themes: Iterable[ThemeDefinition]) -> None:
        super().__init__("settingsPanel", "SETTINGS")
        self.content_layout.addWidget(
            semantic_label(
                "Application, model, and campaign controls.",
                text_role="secondary",
            )
        )
        self.startup_status = semantic_label(
            "Startup checks pending.",
            object_name="startupReadinessStatus",
            text_role="secondary",
            word_wrap=True,
        )
        self.startup_status.setAccessibleName("Application startup readiness")
        self.content_layout.addWidget(self.startup_status)

        self.content_layout.addWidget(
            semantic_label("LOCAL AI MODEL", text_role="heading")
        )
        self.content_layout.addWidget(
            semantic_label(
                "Review the model provided by llama.cpp or LM Studio before evaluation or play.",
                text_role="secondary",
                word_wrap=True,
            )
        )
        model_controls = QVBoxLayout()
        self.model_selector = QComboBox()
        self.model_selector.setObjectName("lmStudioModelSelector")
        self.model_selector.setAccessibleName("Local AI model")
        self.model_selector.addItem("Refresh to discover models", "")
        self.model_selector.currentIndexChanged.connect(self._model_changed)
        model_controls.addWidget(self.model_selector)
        self.model_refresh_button = SemanticButton("Refresh Models", role="secondary")
        self.model_refresh_button.setObjectName("refreshLmStudioModelsButton")
        self.model_refresh_button.clicked.connect(self.model_refresh_requested)
        self.model_load_button = SemanticButton("Load Selected Model", role="primary")
        self.model_load_button.setObjectName("loadLmStudioModelButton")
        self.model_load_button.clicked.connect(self._load_model)
        self.model_load_button.setEnabled(False)
        self.model_evaluate_button = SemanticButton("Run 3-Sample Evaluation", role="primary")
        self.model_evaluate_button.setObjectName("evaluateLmStudioModelButton")
        self.model_evaluate_button.clicked.connect(self._evaluate_model)
        self.model_evaluate_button.setEnabled(False)
        model_controls.addWidget(self.model_refresh_button)
        model_controls.addWidget(self.model_load_button)
        model_controls.addWidget(self.model_evaluate_button)
        self.content_layout.addLayout(model_controls)
        self.model_status = semantic_label(
            "The local AI provider has not been scanned in this session.",
            object_name="lmStudioModelStatus",
            text_role="muted",
            word_wrap=True,
        )
        self.model_status.setAccessibleName("Local AI model status")
        self.content_layout.addWidget(self.model_status)
        configure_local_ai = SemanticButton("Change Local AI Setup", role="secondary")
        configure_local_ai.setObjectName("changeLocalAiSetupButton")
        configure_local_ai.clicked.connect(self.local_ai_setup_requested)
        self.content_layout.addWidget(configure_local_ai)
        self.content_layout.addWidget(semantic_label(
            "Troubleshooting: load exactly one model, refresh the list, then run the "
            "3-sample evaluation. If generation still fails, reload the model and export "
            "diagnostic logs below.",
            text_role="secondary", word_wrap=True,
        ))

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

        self.theme_selector = QComboBox()
        self.theme_selector.setObjectName("settingsThemeSelector")
        self.theme_selector.setAccessibleName("Interface theme")
        for theme in themes:
            self.theme_selector.addItem(theme.name, theme.theme_id)
        self.theme_selector.currentIndexChanged.connect(self._theme_changed)
        form.addRow(semantic_label("Theme", text_role="body"), self.theme_selector)

        font_controls = QHBoxLayout()
        font_controls.setContentsMargins(0, 0, 0, 0)
        self.font_size_decrease = SemanticButton("−", role="secondary")
        self.font_size_decrease.setObjectName("decreaseFontSizeButton")
        self.font_size_decrease.setAccessibleName("Decrease interface font size")
        self.font_size_decrease.clicked.connect(lambda: self._adjust_font_size(-5))
        self.font_size_increase = SemanticButton("+", role="secondary")
        self.font_size_increase.setObjectName("increaseFontSizeButton")
        self.font_size_increase.setAccessibleName("Increase interface font size")
        self.font_size_increase.clicked.connect(lambda: self._adjust_font_size(5))
        self.font_size_value = semantic_label(
            "100%", object_name="fontSizeValue", text_role="body"
        )
        self.font_size_value.setAccessibleName("Current interface font size")
        font_controls.addWidget(self.font_size_decrease)
        font_controls.addWidget(self.font_size_increase)
        font_controls.addWidget(self.font_size_value)
        font_controls.addStretch(1)
        self._font_size_percent = 100
        form.addRow(
            semantic_label("Font size", text_role="body"),
            font_controls,
        )

        self.reduced_motion_checkbox = QCheckBox("Reduce interface motion")
        self.reduced_motion_checkbox.setObjectName("reducedMotionPreference")
        self.reduced_motion_checkbox.setAccessibleName("Reduce interface motion")
        self.reduced_motion_checkbox.setToolTip(
            "Show resource changes immediately instead of animating them"
        )
        self.reduced_motion_checkbox.toggled.connect(self.reduced_motion_requested)
        form.addRow(
            semantic_label("Motion", text_role="body"),
            self.reduced_motion_checkbox,
        )

        self.high_contrast_checkbox = QCheckBox("Increase interface contrast")
        self.high_contrast_checkbox.setObjectName("highContrastPreference")
        self.high_contrast_checkbox.setAccessibleName("Increase interface contrast")
        self.high_contrast_checkbox.setEnabled(False)
        self.high_contrast_checkbox.setToolTip(
            "High-contrast mode is planned for theme validation"
        )
        form.addRow(
            semantic_label("Contrast", text_role="body"), self.high_contrast_checkbox
        )

        self.content_layout.addLayout(form)
        self.content_layout.addWidget(
            semantic_label(
                "Splitter positions, selected tabs, theme, and font size are restored "
                "when the application starts.",
                text_role="secondary",
            )
        )

        self.content_layout.addWidget(
            semantic_label("CAMPAIGN RELIABILITY", text_role="heading")
        )
        self.content_layout.addWidget(
            semantic_label(
                "Campaign state is continuously persisted. Named checkpoints provide "
                "verified rollback points; repair and replay operate without LM Studio.",
                text_role="secondary",
                word_wrap=True,
            )
        )
        reliability = QVBoxLayout()
        checkpoint = SemanticButton("Create Checkpoint", role="primary")
        checkpoint.setObjectName("createCheckpointButton")
        checkpoint.clicked.connect(self.checkpoint_create_requested)
        load = SemanticButton("Load Checkpoint", role="secondary")
        load.setObjectName("loadCheckpointButton")
        load.clicked.connect(self.checkpoint_load_requested)
        repair = SemanticButton("Inspect && Repair", role="secondary")
        repair.setObjectName("repairCampaignButton")
        repair.clicked.connect(self.repair_requested)
        replay = SemanticButton("Verify Replay", role="secondary")
        replay.setObjectName("verifyReplayButton")
        replay.clicked.connect(self.replay_requested)
        reliability.addWidget(checkpoint)
        reliability.addWidget(load)
        reliability.addWidget(repair)
        reliability.addWidget(replay)
        self.export_logs_button = SemanticButton("Export Diagnostic Logs", role="secondary")
        self.export_logs_button.setObjectName("exportDiagnosticLogsButton")
        self.export_logs_button.setAccessibleName("Export diagnostic logs")
        self.export_logs_button.setToolTip(
            "Save application, local-model, and evaluation logs without campaign data"
        )
        self.export_logs_button.clicked.connect(self.diagnostic_export_requested)
        reliability.addWidget(self.export_logs_button)
        self.content_layout.addLayout(reliability)
        self.reliability_status = semantic_label(
            "No reliability operation has run in this session.",
            object_name="reliabilityStatus",
            text_role="muted",
            word_wrap=True,
        )
        self.reliability_status.setAccessibleName("Campaign reliability status")
        self.content_layout.addWidget(self.reliability_status)
        self.content_layout.addStretch(1)

        self.back_button = SemanticButton("Return to Adventure", role="secondary")
        self.back_button.setObjectName("settingsBackButton")
        self.back_button.clicked.connect(self.back_requested)
        reset = SemanticButton("Restore UI Defaults", role="destructive")
        reset.setObjectName("resetUiButton")
        reset.setToolTip("Reset splitters, tabs, navigation, theme, and font size")
        reset.clicked.connect(self.reset_requested)
        self.content_layout.addWidget(reset)

    def _theme_changed(self, index: int) -> None:
        theme_id = self.theme_selector.itemData(index)
        if theme_id:
            self.theme_requested.emit(str(theme_id))

    def _adjust_font_size(self, delta: int) -> None:
        value = min(150, max(75, self._font_size_percent + delta))
        if value != self._font_size_percent:
            self.select_font_size(value)
            self.font_size_requested.emit(value)

    def _model_changed(self, index: int) -> None:
        model_id = self.model_selector.itemData(index)
        loaded = bool(self.model_selector.itemData(index, 257))
        self.model_load_button.setEnabled(bool(model_id) and not loaded)
        self.model_evaluate_button.setEnabled(bool(model_id) and loaded)
        if model_id and loaded:
            self.model_requested.emit(str(model_id))

    def _load_model(self) -> None:
        model_id = self.model_selector.currentData()
        if model_id and self.model_load_button.isEnabled():
            self.model_load_requested.emit(str(model_id))

    def _evaluate_model(self) -> None:
        model_id = self.model_selector.currentData()
        if model_id and self.model_evaluate_button.isEnabled():
            self.model_evaluation_requested.emit(str(model_id))

    def set_model_busy(self, busy: bool, message: str) -> None:
        self.model_selector.setEnabled(not busy)
        self.model_refresh_button.setEnabled(not busy)
        current_loaded = bool(
            self.model_selector.itemData(self.model_selector.currentIndex(), 257)
        )
        self.model_evaluate_button.setEnabled(
            not busy and bool(self.model_selector.currentData()) and current_loaded
        )
        self.model_load_button.setEnabled(
            not busy and bool(self.model_selector.currentData()) and not current_loaded
        )
        self.show_model_status(message)

    def set_models(
        self,
        models: Iterable[LMStudioModelInfo],
        selected_model_id: str | None,
    ) -> None:
        values = tuple(sorted(models, key=lambda item: (not item.loaded, item.display_name.casefold())))
        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        selected_index = -1
        loaded_count = 0
        for item in values:
            prefix = "Loaded and ready" if item.loaded else "Installed, not loaded"
            identifier = item.instance_id or item.model_id
            self.model_selector.addItem(f"{prefix} — {item.display_name}", identifier)
            index = self.model_selector.count() - 1
            self.model_selector.setItemData(index, item.loaded, 257)
            details = [item.display_name]
            if item.architecture:
                details.append(f"Architecture: {item.architecture}")
            if item.quantization:
                details.append(f"Quantization: {item.quantization}")
            if item.context_length:
                details.append(f"Context: {item.context_length:,} tokens")
            if item.memory_bytes:
                details.append(f"Loaded memory: {item.memory_bytes / 1_073_741_824:.1f} GB")
            self.model_selector.setItemData(index, "\n".join(details), Qt.ItemDataRole.ToolTipRole)
            if item.loaded:
                loaded_count += 1
            if item.loaded and selected_model_id in {item.model_id, item.instance_id, identifier}:
                selected_index = index
        if not values:
            self.model_selector.addItem("No models reported", "")
        if selected_index < 0:
            selected_index = next(
                (
                    index
                    for index in range(self.model_selector.count())
                    if bool(self.model_selector.itemData(index, 257))
                ),
                0,
            )
        self.model_selector.setCurrentIndex(selected_index)
        self.model_selector.blockSignals(False)
        current_id = self.model_selector.currentData()
        current_loaded = bool(self.model_selector.itemData(selected_index, 257))
        self.model_evaluate_button.setEnabled(bool(current_id) and current_loaded)
        self.model_load_button.setEnabled(bool(current_id) and not current_loaded)
        if current_id and current_loaded and current_id != selected_model_id:
            self.model_requested.emit(str(current_id))
        self.show_model_status(
            f"Connected to local AI: {loaded_count} loaded, "
            f"{len(values) - loaded_count} installed but not loaded."
        )

    def show_model_status(self, message: str, *, error: bool = False) -> None:
        self.model_status.setProperty("textRole", "danger" if error else "secondary")
        self.model_status.setText(message)
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)

    def show_model_evaluation(self, result: ModelEvaluation) -> None:
        self.show_model_status(result.status_line(), error=result.valid_responses < result.samples)

    def show_startup_status(self, message: str) -> None:
        self.startup_status.setText(message)

    def select_theme(self, theme_id: str) -> None:
        index = self.theme_selector.findData(theme_id)
        if index < 0 or index == self.theme_selector.currentIndex():
            return
        self.theme_selector.blockSignals(True)
        self.theme_selector.setCurrentIndex(index)
        self.theme_selector.blockSignals(False)

    def select_font_size(self, percent: int) -> None:
        self._font_size_percent = min(150, max(75, int(percent)))
        self.font_size_value.setText(f"{self._font_size_percent}%")
        self.font_size_decrease.setEnabled(self._font_size_percent > 75)
        self.font_size_increase.setEnabled(self._font_size_percent < 150)

    def select_reduced_motion(self, enabled: bool) -> None:
        if self.reduced_motion_checkbox.isChecked() == enabled:
            return
        self.reduced_motion_checkbox.blockSignals(True)
        self.reduced_motion_checkbox.setChecked(enabled)
        self.reduced_motion_checkbox.blockSignals(False)

    def show_reliability_status(self, message: str, *, error: bool = False) -> None:
        self.reliability_status.setProperty("textRole", "danger" if error else "secondary")
        self.reliability_status.setText(message)
        self.reliability_status.style().unpolish(self.reliability_status)
        self.reliability_status.style().polish(self.reliability_status)
