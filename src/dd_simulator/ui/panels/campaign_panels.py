"""Themed campaign selection and complete character-creation forms."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.state.character_creation import (
    ABILITY_NAMES,
    ANCESTRIES,
    ARMOR_CHOICES,
    BACKGROUNDS,
    CAMERA_STYLES,
    CLASS_DETAILS,
    CLASSES,
    DEFAULT_CONTENT_PREFERENCES,
    DIFFICULTIES,
    FLAWS,
    KEEPSAKE_CHOICES,
    LOCATIONS,
    MOTIVATIONS,
    PERSONALITIES,
    PRIMARY_WEAPONS,
    REGIONS,
    RANGED_WEAPONS,
    SECONDARY_WEAPONS,
    SHIELD_CHOICES,
    SKILLS,
    STRENGTHS,
    TOOL_CHOICES,
    TONES,
    VISUAL_STYLES,
    WORLD_TYPES,
    CharacterCreationDraft,
    CharacterCreationValidator,
    ability_modifier,
    level_one_hit_points,
    point_buy_spent,
)
from dd_simulator.lm_studio import (
    CharacterRandomizationService,
    LMStudioModelInfo,
    ModelEvaluation,
)
from dd_simulator.state.models import CampaignRecord
from dd_simulator.state.item_actions import item_definition
from dd_simulator.state.presets import load_preset, preset_choices
from dd_simulator.ui.panels.common import DashboardPanel, semantic_label
from dd_simulator.ui.panels.navigation_pages import centered_third
from dd_simulator.ui.services.randomization_worker import (
    CampaignRandomizationTask,
    RandomizationTask,
)
from dd_simulator.ui.widgets.full_click_combo import FullClickComboBox
from dd_simulator.ui.widgets.option_dialog import OptionSelectionDialog
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_frame import ThemedFrame


PERSONALITY_DESCRIPTIONS = {
    "Brave": "Faces danger readily, even when retreat may be safer.",
    "Cautious": "Studies risks and favors preparation before acting.",
    "Charming": "Builds rapport easily through warmth, humor, or confidence.",
    "Suspicious": "Questions motives and looks for concealed threats.",
    "Curious": "Seeks answers, unfamiliar places, and hidden knowledge.",
    "Honorable": "Values promises, fairness, and a personal code of conduct.",
    "Ruthless": "Prioritizes results and accepts harsh choices to achieve them.",
    "Compassionate": "Notices suffering and is inclined to help others.",
    "Sarcastic": "Uses dry or cutting humor, especially under pressure.",
    "Ambitious": "Pursues status, power, mastery, or a lasting legacy.",
    "Quiet": "Speaks selectively and tends to observe before responding.",
    "Reckless": "Acts quickly on instinct and accepts significant risk.",
}
STRENGTH_DESCRIPTIONS = {
    "Courage": "Acts despite fear and remains steady when facing danger.",
    "Intelligence": "Analyzes problems, recalls knowledge, and forms sound plans.",
    "Loyalty": "Stands by trusted people, causes, and promises.",
    "Discipline": "Maintains focus, restraint, and dependable habits under pressure.",
    "Creativity": "Finds original approaches when ordinary solutions fail.",
    "Persuasion": "Influences others through reasoning, confidence, or empathy.",
    "Survival instinct": "Recognizes danger and reacts quickly to remain alive.",
    "Magical talent": "Has a natural aptitude for understanding and wielding magic.",
}
FLAW_DESCRIPTIONS = {
    "Pride": "Resists admitting weakness, mistakes, or the need for help.",
    "Greed": "Places excessive importance on wealth, possessions, or reward.",
    "Impulsiveness": "Acts before fully considering risks and consequences.",
    "Distrust": "Struggles to rely on others or accept their motives as sincere.",
    "Short temper": "Becomes angry quickly when challenged, delayed, or insulted.",
    "Recklessness": "Accepts unnecessary danger even when safer choices exist.",
    "Obsession": "Fixates on one goal or idea at the expense of other priorities.",
    "Excessive loyalty": "Supports someone or something despite serious warning signs.",
}
MOTIVATION_DESCRIPTIONS = {
    "Revenge": "Seeks to punish someone responsible for a past wrong.",
    "Wealth": "Pursues financial security, treasure, or material success.",
    "Knowledge": "Searches for truth, secrets, history, or forbidden learning.",
    "Redemption": "Tries to atone for past actions and become worthy of forgiveness.",
    "Adventure": "Seeks discovery, danger, excitement, and unfamiliar experiences.",
    "Protecting someone": "Acts to keep a specific person or group safe.",
    "Finding a missing person": "Searches for someone whose fate or location is unknown.",
    "Recovering an artifact": "Pursues an important lost, stolen, or hidden object.",
    "Escaping the past": "Tries to outrun former actions, enemies, or identity.",
    "Gaining power": "Seeks greater personal, political, martial, or magical influence.",
    "Saving a homeland": "Works to defend or restore a threatened home and its people.",
}


def _choice_combo(name: str, values: Iterable[str]) -> FullClickComboBox:
    combo = FullClickComboBox()
    combo.setObjectName(name)
    combo.addItems(tuple(values))
    combo.setAccessibleName(name.replace("Creation", "").replace("Combo", ""))
    return combo


def _add_choice_tooltips(
    combo: FullClickComboBox,
    descriptions: dict[str, str],
) -> None:
    for index in range(combo.count()):
        combo.setItemData(
            index, descriptions.get(combo.itemText(index), ""), Qt.ItemDataRole.ToolTipRole
        )
    combo.currentTextChanged.connect(
        lambda value: combo.setToolTip(descriptions.get(value, ""))
    )
    combo.setToolTip(descriptions.get(combo.currentText(), ""))


def _text_field(name: str, placeholder: str = "") -> QLineEdit:
    field = QLineEdit()
    field.setObjectName(name)
    field.setPlaceholderText(placeholder)
    field.setMaxLength(200)
    field.setAccessibleName(name.replace("Creation", " ").replace("Input", " "))
    return field


def _text_area(name: str, placeholder: str, maximum_height: int = 92) -> QPlainTextEdit:
    field = QPlainTextEdit()
    field.setObjectName(name)
    field.setPlaceholderText(placeholder)
    field.setMaximumHeight(maximum_height)
    field.setTabChangesFocus(True)
    field.setAccessibleName(name.replace("Creation", " ").replace("Input", " "))
    return field


class CampaignBrowserPanel(DashboardPanel):
    new_requested = Signal()
    preset_requested = Signal(str)
    load_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, campaigns: tuple[CampaignRecord, ...]) -> None:
        super().__init__("campaignBrowserPanel", "CAMPAIGNS")
        intro = semantic_label(
            "Load a completed campaign or begin a new character.",
            text_role="secondary",
        )
        self.content_layout.addWidget(intro)
        self.content_layout.addWidget(
            semantic_label("PRESET CAMPAIGNS", text_role="accent")
        )
        self.preset_list = QListWidget()
        self.preset_list.setObjectName("presetCampaignList")
        self.preset_list.setAccessibleName("Preset campaigns")
        for label, preset_id in preset_choices():
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, preset_id)
            item.setToolTip("Begin character creation for this authored campaign")
            self.preset_list.addItem(item)
        self.preset_list.itemClicked.connect(self._select_preset)
        self.content_layout.addWidget(self.preset_list, 1)

        self.content_layout.addWidget(
            semantic_label("CUSTOM CAMPAIGNS", text_role="secondary")
        )
        self.campaign_list = QListWidget()
        self.campaign_list.setObjectName("campaignList")
        self.campaign_list.setAccessibleName("Custom campaigns")
        self.campaign_list.itemDoubleClicked.connect(lambda _item: self._load())
        self.campaign_list.itemSelectionChanged.connect(self._update_buttons)
        self.content_layout.addWidget(self.campaign_list, 1)

        buttons = QHBoxLayout()
        self.new_button = SemanticButton("New Campaign", role="primary")
        self.new_button.setObjectName("newCampaignButton")
        self.new_button.clicked.connect(self.new_requested)
        self.delete_button = SemanticButton("Delete Campaign", role="destructive")
        self.delete_button.setObjectName("deleteCampaignButton")
        self.delete_button.clicked.connect(self._delete)
        self.load_button = SemanticButton("Load Selected", role="secondary")
        self.load_button.setObjectName("loadCampaignButton")
        self.load_button.clicked.connect(self._load)
        buttons.addWidget(self.new_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        buttons.addWidget(self.load_button)
        self.content_layout.addLayout(buttons)
        self.set_campaigns(campaigns)

    def set_campaigns(self, campaigns: tuple[CampaignRecord, ...]) -> None:
        self.campaign_list.clear()
        for campaign in campaigns:
            suffix = "" if campaign.creation_complete else " (creation incomplete)"
            item = QListWidgetItem(f"{campaign.name}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, campaign.campaign_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, campaign.creation_complete)
            item.setToolTip(f"Status: {campaign.status}")
            self.campaign_list.addItem(item)
        if self.campaign_list.count():
            self.campaign_list.setCurrentRow(0)
        self._update_buttons()

    def _update_buttons(self) -> None:
        item = self.campaign_list.currentItem()
        self.delete_button.setEnabled(item is not None)
        self.load_button.setEnabled(
            item is not None and bool(item.data(Qt.ItemDataRole.UserRole + 1))
        )

    def _delete(self) -> None:
        item = self.campaign_list.currentItem()
        if item is not None:
            self.delete_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def _load(self) -> None:
        item = self.campaign_list.currentItem()
        if item is not None and bool(item.data(Qt.ItemDataRole.UserRole + 1)):
            self.load_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def _select_preset(self, item: QListWidgetItem) -> None:
        self.preset_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))


class CharacterCreationPanel(DashboardPanel):
    cancelled = Signal()
    completed = Signal(object)
    model_refresh_requested = Signal()
    model_requested = Signal(str)
    model_load_requested = Signal(str)
    model_evaluation_requested = Signal(str)

    TAB_FIELDS = {
        "name": 1, "ancestry": 1, "age": 1, "body_description": 1,
        "face_description": 1, "clothing_style": 1, "background": 1,
        "character_class": 1, "skills": 1, "personalities": 1,
        "primary_strength": 1, "meaningful_flaw": 1, "motivation": 1,
        "biography": 1, "backstory": 1, "primary_weapon": 1,
        "ability_scores": 1, "world_type": 2, "tone": 2, "starting_region": 2,
        "starting_location": 2, "difficulty": 2, "content_preferences": 2,
        "visual_style": 2, "camera_style": 2, "campaign_description": 2,
        "campaign_name": 2,
    }

    def __init__(
        self,
        randomizer: CharacterRandomizationService | None = None,
        *,
        thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__("characterCreationPanel", "CHARACTER CREATION")
        self.randomizer = randomizer
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self.randomize_buttons: dict[str, SemanticButton] = {}
        self.randomized_fields: dict[str, QLineEdit | QPlainTextEdit] = {}
        self._randomization_tasks: set[RandomizationTask] = set()
        self._campaign_randomization_task: CampaignRandomizationTask | None = None
        self._preset_only_mode = False
        self._model_loaded = False
        self.content_layout.addWidget(
            semantic_label(
                "Complete every required selection, then confirm the written review. "
                "Choose fixed options from full-click dropdowns; use Randomize for local AI suggestions.",
                text_role="secondary",
                word_wrap=True,
            )
        )
        self.tabs = QTabWidget()
        self.tabs.setObjectName("characterCreationTabs")
        self.tabs.setAccessibleName("Character creation sections")
        self.content_layout.addWidget(self.tabs, 1)

        self._build_model_page()
        self._build_character_page()
        self._build_campaign_page()
        self._build_review_page()
        for index in range(1, self.tabs.count()):
            self.tabs.setTabEnabled(index, False)
        self.tabs.currentChanged.connect(self._tab_changed)

        footer = QHBoxLayout()
        cancel = SemanticButton("Cancel", role="destructive")
        cancel.setObjectName("cancelCharacterCreationButton")
        cancel.clicked.connect(self.cancelled)
        self.error_label = semantic_label(
            "", object_name="characterCreationError", text_role="danger", word_wrap=True
        )
        self.complete_button = SemanticButton("Create Campaign", role="primary")
        self.complete_button.setObjectName("completeCharacterCreationButton")
        self.complete_button.clicked.connect(self._complete)
        self.complete_button.setEnabled(False)
        self.review_confirmed.toggled.connect(self._update_complete_button)
        footer.addWidget(cancel)
        footer.addWidget(self.error_label, 1)
        footer.addWidget(self.complete_button)
        footer_host = QWidget()
        footer_host.setLayout(footer)
        self.content_layout.addWidget(centered_third(footer_host, "creationCenteredFooter"))

    def _randomizable_text_field(
        self, section: str, name: str, placeholder: str,
    ) -> tuple[QLineEdit, QWidget]:
        field = _text_field(name, placeholder)
        return field, self._randomizable_row(section, field)

    def _randomizable_text_area(
        self,
        section: str,
        name: str,
        placeholder: str,
        maximum_height: int = 92,
    ) -> tuple[QPlainTextEdit, QWidget]:
        field = _text_area(name, placeholder, maximum_height)
        row = self._randomizable_row(section, field)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(row)
        counter = semantic_label(
            "0 / 4000", object_name="creationCharacterCounter", text_role="muted"
        )
        counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(counter)
        field.textChanged.connect(
            lambda editor=field, label=counter: self._enforce_text_limit(
                editor, label, 4000
            )
        )
        return field, host

    @staticmethod
    def _enforce_text_limit(
        field: QPlainTextEdit, counter: QLabel, maximum: int
    ) -> None:
        value = field.toPlainText()
        if len(value) > maximum:
            field.blockSignals(True)
            field.setPlainText(value[:maximum])
            cursor = field.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            field.setTextCursor(cursor)
            field.blockSignals(False)
            value = field.toPlainText()
        counter.setText(f"{len(value)} / {maximum}")

    def _randomizable_row(
        self, section: str, field: QLineEdit | QPlainTextEdit,
    ) -> QWidget:
        button = SemanticButton("Randomize", role="secondary")
        button.setObjectName(f"randomize{section.title().replace('_', '')}Button")
        button.setToolTip("Generate three options with the loaded local LM Studio model")
        button.clicked.connect(
            lambda _checked=False, target=section: self._request_randomization(target)
        )
        row = QWidget()
        row.setObjectName("randomizableField")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(field, 1)
        layout.addWidget(button)
        self.randomize_buttons[section] = button
        self.randomized_fields[section] = field
        return row

    def _page(
        self, name: str, *, vertical_spacing: int = 8,
    ) -> tuple[QWidget, QFormLayout]:
        scroll = QScrollArea()
        scroll.setObjectName(f"{name}CreationScroll")
        scroll.setProperty("creationSurface", True)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        page = QWidget()
        page.setObjectName(f"{name}CreationPage")
        page.setProperty("creationSurface", True)
        outer = QGridLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        for column in range(3):
            outer.setColumnStretch(column, 1)
        form_host = QWidget()
        form_host.setObjectName(f"{name}CreationForm")
        form_host.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        form = QFormLayout(form_host)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(vertical_spacing)
        outer.addWidget(form_host, 0, 1, Qt.AlignmentFlag.AlignTop)
        outer.setRowStretch(1, 1)
        scroll.setWidget(page)
        return scroll, form

    def _two_column_page(
        self,
        name: str,
        left_heading: str,
        right_heading: str,
    ) -> tuple[QWidget, QFormLayout, QFormLayout]:
        scroll = QScrollArea()
        scroll.setObjectName(f"{name}CreationScroll")
        scroll.setProperty("creationSurface", True)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        page = QWidget()
        page.setObjectName(f"{name}CreationPage")
        page.setProperty("creationSurface", True)
        columns = QHBoxLayout(page)
        columns.setContentsMargins(18, 8, 18, 8)
        columns.setSpacing(24)

        forms: list[QFormLayout] = []
        for side, heading in (("Left", left_heading), ("Right", right_heading)):
            column = QWidget()
            column.setObjectName(f"{name}Creation{side}Column")
            column.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
            )
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(6)
            column_layout.addWidget(
                semantic_label(
                    heading,
                    object_name="creationSectionTitle",
                    text_role="accent",
                )
            )
            form_host = QWidget()
            form_host.setObjectName(f"{name}Creation{side}Form")
            form = QFormLayout(form_host)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(4)
            column_layout.addWidget(form_host)
            column_layout.addStretch(1)
            columns.addWidget(column, 1)
            forms.append(form)
        scroll.setWidget(page)
        return scroll, forms[0], forms[1]

    def _build_model_page(self) -> None:
        page, form = self._page("model")
        form.addRow(
            semantic_label(
                "SECTION 1 — LOCAL AI MODEL SELECTION",
                object_name="creationSectionTitle",
                text_role="accent",
            )
        )
        form.addRow(
            semantic_label(
                "Load one local AI model before creating a character. Loading a "
                "model here unloads other active models to prevent channel conflicts.",
                text_role="secondary",
                word_wrap=True,
            )
        )
        self.model_selector = FullClickComboBox()
        self.model_selector.setObjectName("creationLmStudioModelSelector")
        self.model_selector.setAccessibleName("Character creation local AI model")
        self.model_selector.addItem("Refresh to discover models", "")
        self.model_selector.currentIndexChanged.connect(self._model_changed)
        form.addRow("Installed model *", self.model_selector)
        self.model_refresh_button = SemanticButton(
            "Refresh Models", role="secondary", object_name="creationRefreshModelsButton"
        )
        self.model_refresh_button.clicked.connect(self.model_refresh_requested)
        form.addRow("", self.model_refresh_button)
        self.model_load_button = SemanticButton(
            "Load Selected Model", role="primary", object_name="creationLoadModelButton"
        )
        self.model_load_button.setEnabled(False)
        self.model_load_button.clicked.connect(self._load_model)
        form.addRow("", self.model_load_button)
        self.model_evaluate_button = SemanticButton(
            "Run 3-Sample Evaluation",
            role="secondary",
            object_name="creationEvaluateModelButton",
        )
        self.model_evaluate_button.setEnabled(False)
        self.model_evaluate_button.clicked.connect(self._evaluate_model)
        form.addRow("", self.model_evaluate_button)
        self.model_status = semantic_label(
            "Refresh the model list, then load one model to unlock character creation.",
            object_name="creationLmStudioModelStatus",
            text_role="muted",
            word_wrap=True,
        )
        form.addRow(self.model_status)
        self.tabs.addTab(page, "1. Local AI Model Selection")

    def _model_changed(self, index: int) -> None:
        model_id = self.model_selector.itemData(index)
        loaded = bool(self.model_selector.itemData(index, 257))
        self.model_load_button.setEnabled(bool(model_id) and not loaded)
        self.model_evaluate_button.setEnabled(bool(model_id) and loaded)
        self._set_creation_unlocked(bool(model_id) and loaded)
        if model_id and loaded:
            self.model_requested.emit(str(model_id))

    def _load_model(self) -> None:
        model_id = self.model_selector.currentData()
        if model_id and self.model_load_button.isEnabled():
            self._set_creation_unlocked(False)
            self.model_load_requested.emit(str(model_id))

    def _evaluate_model(self) -> None:
        model_id = self.model_selector.currentData()
        if model_id and self.model_evaluate_button.isEnabled():
            self.model_evaluation_requested.emit(str(model_id))

    def _set_creation_unlocked(self, unlocked: bool) -> None:
        self._model_loaded = unlocked
        for index in range(1, self.tabs.count()):
            self.tabs.setTabEnabled(index, unlocked)
        if not unlocked and self.tabs.currentIndex() > 0:
            self.tabs.setCurrentIndex(0)
        if hasattr(self, "complete_button"):
            self._update_complete_button()

    def _update_complete_button(self, _checked: bool = False) -> None:
        self.complete_button.setEnabled(
            self._model_loaded
            and self.review_confirmed.isChecked()
        )

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
        if busy:
            self._set_creation_unlocked(False)
        self.show_model_status(message)

    def set_models(
        self,
        models: Iterable[LMStudioModelInfo],
        selected_model_id: str | None,
    ) -> None:
        values = tuple(
            sorted(models, key=lambda item: (not item.loaded, item.display_name.casefold()))
        )
        self.model_selector.blockSignals(True)
        self.model_selector.clear()
        selected_index = -1
        for item in values:
            prefix = "Loaded and ready" if item.loaded else "Installed, not loaded"
            identifier = item.instance_id or item.model_id
            self.model_selector.addItem(f"{prefix} — {item.display_name}", identifier)
            index = self.model_selector.count() - 1
            self.model_selector.setItemData(index, item.loaded, 257)
            if item.loaded and selected_model_id in {
                item.model_id, item.instance_id, identifier,
            }:
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
        loaded = bool(self.model_selector.itemData(selected_index, 257))
        current_id = self.model_selector.currentData()
        self.model_load_button.setEnabled(bool(current_id) and not loaded)
        self.model_evaluate_button.setEnabled(bool(current_id) and loaded)
        self._set_creation_unlocked(bool(current_id) and loaded)
        if current_id and loaded:
            self.model_requested.emit(str(current_id))
        loaded_count = sum(item.loaded for item in values)
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
        self.show_model_status(
            result.status_line(), error=result.valid_responses < result.samples
        )

    def _build_character_page(self) -> None:
        page = QScrollArea()
        page.setObjectName("characterCreationScroll")
        page.setProperty("creationSurface", True)
        page.setWidgetResizable(True)
        page.setFrameShape(QScrollArea.Shape.NoFrame)
        sheet = ThemedFrame("characterCreationSheetSurface", role="section")
        sheet.setProperty("creationSurface", True)
        page_layout = QVBoxLayout(sheet)
        page_layout.setContentsMargins(14, 10, 14, 12)
        page_layout.setSpacing(7)
        page_layout.addWidget(semantic_label(
            "SECTION 2 — CHARACTER SHEET",
            object_name="creationSectionTitle",
            text_role="accent",
        ))

        def section(title: str) -> tuple[ThemedFrame, QFormLayout]:
            frame = ThemedFrame("characterSheetSection", role="section")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(9, 5, 9, 7)
            layout.setSpacing(3)
            layout.addWidget(semantic_label(title.upper(), text_role="accent"))
            host = QWidget()
            form = QFormLayout(host)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setFormAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            form.setHorizontalSpacing(8)
            form.setVerticalSpacing(4)
            layout.addWidget(host, 0, Qt.AlignmentFlag.AlignTop)
            return frame, form

        appearance, left_form = section("Appearance & Identity")
        role, right_form = section("Role & Skills")
        equipment, equipment_form = section("Starting Equipment")
        self.character_name, character_name_row = self._randomizable_text_field(
            "character_name", "characterNameInput", "Character name"
        )
        self.ancestry = _choice_combo("ancestryCreationCombo", ANCESTRIES)
        self.age = QSpinBox()
        self.age.setObjectName("ageCreationSpin")
        self.age.setRange(1, 2000)
        self.age.setValue(18)
        self.age.setAccessibleName("Adult age")
        self.gender = _text_field("genderIdentityInput", "Optional")
        self.pronouns = _text_field("pronounsInput", "Optional")
        self.body, body_row = self._randomizable_text_area(
            "body_description", "bodyDescriptionInput",
            "Height, build, proportions, and physical presence",
        )
        self.face, face_row = self._randomizable_text_area(
            "face_description", "faceDescriptionInput",
            "Face, eyes, hair, covering, scars, tattoos, and ancestry-specific traits",
            120,
        )
        self.clothing, clothing_row = self._randomizable_text_area(
            "clothing_style", "clothingStyleInput", "Normal clothing style before armor"
        )
        self.biography, biography_row = self._randomizable_text_area(
            "biography", "biographyCreationInput",
            "Optional short biography and formative backstory", 120,
        )
        # Legacy attribute retained for callers that restore pre-26.8.2 drafts.
        self.backstory = self.biography
        self.randomized_fields["backstory"] = self.biography
        for label, widget in (
            ("Gender identity", self.gender),
            ("Pronouns", self.pronouns),
            ("Body and height *", body_row),
            ("Face and features *", face_row),
            ("Clothing style *", clothing_row),
            ("Biography/Backstory", biography_row),
        ):
            left_form.addRow(label, widget)

        self.background = _choice_combo("backgroundCreationCombo", BACKGROUNDS)
        self.character_class = _choice_combo("classCreationCombo", CLASSES)
        identity = ThemedFrame("characterSheetIdentity", role="section")
        identity_grid = QGridLayout(identity)
        identity_grid.setContentsMargins(9, 7, 9, 8)
        identity_grid.setHorizontalSpacing(10)
        for column, (label, widget) in enumerate((
            ("Character", character_name_row),
            ("Ancestry", self.ancestry),
            ("Class", self.character_class),
            ("Adult age", self.age),
            ("Background", self.background),
        )):
            identity_grid.addWidget(semantic_label(label.upper(), text_role="muted"), 0, column)
            identity_grid.addWidget(widget, 1, column)
            identity_grid.setColumnStretch(column, 1)
        page_layout.addWidget(identity)
        self._build_ability_scores(page_layout)
        self.character_class.currentTextChanged.connect(self._update_class_details)
        self.skill_buttons: dict[str, SemanticButton] = {}
        skill_grid = QGridLayout()
        skill_grid.setContentsMargins(0, 0, 0, 0)
        skill_grid.setSpacing(4)
        for index, skill in enumerate(SKILLS):
            button = SemanticButton(
                skill, role="secondary", object_name="focusSkillButton"
            )
            button.setCheckable(True)
            button.setAccessibleName(f"Focus skill: {skill}")
            button.toggled.connect(self._update_skill_counter)
            self.skill_buttons[skill] = button
            skill_grid.addWidget(button, index // 2, index % 2)
        self.skill_counter = semantic_label(
            "0 / 3 selected", object_name="skillAllocationCounter", text_role="warning"
        )
        skill_box = QWidget()
        skill_box.setObjectName("focusSkillsCreationBox")
        skill_box.setAccessibleName("Starting focus skills; select exactly three")
        self.skill_box = skill_box
        skill_layout = QVBoxLayout(skill_box)
        skill_layout.setContentsMargins(0, 0, 0, 0)
        skill_layout.setSpacing(2)
        skill_layout.addLayout(skill_grid)
        skill_layout.addWidget(self.skill_counter)

        self.personality_buttons: dict[str, SemanticButton] = {}
        personality_grid = QGridLayout()
        personality_grid.setContentsMargins(0, 0, 0, 0)
        personality_grid.setSpacing(4)
        for index, personality in enumerate(PERSONALITIES):
            button = SemanticButton(
                personality, role="secondary", object_name="personalityTraitButton"
            )
            button.setCheckable(True)
            button.setAccessibleName(f"Personality trait: {personality}")
            button.setToolTip(PERSONALITY_DESCRIPTIONS[personality])
            button.toggled.connect(self._update_personality_counter)
            self.personality_buttons[personality] = button
            personality_grid.addWidget(button, index // 2, index % 2)
        self.personality_counter = semantic_label(
            "0 / 2 selected", object_name="personalityAllocationCounter", text_role="warning"
        )
        personality_box = QWidget()
        personality_layout = QVBoxLayout(personality_box)
        personality_layout.setContentsMargins(0, 0, 0, 0)
        personality_layout.setSpacing(2)
        personality_layout.addLayout(personality_grid)
        personality_layout.addWidget(self.personality_counter)
        self.primary_strength = _choice_combo("strengthCreationCombo", STRENGTHS)
        self.flaw = _choice_combo("flawCreationCombo", FLAWS)
        self.motivation = _choice_combo("motivationCreationCombo", MOTIVATIONS)
        _add_choice_tooltips(self.primary_strength, STRENGTH_DESCRIPTIONS)
        _add_choice_tooltips(self.flaw, FLAW_DESCRIPTIONS)
        _add_choice_tooltips(self.motivation, MOTIVATION_DESCRIPTIONS)

        right_form.addRow("Focus skills *", skill_box)
        right_form.addRow("Personality traits *", personality_box)
        right_form.addRow("Primary strength *", self.primary_strength)
        right_form.addRow("Meaningful flaw *", self.flaw)
        right_form.addRow("Motivation *", self.motivation)
        self._build_equipment_page(equipment_form)
        columns = QHBoxLayout()
        columns.setSpacing(7)
        columns.addWidget(appearance, 3)
        columns.addWidget(role, 2)
        columns.addWidget(equipment, 2)
        page_layout.addLayout(columns)
        page_layout.addStretch(1)
        page.setWidget(sheet)
        self.tabs.addTab(page, "2. Character Sheet")

    def _build_equipment_page(self, form: QFormLayout) -> None:
        self.equipment_fields: dict[str, FullClickComboBox] = {}
        fields = (
            ("primary_weapon", "Primary weapon *", PRIMARY_WEAPONS),
            ("secondary_weapon", "Secondary weapon", SECONDARY_WEAPONS),
            ("ranged_weapon", "Ranged weapon", RANGED_WEAPONS),
            ("armor", "Armor or clothing", ARMOR_CHOICES),
            ("shield", "Shield", SHIELD_CHOICES),
            ("important_tool", "Important tool", TOOL_CHOICES),
            ("keepsake", "Personal keepsake", KEEPSAKE_CHOICES),
        )
        for key, label, choices in fields:
            field = _choice_combo(f"{key}CreationCombo", choices)
            for index, name in enumerate(choices):
                field.setItemData(
                    index,
                    self._equipment_tooltip(name),
                    Qt.ItemDataRole.ToolTipRole,
                )
            field.currentTextChanged.connect(
                lambda text, combo=field: self._show_equipment_details(combo, text)
            )
            self._show_equipment_details(field, field.currentText())
            self.equipment_fields[key] = field
            form.addRow(label, field)

    def _build_ability_scores(self, layout: QVBoxLayout) -> None:
        self.ability_scores = {name: 8 for name in ABILITY_NAMES}
        self.ability_value_labels: dict[str, QLabel] = {}
        self.ability_modifier_labels: dict[str, QLabel] = {}
        self.ability_minus_buttons: dict[str, SemanticButton] = {}
        self.ability_plus_buttons: dict[str, SemanticButton] = {}
        header = QHBoxLayout()
        header.addWidget(semantic_label("ABILITY SCORES", text_role="accent"))
        header.addStretch(1)
        self.hit_points_preview = semantic_label("", text_role="secondary")
        self.points_left_label = semantic_label(
            "POINTS LEFT: 27", object_name="abilityPointsLeft", text_role="warning"
        )
        header.addWidget(self.hit_points_preview)
        header.addWidget(self.points_left_label)
        layout.addLayout(header)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(5)
        for column, name in enumerate(ABILITY_NAMES):
            card = ThemedFrame("characterSheetAttribute", role="section")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(5, 4, 5, 5)
            card_layout.setSpacing(1)
            title = semantic_label(name.upper(), text_role="muted")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value = semantic_label(
                "8", object_name="characterSheetAttributeValue", text_role="heading"
            )
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            modifier = semantic_label(
                "-1", object_name="characterSheetModifier", text_role="accent"
            )
            modifier.setAlignment(Qt.AlignmentFlag.AlignCenter)
            controls = QHBoxLayout()
            minus = SemanticButton(
                "−", role="secondary", object_name="abilityScoreMinusButton"
            )
            plus = SemanticButton(
                "+", role="secondary", object_name="abilityScorePlusButton"
            )
            minus.setAccessibleName(f"Decrease {name}")
            plus.setAccessibleName(f"Increase {name}")
            minus.setFixedWidth(34)
            plus.setFixedWidth(34)
            minus.clicked.connect(
                lambda _checked=False, ability=name: self._change_ability(ability, -1)
            )
            plus.clicked.connect(
                lambda _checked=False, ability=name: self._change_ability(ability, 1)
            )
            controls.addStretch(1)
            controls.addWidget(minus)
            controls.addWidget(plus)
            controls.addStretch(1)
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            card_layout.addWidget(modifier)
            card_layout.addLayout(controls)
            grid.addWidget(card, 0, column)
            grid.setColumnStretch(column, 1)
            self.ability_value_labels[name] = value
            self.ability_modifier_labels[name] = modifier
            self.ability_minus_buttons[name] = minus
            self.ability_plus_buttons[name] = plus
        layout.addLayout(grid)
        self._update_ability_controls()

    def _change_ability(self, name: str, change: int) -> None:
        candidate = self.ability_scores[name] + change
        if not 8 <= candidate <= 15:
            return
        scores = dict(self.ability_scores)
        scores[name] = candidate
        if point_buy_spent(tuple(scores.items())) > 27:
            return
        self.ability_scores[name] = candidate
        self._update_ability_controls()

    def _update_ability_controls(self) -> None:
        spent = point_buy_spent(tuple(self.ability_scores.items()))
        points_left = 27 - spent
        for name, score in self.ability_scores.items():
            self.ability_value_labels[name].setText(str(score))
            self.ability_modifier_labels[name].setText(f"{ability_modifier(score):+d}")
            self.ability_minus_buttons[name].setEnabled(score > 8)
            candidate = dict(self.ability_scores)
            candidate[name] = score + 1
            self.ability_plus_buttons[name].setEnabled(
                score < 15 and point_buy_spent(tuple(candidate.items())) <= 27
            )
        self.points_left_label.setText(f"POINTS LEFT: {points_left}")
        self.points_left_label.setProperty(
            "textRole", "success" if points_left == 0 else "warning"
        )
        self.points_left_label.style().unpolish(self.points_left_label)
        self.points_left_label.style().polish(self.points_left_label)
        self._update_class_details(self.character_class.currentText())
        if hasattr(self, "complete_button"):
            self._update_complete_button()

    def _class_tooltip(self, name: str) -> str:
        details = CLASS_DETAILS[name]
        constitution = self.ability_scores.get("Constitution", 8)
        return "\n".join((
            name,
            str(details["role"]),
            f"Hit die: d{details['hit_die']}",
            f"Primary abilities: {details['primary']}",
            f"Saving throws: {details['saves']}",
            f"Armor: {details['armor']}",
            f"Weapons: {details['weapons']}",
            f"Level 1 HP with Constitution {constitution}: "
            f"{level_one_hit_points(name, constitution)}",
        ))

    def _update_class_details(self, name: str) -> None:
        if not hasattr(self, "ability_scores") or name not in CLASS_DETAILS:
            return
        for index, class_name in enumerate(CLASSES):
            self.character_class.setItemData(
                index, self._class_tooltip(class_name), Qt.ItemDataRole.ToolTipRole
            )
        self.character_class.setToolTip(self._class_tooltip(name))
        constitution = self.ability_scores["Constitution"]
        self.hit_points_preview.setText(
            f"LEVEL 1 HP: {level_one_hit_points(name, constitution)}"
        )

    @staticmethod
    def _show_equipment_details(combo: FullClickComboBox, name: str) -> None:
        combo.setToolTip(CharacterCreationPanel._equipment_tooltip(name))

    @staticmethod
    def _equipment_tooltip(name: str) -> str:
        if not name.strip() or name == "None":
            return "No item selected."
        definition = item_definition(name)
        details = [name, f"Type: {definition.item_type.title()}"]
        slots = definition.compatible_slots or ((definition.equip_slot,) if definition.equip_slot else ())
        if slots:
            details.append(f"Compatible slot: {', '.join(slots)}")
        if definition.damage:
            details.append(f"Damage: {definition.damage}")
        if definition.armor:
            details.append(f"Armor: {definition.armor}")
        if definition.maximum_charges is not None:
            details.append(f"Charges: {definition.charges}/{definition.maximum_charges}")
        if definition.consumable:
            details.append("Consumable")
        details.append(f"Weight: {definition.weight:g} | Value: {definition.value_gp} gp")
        if definition.description:
            details.append(definition.description)
        return "\n".join(details)

    def _build_campaign_page(self) -> None:
        page, world_form, details_form = self._two_column_page(
            "campaign",
            "SECTION 3 — WORLD & SAFETY",
            "SECTION 4 — CAMPAIGN DETAILS",
        )
        self._world_form = world_form
        self._details_form = details_form
        self.world_type = _choice_combo("worldTypeCreationCombo", WORLD_TYPES)
        self.tone = _choice_combo("toneCreationCombo", TONES)
        self.region = _choice_combo("regionCreationCombo", REGIONS)
        self.location = _choice_combo("locationCreationCombo", LOCATIONS)
        self.difficulty = _choice_combo("difficultyCreationCombo", DIFFICULTIES)
        self.content_preferences = _text_area(
            "contentPreferencesInput",
            "Optional — a balanced default profile is used when blank",
            105,
        )
        self.content_preferences.setToolTip(f"Default: {DEFAULT_CONTENT_PREFERENCES}")
        self.visual_style = _choice_combo("visualStyleCreationCombo", VISUAL_STYLES)
        self.camera_style = _choice_combo("cameraStyleCreationCombo", CAMERA_STYLES)
        for label, widget in (
            ("World type *", self.world_type), ("World tone *", self.tone),
            ("Starting region *", self.region), ("Starting location *", self.location),
            ("Difficulty *", self.difficulty), ("Content preferences", self.content_preferences),
            ("Visual art style *", self.visual_style), ("Camera style *", self.camera_style),
        ):
            world_form.addRow(label, widget)
        self.preset_selector = FullClickComboBox()
        self.preset_selector.setObjectName("campaignPresetSelector")
        self.preset_selector.addItem("Custom Campaign", "")
        for label, preset_id in preset_choices():
            self.preset_selector.addItem(label, preset_id)
        self.preset_selector.setToolTip(
            "Choose a freeform campaign or a packaged campaign with authored quests and lore."
        )
        details_form.addRow("Campaign source *", self.preset_selector)
        self.campaign_name, campaign_name_row = self._randomizable_text_field(
            "campaign_name", "campaignNameInput", "Campaign name"
        )
        self._campaign_name_row = campaign_name_row
        details_form.addRow("Campaign name *", campaign_name_row)
        self.randomize_campaign_button = SemanticButton(
            "Randomize Campaign", role="primary", object_name="randomizeCampaignButton"
        )
        self.randomize_campaign_button.setToolTip(
            "Generate campaign details from all completed character and world selections"
        )
        self.randomize_campaign_button.clicked.connect(self._request_campaign_randomization)
        details_form.addRow("", self.randomize_campaign_button)
        self.campaign_description = _text_area(
            "campaignDescriptionInput",
            "The generated campaign premise appears here and may be edited before creation",
            180,
        )
        details_form.addRow("Campaign premise *", self.campaign_description)
        self.preset_selector.currentIndexChanged.connect(self._preset_changed)
        self.tabs.addTab(page, "3. Campaign")

    def begin_creation(self, preset_id: str = "") -> None:
        """Enter custom or preset creation without duplicating the form."""

        self._preset_only_mode = bool(preset_id)
        self.preset_selector.blockSignals(True)
        self.preset_selector.clear()
        if not self._preset_only_mode:
            self.preset_selector.addItem("Custom Campaign", "")
        for label, available_id in preset_choices():
            self.preset_selector.addItem(label, available_id)
        index = self.preset_selector.findData(preset_id)
        self.preset_selector.setCurrentIndex(max(0, index))
        self.preset_selector.blockSignals(False)
        self._preset_changed(self.preset_selector.currentIndex())
        self.tabs.setCurrentIndex(0)

    def _preset_changed(self, _index: int) -> None:
        preset_id = str(self.preset_selector.currentData() or "")
        is_preset = bool(preset_id)
        for field in (
            self.world_type,
            self.tone,
            self.region,
            self.location,
            self.content_preferences,
        ):
            self._world_form.setRowVisible(field, not is_preset)
        self._details_form.setRowVisible(self._campaign_name_row, not is_preset)
        allow_generation = not is_preset
        self.randomize_campaign_button.setEnabled(allow_generation)
        self.randomize_buttons["campaign_name"].setEnabled(allow_generation)
        self.campaign_name.setReadOnly(is_preset)
        self.campaign_description.setReadOnly(is_preset)
        if is_preset:
            preset = load_preset(preset_id)
            self.campaign_name.setText(str(preset["name"]))
            self.campaign_description.setPlainText(str(preset["premise"]))
            self.error_label.setText(
                f"Loaded {preset['display_name']}. Character and safety selections remain yours."
            )
        else:
            self.error_label.clear()

    def _build_review_page(self) -> None:
        scroll = QScrollArea()
        scroll.setObjectName("reviewCreationScroll")
        scroll.setProperty("creationSurface", True)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        page = QWidget()
        page.setObjectName("reviewCreationPage")
        page.setProperty("creationSurface", True)
        outer = QHBoxLayout(page)
        outer.setContentsMargins(18, 8, 18, 8)
        outer.addStretch(1)
        host = QWidget()
        host.setObjectName("reviewCreationCards")
        self.review_cards_layout = QVBoxLayout(host)
        self.review_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.review_cards_layout.setSpacing(8)
        self.review_cards_layout.addWidget(
            semantic_label(
                "SECTION 5 — FINAL REVIEW",
                object_name="creationSectionTitle",
                text_role="accent",
            )
        )
        self.review_cards_marker = self.review_cards_layout.count()
        self._rendered_review_cards: list[ThemedFrame] = []
        outer.addWidget(host, 3)
        outer.addStretch(1)
        self.review_confirmed = QCheckBox("I confirm this complete written character profile.")
        self.review_confirmed.setObjectName("characterReviewConfirmation")
        self.review_cards_layout.addWidget(self.review_confirmed)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "4. Final Review")

    def _review_card(
        self,
        title: str,
        rows: tuple[tuple[str, str], ...],
        narratives: tuple[tuple[str, str], ...] = (),
    ) -> ThemedFrame:
        card = ThemedFrame(
            f"review{title.replace(' ', '').replace('&', 'And')}Card", role="content"
        )
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QGridLayout(card)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(5)
        heading = semantic_label(title.upper(), text_role="accent")
        layout.addWidget(heading, 0, 0, 1, 4)
        for index in range(0, len(rows), 2):
            row = 1 + index // 2
            for pair, (label, value) in enumerate(rows[index:index + 2]):
                label_widget = semantic_label(f"{label}:", text_role="secondary")
                value_widget = QLabel(value or "Not provided")
                value_widget.setObjectName("characterCreationReviewTableValue")
                value_widget.setWordWrap(True)
                value_widget.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                layout.addWidget(label_widget, row, pair * 2)
                layout.addWidget(value_widget, row, pair * 2 + 1)
        row = 1 + (len(rows) + 1) // 2
        for label, value in narratives:
            layout.addWidget(semantic_label(f"{label}:", text_role="secondary"), row, 0, 1, 4)
            row += 1
            text = QLabel(value or "Not provided")
            text.setObjectName("characterCreationReviewNarrative")
            text.setWordWrap(True)
            text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(text, row, 0, 1, 4)
            row += 1
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        return card

    def _selected(self, widget: QListWidget) -> tuple[str, ...]:
        return tuple(item.text() for item in widget.selectedItems())

    def _selected_skills(self) -> tuple[str, ...]:
        return tuple(
            skill for skill, button in self.skill_buttons.items() if button.isChecked()
        )

    def _selected_personalities(self) -> tuple[str, ...]:
        return tuple(
            trait
            for trait, button in self.personality_buttons.items()
            if button.isChecked()
        )

    def draft(self) -> CharacterCreationDraft:
        equipment = {
            key: "" if field.currentText() == "None" else field.currentText()
            for key, field in self.equipment_fields.items()
        }
        return CharacterCreationDraft(
            campaign_name=self.campaign_name.text(), name=self.character_name.text(),
            ancestry=self.ancestry.currentText(), age=self.age.value(),
            gender_identity=self.gender.text(), pronouns=self.pronouns.text(),
            body_description=self.body.toPlainText(), face_description=self.face.toPlainText(),
            clothing_style=self.clothing.toPlainText(), background=self.background.currentText(),
            character_class=self.character_class.currentText(), **equipment,
            personalities=self._selected_personalities(),
            primary_strength=self.primary_strength.currentText(),
            meaningful_flaw=self.flaw.currentText(), motivation=self.motivation.currentText(),
            biography=self.biography.toPlainText(), backstory="",
            skills=self._selected_skills(), world_type=self.world_type.currentText(),
            tone=self.tone.currentText(), starting_region=self.region.currentText(),
            starting_location=self.location.currentText(), difficulty=self.difficulty.currentText(),
            content_preferences=(
                self.content_preferences.toPlainText().strip()
                or DEFAULT_CONTENT_PREFERENCES
            ),
            visual_style=self.visual_style.currentText(), camera_style=self.camera_style.currentText(),
            campaign_description=self.campaign_description.toPlainText(),
            ability_scores=tuple(self.ability_scores.items()),
            preset_id=str(self.preset_selector.currentData() or ""),
        )

    def _update_skill_counter(self, _checked: bool = False) -> None:
        selected = self._selected_skills()
        count = len(selected)
        for skill, button in self.skill_buttons.items():
            button.set_selected(skill in selected)
            button.setEnabled(count < 3 or skill in selected)
            button.setText(f"✓ {skill}" if skill in selected else skill)
        self.skill_counter.setText(f"{count} / 3 selected")
        self.skill_counter.setProperty("textRole", "success" if count == 3 else "warning")
        self.skill_counter.style().unpolish(self.skill_counter)
        self.skill_counter.style().polish(self.skill_counter)

    def _set_skill_selection(self, selected: tuple[str, ...]) -> None:
        for skill, button in self.skill_buttons.items():
            button.blockSignals(True)
            button.set_selected(skill in selected)
            button.blockSignals(False)
        self._update_skill_counter()

    def _update_personality_counter(self, _checked: bool = False) -> None:
        selected = self._selected_personalities()
        count = len(selected)
        for trait, button in self.personality_buttons.items():
            button.set_selected(trait in selected)
            button.setEnabled(count < 2 or trait in selected)
            button.setText(f"✓ {trait}" if trait in selected else trait)
        self.personality_counter.setText(f"{count} / 2 selected")
        self.personality_counter.setProperty(
            "textRole", "success" if count in (1, 2) else "warning"
        )
        self.personality_counter.style().unpolish(self.personality_counter)
        self.personality_counter.style().polish(self.personality_counter)

    def _request_randomization(self, section: str) -> None:
        button = self.randomize_buttons[section]
        if self.randomizer is None:
            self.error_label.setText(
                "LM Studio randomization is unavailable in this application session."
            )
            return
        button.setEnabled(False)
        button.setText("Generating...")
        self.error_label.setText("Generating three local options with LM Studio...")
        task = RandomizationTask(self.randomizer, section, self.draft())
        self._randomization_tasks.add(task)
        task.signals.succeeded.connect(self._show_generated_options)
        task.signals.failed.connect(self._randomization_failed)
        task.signals.finished.connect(
            lambda target, worker=task: self._randomization_finished(target, worker)
        )
        self.thread_pool.start(task)

    def _request_campaign_randomization(self) -> None:
        if self.randomizer is None:
            self.error_label.setText(
                "LM Studio randomization is unavailable in this application session."
            )
            return
        if self._campaign_randomization_task is not None:
            return
        self.randomize_campaign_button.setEnabled(False)
        self.randomize_campaign_button.setText("Generating...")
        self.error_label.setText(
            "Generating a campaign from the selected World & Safety profile..."
        )
        task = CampaignRandomizationTask(self.randomizer, self.draft())
        self._campaign_randomization_task = task
        task.signals.succeeded.connect(self._apply_generated_campaign)
        task.signals.failed.connect(self._campaign_randomization_failed)
        task.signals.finished.connect(self._campaign_randomization_finished)
        self.thread_pool.start(task)

    def _apply_generated_campaign(self, generated: object) -> None:
        if not isinstance(generated, CharacterCreationDraft):
            self._campaign_randomization_failed("LM Studio returned an invalid campaign.")
            return
        self.campaign_name.setText(generated.campaign_name)
        self.campaign_description.setPlainText(generated.campaign_description)
        self.error_label.setText(
            "Campaign generated. Your character, equipment, and World & Safety selections "
            "were preserved."
        )

    def _campaign_randomization_failed(self, message: str) -> None:
        self.error_label.setText(message)

    def _campaign_randomization_finished(self) -> None:
        self._campaign_randomization_task = None
        self.randomize_campaign_button.setText("Randomize Campaign")
        self.randomize_campaign_button.setEnabled(
            not bool(self.preset_selector.currentData())
        )

    def _show_generated_options(self, section: str, raw_options: object) -> None:
        if not isinstance(raw_options, tuple) or len(raw_options) != 3:
            self._randomization_failed(section, "LM Studio returned invalid options.")
            return
        labels = {
            "campaign_name": "Campaign Name",
            "character_name": "Character Name",
            "body_description": "Body and Height",
            "face_description": "Face and Features",
            "clothing_style": "Clothing Style",
            "biography": "Biography/Backstory",
            "backstory": "Biography/Backstory",
        }
        dialog = OptionSelectionDialog(labels[section], raw_options, self)
        result = dialog.exec()
        if result == getattr(OptionSelectionDialog, "RETRY_RESULT", 2):
            QTimer.singleShot(0, lambda target=section: self._request_randomization(target))
        elif result == OptionSelectionDialog.DialogCode.Accepted:
            selected = dialog.selected_option()
            if selected:
                self.apply_generated_option(section, selected)
                self.error_label.setText(f"Applied generated {labels[section].lower()} option.")

    def apply_generated_option(self, section: str, option: str) -> None:
        """Apply an explicitly selected option without changing any other field."""

        field = self.randomized_fields[section]
        if isinstance(field, QLineEdit):
            field.setText(option)
        else:
            field.setPlainText(option)
        field.setProperty("validationState", "valid")
        field.style().unpolish(field)
        field.style().polish(field)

    def _randomization_failed(self, _section: str, message: str) -> None:
        self.error_label.setText(message)

    def _randomization_finished(
        self,
        section: str,
        task: RandomizationTask,
    ) -> None:
        self._randomization_tasks.discard(task)
        button = self.randomize_buttons.get(section)
        if button is not None:
            button.setText("Randomize")
            button.setEnabled(True)

    def _tab_changed(self, index: int) -> None:
        if index == self.tabs.count() - 1:
            self._render_review()

    def _render_review(self) -> None:
        draft = self.draft()
        for card in self._rendered_review_cards:
            self.review_cards_layout.removeWidget(card)
            card.deleteLater()
        equipment_rows = (
            ("Primary weapon", draft.primary_weapon),
            ("Secondary weapon", draft.secondary_weapon or "None"),
            ("Ranged weapon", draft.ranged_weapon or "None"),
            ("Armor", draft.armor or "None"),
            ("Shield", draft.shield or "None"),
            ("Important tool", draft.important_tool or "None"),
            ("Keepsake", draft.keepsake or "None"),
        )
        cards = [
            self._review_card(
                "Appearance & Identity",
                (
                    ("Name", draft.name or "Unnamed Character"),
                    ("Ancestry", draft.ancestry),
                    ("Age", str(draft.age)),
                    ("Gender", draft.gender_identity or "Unspecified"),
                    ("Pronouns", draft.pronouns or "Unspecified"),
                ),
                (
                    ("Body & height", draft.body_description),
                    ("Face & features", draft.face_description),
                    ("Clothing", draft.clothing_style),
                    ("Biography/Backstory", draft.biography or draft.backstory),
                ),
            ),
            self._review_card(
                "Role & Skills",
                (
                    ("Class", draft.character_class),
                    ("Background", draft.background),
                    ("Focus skills", ", ".join(draft.skills) or "None selected"),
                    ("Personality", ", ".join(draft.personalities) or "None selected"),
                    ("Strength", draft.primary_strength),
                    ("Flaw", draft.meaningful_flaw),
                    ("Motivation", draft.motivation),
                ),
            ),
            self._review_card(
                "Ability Scores",
                tuple(
                    (name, f"{score} ({ability_modifier(score):+d})")
                    for name, score in draft.ability_scores
                ) + ((
                    "Level 1 HP",
                    str(level_one_hit_points(
                        draft.character_class, dict(draft.ability_scores)["Constitution"]
                    )),
                ),),
            ),
            self._review_card("Equipment", equipment_rows),
            self._review_card(
                "World & Safety",
                (
                    ("World type", draft.world_type),
                    ("Tone", draft.tone),
                    ("Starting region", draft.starting_region),
                    ("Starting location", draft.starting_location),
                    ("Difficulty", draft.difficulty),
                    ("Visual style", draft.visual_style),
                    ("Camera style", draft.camera_style),
                ),
                (("Content preferences", draft.content_preferences),),
            ),
            self._review_card(
                "Campaign Details",
                (
                    ("Campaign name", draft.campaign_name or "Unnamed Campaign"),
                    ("Campaign source", "Preset campaign" if draft.preset_id else "Custom campaign"),
                ),
                (("Campaign premise", draft.campaign_description),),
            ),
        ]
        confirmation_index = self.review_cards_layout.indexOf(self.review_confirmed)
        for offset, card in enumerate(cards):
            self.review_cards_layout.insertWidget(confirmation_index + offset, card)
        self._rendered_review_cards = cards

    def _complete(self) -> None:
        draft = self.draft()
        errors = CharacterCreationValidator.validate(draft)
        if errors:
            field, message = next(iter(errors.items()))
            self.tabs.setCurrentIndex(self.TAB_FIELDS.get(field, 0))
            self.error_label.setText(f"{field.replace('_', ' ').title()}: {message}")
            self.error_label.setAccessibleName("Character creation validation error")
            self._focus_invalid_field(field)
            return
        if not self.review_confirmed.isChecked():
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
            self._render_review()
            self.error_label.setText("Review and confirm the written profile before creation.")
            self.review_confirmed.setFocus()
            return
        self.error_label.clear()
        self.completed.emit(draft)

    def _focus_invalid_field(self, field: str) -> None:
        widgets = {
            "campaign_name": self.campaign_name, "name": self.character_name,
            "ancestry": self.ancestry, "age": self.age,
            "body_description": self.body, "face_description": self.face,
            "clothing_style": self.clothing, "background": self.background,
            "character_class": self.character_class, "skills": self.skill_box,
            "ability_scores": self.points_left_label,
            "primary_weapon": self.equipment_fields["primary_weapon"],
            "personalities": next(iter(self.personality_buttons.values())),
            "primary_strength": self.primary_strength,
            "meaningful_flaw": self.flaw, "motivation": self.motivation,
            "biography": self.biography, "backstory": self.backstory,
            "world_type": self.world_type, "tone": self.tone,
            "starting_region": self.region, "starting_location": self.location,
            "difficulty": self.difficulty,
            "content_preferences": self.content_preferences,
            "campaign_description": self.campaign_description,
            "visual_style": self.visual_style, "camera_style": self.camera_style,
        }
        widget = widgets.get(field)
        if widget is not None:
            widget.setProperty("validationState", "error")
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.setFocus()
