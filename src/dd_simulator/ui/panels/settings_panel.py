"""In-application settings panel for Phase 4 UI preferences."""

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget
)

from dd_simulator.local_model import LocalModelModelInfo, ModelEvaluation
from dd_simulator.ui.panels.common import semantic_label
from dd_simulator.ui.themes.theme_schema import ThemeDefinition
from dd_simulator.ui.widgets.codex_cards import codex_card, plain_label
from dd_simulator.ui.widgets.dice_roll import DEFAULT_HOLD_SECONDS, HOLD_RANGE_SECONDS
from dd_simulator.ui.widgets.semantic_button import SemanticButton


def _row_label(text: str) -> QLabel:
    return plain_label(text.upper(), "pageCardLabel")


def _help(text: str) -> QLabel:
    return plain_label(text, "pageCardMeta", word_wrap=True)


class SettingsPanel(QWidget):
    """Settings grouped into codex page cards in two columns; the page header is the window's."""

    theme_requested = Signal(str)
    font_size_requested = Signal(int)
    reduced_motion_requested = Signal(bool)
    glow_pulse_requested = Signal(bool)
    audio_requested = Signal(int, int, bool)  # music volume, ambience volume, muted
    sfx_volume_requested = Signal(int)
    dice_roll_seconds_requested = Signal(float)
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
        super().__init__()
        self.setObjectName("settingsPanel")
        self.setAccessibleName("Settings")
        model_card, model_layout = codex_card("Local AI Model", "settingsModelCard")
        display_card, display_layout = codex_card("Display & Accessibility", "settingsDisplayCard")
        audio_card, audio_layout = codex_card("Audio", "settingsAudioCard")
        reliability_card, reliability_layout = codex_card(
            "Campaign Reliability", "settingsReliabilityCard"
        )
        self.startup_status = semantic_label(
            "Startup checks pending.",
            object_name="startupReadinessStatus",
            text_role="secondary",
            word_wrap=True,
        )
        self.startup_status.setAccessibleName("Application startup readiness")
        model_layout.addWidget(_help(
            "Review the model provided by llama.cpp, Unsloth Studio, or LM Studio before evaluation or play."
        ))
        model_controls = QVBoxLayout()
        self.model_selector = QComboBox()
        self.model_selector.setObjectName("localModelSelector")
        self.model_selector.setAccessibleName("Local AI model")
        # Long model names elide instead of widening the card's column.
        self.model_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.model_selector.addItem("Refresh to discover models", "")
        self.model_selector.currentIndexChanged.connect(self._model_changed)
        model_controls.addWidget(self.model_selector)
        self.model_refresh_button = SemanticButton("Refresh Models", role="secondary")
        self.model_refresh_button.setObjectName("refreshLocalModelsButton")
        self.model_refresh_button.clicked.connect(self.model_refresh_requested)
        self.model_load_button = SemanticButton("Load Selected Model", role="primary")
        self.model_load_button.setObjectName("loadLocalModelButton")
        self.model_load_button.clicked.connect(self._load_model)
        self.model_load_button.setEnabled(False)
        self.model_evaluate_button = SemanticButton("Run 3-Sample Evaluation", role="primary")
        self.model_evaluate_button.setObjectName("evaluateLocalModelButton")
        self.model_evaluate_button.clicked.connect(self._evaluate_model)
        self.model_evaluate_button.setEnabled(False)
        model_controls.addWidget(self.model_refresh_button)
        model_controls.addWidget(self.model_load_button)
        model_controls.addWidget(self.model_evaluate_button)
        model_layout.addLayout(model_controls)
        self.model_status = semantic_label(
            "The local AI provider has not been scanned in this session.",
            object_name="localModelStatus",
            text_role="muted",
            word_wrap=True,
        )
        self.model_status.setAccessibleName("Local AI model status")
        model_layout.addWidget(self.model_status)
        configure_local_ai = SemanticButton("Change Local AI Setup", role="secondary")
        configure_local_ai.setObjectName("changeLocalAiSetupButton")
        configure_local_ai.clicked.connect(self.local_ai_setup_requested)
        model_layout.addWidget(configure_local_ai)
        model_layout.addWidget(_help(
            "Troubleshooting: load exactly one model, refresh the list, then run the "
            "3-sample evaluation. If generation still fails, reload the model and export "
            "diagnostic logs from Campaign Reliability."
        ))

        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        # Labels above their controls: WrapLongRows only wraps once the width is known,
        # so at large fonts the card's minimum height came out short and rows overlapped.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.theme_selector = QComboBox()
        self.theme_selector.setObjectName("settingsThemeSelector")
        self.theme_selector.setAccessibleName("Interface theme")
        for theme in themes:
            self.theme_selector.addItem(theme.name, theme.theme_id)
        self.theme_selector.currentIndexChanged.connect(self._theme_changed)
        form.addRow(_row_label("Theme"), self.theme_selector)

        # Drag to a size, then Apply: restyling the whole window on every step is slow.
        font_controls = QVBoxLayout()
        font_controls.setContentsMargins(0, 0, 0, 0)
        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(0, 0, 0, 0)
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setObjectName("fontSizeSlider")
        self.font_size_slider.setAccessibleName("Interface font size")
        self.font_size_slider.setRange(75, 150)
        self.font_size_slider.setSingleStep(5)
        self.font_size_slider.setPageStep(5)
        self.font_size_slider.setValue(100)
        self.font_size_slider.valueChanged.connect(self._font_size_slid)
        self.font_size_value = semantic_label(
            "100%", object_name="fontSizeValue", text_role="body"
        )
        self.font_size_value.setAccessibleName("Selected interface font size")
        self.font_size_value.setMinimumWidth(44)
        slider_row.addWidget(self.font_size_slider, 1)
        slider_row.addWidget(self.font_size_value)
        font_controls.addLayout(slider_row)
        self.font_size_apply = SemanticButton("Apply", role="secondary")
        self.font_size_apply.setObjectName("applyFontSizeButton")
        self.font_size_apply.setAccessibleName("Apply interface font size")
        self.font_size_apply.setEnabled(False)
        self.font_size_apply.clicked.connect(self._apply_font_size)
        font_controls.addWidget(self.font_size_apply, 0, Qt.AlignmentFlag.AlignLeft)
        self._font_size_percent = 100
        form.addRow(_row_label("Font size"), font_controls)

        self.reduced_motion_checkbox = QCheckBox("Reduce interface motion")
        self.reduced_motion_checkbox.setObjectName("reducedMotionPreference")
        self.reduced_motion_checkbox.setAccessibleName("Reduce interface motion")
        self.reduced_motion_checkbox.setToolTip(
            "Show resource changes immediately instead of animating them"
        )
        self.reduced_motion_checkbox.toggled.connect(self.reduced_motion_requested)
        form.addRow(_row_label("Motion"), self.reduced_motion_checkbox)

        self.glow_pulse_checkbox = QCheckBox("Pulse item rarity glow")
        self.glow_pulse_checkbox.setObjectName("glowPulsePreference")
        self.glow_pulse_checkbox.setAccessibleName("Pulse item rarity glow")
        self.glow_pulse_checkbox.setToolTip("Let the rarity glow behind items gently pulse")
        self.glow_pulse_checkbox.setChecked(True)
        self.glow_pulse_checkbox.toggled.connect(self.glow_pulse_requested)
        form.addRow(_row_label("Rarity glow"), self.glow_pulse_checkbox)

        self.dice_roll_slider = QSlider(Qt.Orientation.Horizontal)
        self.dice_roll_slider.setObjectName("diceRollSecondsSlider")
        self.dice_roll_slider.setAccessibleName("Dice roll display time")
        self.dice_roll_slider.setToolTip(
            "How long a dice roll stays under the conversation before its one-second fade"
        )
        low, high = HOLD_RANGE_SECONDS
        self.dice_roll_slider.setRange(int(low), int(high))
        self.dice_roll_slider.setPageStep(1)
        self.dice_roll_slider.setValue(int(DEFAULT_HOLD_SECONDS))
        self.dice_roll_slider.valueChanged.connect(
            lambda seconds: self.dice_roll_seconds_requested.emit(float(seconds))
        )
        form.addRow(_row_label("Dice roll display"), self._with_value(self.dice_roll_slider, " s"))

        self.high_contrast_checkbox = QCheckBox("Increase interface contrast")
        self.high_contrast_checkbox.setObjectName("highContrastPreference")
        self.high_contrast_checkbox.setAccessibleName("Increase interface contrast")
        self.high_contrast_checkbox.setEnabled(False)
        self.high_contrast_checkbox.setToolTip(
            "High-contrast mode is planned for theme validation"
        )
        form.addRow(_row_label("Contrast"), self.high_contrast_checkbox)
        display_layout.addLayout(form)
        display_layout.addWidget(_help(
            "Splitter positions, selected tabs, theme, and font size are restored "
            "when the application starts."
        ))

        audio_form = QFormLayout()
        audio_form.setHorizontalSpacing(18)
        audio_form.setVerticalSpacing(10)
        audio_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)  # as Display

        self.music_volume_slider = self._volume_slider("musicVolumeSlider", "Music volume")
        audio_form.addRow(_row_label("Music volume"), self._with_value(self.music_volume_slider))
        self.ambience_volume_slider = self._volume_slider(
            "ambienceVolumeSlider", "Ambience volume"
        )
        audio_form.addRow(
            _row_label("Ambience volume"), self._with_value(self.ambience_volume_slider)
        )
        self.sfx_volume_slider = self._volume_slider("sfxVolumeSlider", "Interface sound volume")
        self.sfx_volume_slider.valueChanged.disconnect(self._audio_changed)
        # once per drag or step: every tick would replay the sample click
        self.sfx_volume_slider.sliderReleased.connect(self._sfx_changed)
        self.sfx_volume_slider.valueChanged.connect(
            lambda _value: None if self.sfx_volume_slider.isSliderDown() else self._sfx_changed()
        )
        audio_form.addRow(_row_label("Interface sounds"), self._with_value(self.sfx_volume_slider))
        self.mute_checkbox = QCheckBox("Mute all sound")
        self.mute_checkbox.setObjectName("muteAudioPreference")
        self.mute_checkbox.setAccessibleName("Mute all sound")
        self.mute_checkbox.toggled.connect(self._audio_changed)
        audio_form.addRow(_row_label("Mute"), self.mute_checkbox)
        audio_layout.addLayout(audio_form)

        reliability_layout.addWidget(self.startup_status)
        reliability_layout.addWidget(_help(
            "Campaign state is continuously persisted. Named checkpoints provide "
            "verified rollback points; repair and replay operate without the local model."
        ))
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
        reliability_layout.addLayout(reliability)
        self.reliability_status = semantic_label(
            "No reliability operation has run in this session.",
            object_name="reliabilityStatus",
            text_role="muted",
            word_wrap=True,
        )
        self.reliability_status.setAccessibleName("Campaign reliability status")
        reliability_layout.addWidget(self.reliability_status)

        self.back_button = SemanticButton("Return to Adventure", role="secondary")
        self.back_button.setObjectName("settingsBackButton")
        self.back_button.clicked.connect(self.back_requested)
        reset = SemanticButton("Restore UI Defaults", role="destructive")
        reset.setObjectName("resetUiButton")
        reset.setToolTip("Reset splitters, tabs, navigation, theme, and font size")
        reset.clicked.connect(self.reset_requested)
        display_layout.addWidget(reset)

        columns = QHBoxLayout(self)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(8)
        for cards in ((model_card, reliability_card), (display_card, audio_card)):
            column = QVBoxLayout()
            column.setSpacing(8)
            for card in cards:
                column.addWidget(card)
            column.setStretch(len(cards) - 1, 1)  # columns end level with the Campaigns card
            columns.addLayout(column, 1)

    @staticmethod
    def _with_value(slider: QSlider, suffix: str = "%") -> QHBoxLayout:
        """The slider with its live value (a percentage by default) beside it."""

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        value = semantic_label(f"{slider.value()}{suffix}", object_name="sliderValue", text_role="body")
        value.setMinimumWidth(44)
        slider.valueChanged.connect(lambda level: value.setText(f"{level}{suffix}"))
        slider.setProperty("valueLabel", value)  # select_audio sets values with signals blocked
        row.addWidget(slider, 1)
        row.addWidget(value)
        return row

    def _volume_slider(self, object_name: str, accessible_name: str) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName(object_name)
        slider.setAccessibleName(accessible_name)
        slider.setRange(0, 100)
        slider.setPageStep(10)
        slider.valueChanged.connect(self._audio_changed)
        return slider

    def _audio_changed(self, *_args: object) -> None:
        self.audio_requested.emit(
            self.music_volume_slider.value(),
            self.ambience_volume_slider.value(),
            self.mute_checkbox.isChecked(),
        )

    def _sfx_changed(self) -> None:
        self.sfx_volume_requested.emit(self.sfx_volume_slider.value())

    def select_sfx_volume(self, volume: int) -> None:
        self.sfx_volume_slider.blockSignals(True)
        self.sfx_volume_slider.setValue(int(volume))
        self.sfx_volume_slider.blockSignals(False)
        self.sfx_volume_slider.property("valueLabel").setText(f"{self.sfx_volume_slider.value()}%")

    def select_dice_roll_seconds(self, seconds: float) -> None:
        self.dice_roll_slider.blockSignals(True)
        self.dice_roll_slider.setValue(round(seconds))
        self.dice_roll_slider.blockSignals(False)
        self.dice_roll_slider.property("valueLabel").setText(f"{self.dice_roll_slider.value()} s")

    def select_audio(self, music: int, ambience: int, muted: bool) -> None:
        for widget, value in (
            (self.music_volume_slider, music),
            (self.ambience_volume_slider, ambience),
            (self.mute_checkbox, muted),
        ):
            widget.blockSignals(True)
            if isinstance(widget, QSlider):
                widget.setValue(int(value))
                widget.property("valueLabel").setText(f"{widget.value()}%")
            else:
                widget.setChecked(bool(value))
            widget.blockSignals(False)

    def _theme_changed(self, index: int) -> None:
        theme_id = self.theme_selector.itemData(index)
        if theme_id:
            self.theme_requested.emit(str(theme_id))

    def _font_size_slid(self, value: int) -> None:
        value = round(value / 5) * 5  # whole 5% steps, also when dragged
        if value != self.font_size_slider.value():
            self.font_size_slider.setValue(value)
            return
        self.font_size_value.setText(f"{value}%")
        self.font_size_apply.setEnabled(value != self._font_size_percent)

    def _apply_font_size(self) -> None:
        value = self.font_size_slider.value()
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
        models: Iterable[LocalModelModelInfo],
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
        self.font_size_slider.blockSignals(True)
        self.font_size_slider.setValue(self._font_size_percent)
        self.font_size_slider.blockSignals(False)
        self.font_size_value.setText(f"{self._font_size_percent}%")
        self.font_size_apply.setEnabled(False)

    def select_glow_pulse(self, enabled: bool) -> None:
        self.glow_pulse_checkbox.blockSignals(True)
        self.glow_pulse_checkbox.setChecked(enabled)
        self.glow_pulse_checkbox.blockSignals(False)

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
