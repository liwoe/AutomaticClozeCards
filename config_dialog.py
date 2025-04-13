from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QWidget, QScrollArea, QGroupBox, Qt # Added for alignment
)
from aqt.utils import tooltip, showInfo, askUser # For user feedback

# --- Configuration Keys ---
CONFIG_KEY_TARGET_MODEL = "target_model_id"
CONFIG_KEY_SOURCE_MODELS = "source_model_ids" # List of source model IDs
ADDON_IDENTIFIER = mw.addonManager.addonFromModule(__name__)

class ConfigDialog(QDialog):
    def __init__(self):
        super().__init__(mw) # Parent dialog to main window
        self.setWindowTitle("Configure Note Type Change (Simple)")
        self.config = mw.addonManager.getConfig(ADDON_IDENTIFIER) or {} # Ensure config is a dict
        self.all_models = mw.col.models.all() # Get list of model dicts
        self.target_model_id = None
        self.source_widgets = [] # Holds tuples of (container_widget, combo_box)

        # Sort models by name for UI consistency
        self.all_models.sort(key=lambda m: m['name'])

        # --- Main Layout ---
        layout = QVBoxLayout()
        self.setLayout(layout)

        # --- Target Note Type Selection ---
        target_group = QGroupBox("1. Select Target Note Type")
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Change selected notes to:"))
        self.target_combo = QComboBox()
        self.target_combo.setPlaceholderText("Select Target...")
        self.target_combo.addItem("", None) # Placeholder
        for model in self.all_models:
            self.target_combo.addItem(model['name'], model['id'])
        self.target_combo.currentIndexChanged.connect(self.target_model_selected)
        target_layout.addWidget(self.target_combo, 1)
        target_group.setLayout(target_layout)
        layout.addWidget(target_group)

        # --- Source Note Type Selection Area ---
        source_group = QGroupBox("2. Select Source Note Types to Convert")
        source_main_layout = QVBoxLayout()
        source_group.setLayout(source_main_layout)

        # Scroll Area for Source Selections
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content_widget = QWidget()
        self.sources_layout = QVBoxLayout(self.scroll_content_widget) # Layout for the source selection rows
        self.sources_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # Align widgets to the top
        self.scroll_area.setWidget(self.scroll_content_widget)
        source_main_layout.addWidget(self.scroll_area, 1) # Allow scroll area to stretch

        # Add Source Selection Button
        self.add_button = QPushButton("Add Source Note Type")
        self.add_button.clicked.connect(self.add_source_ui)
        self.add_button.setEnabled(False) # Disabled until target is selected
        source_main_layout.addWidget(self.add_button)

        layout.addWidget(source_group, 1) # Allow source group to stretch

        # --- Action Buttons ---
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save Configuration")
        self.save_button.clicked.connect(self.save_config)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject) # Closes dialog without saving

        button_layout.addStretch(1) # Push buttons right
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.save_button)
        layout.addLayout(button_layout)

        # --- Load existing config ---
        self.load_config()

        self.setMinimumWidth(450) # Adjust minimum width
        self.resize(500, 400) # Adjust default size

    def get_available_source_models(self):
        """Returns a list of models suitable for source selection (excluding the target)."""
        if self.target_model_id is None:
            return []
        return [m for m in self.all_models if m['id'] != self.target_model_id]

    def target_model_selected(self, index):
        """Update UI when target model changes."""
        selected_id = self.target_combo.itemData(index)
        if selected_id == self.target_model_id:
            return # No change

        # If target changed and sources exist, confirm clearing them
        if selected_id and self.source_widgets:
             if not askUser(f"Changing the target note type requires clearing the current source selections. Proceed?"):
                  # User cancelled, revert selection
                  self.target_combo.blockSignals(True) # Prevent recursion
                  current_index = -1
                  for i in range(self.target_combo.count()):
                        if self.target_combo.itemData(i) == self.target_model_id:
                             current_index = i
                             break
                  self.target_combo.setCurrentIndex(current_index)
                  self.target_combo.blockSignals(False)
                  return


        previous_target_id = self.target_model_id
        self.target_model_id = selected_id

        if self.target_model_id:
            self.add_button.setEnabled(True)
            # Clear existing source selections if target changed
            if previous_target_id is not None and previous_target_id != self.target_model_id:
                 self.clear_all_sources()
                 tooltip("Source selections cleared because target note type changed.")
        else:
            # No target selected
            self.add_button.setEnabled(False)
            # Clear existing sources as they are now invalid
            if self.source_widgets:
                 self.clear_all_sources()
                 tooltip("Source selections cleared because target note type was unselected.")


    def add_source_ui(self, source_id_to_select=None):
        """Adds a new row for selecting a source note type."""
        if self.target_model_id is None:
             tooltip("Please select a target note type first.")
             return

        available_sources = self.get_available_source_models()
        if not available_sources:
            tooltip("No other note types available to select as source.")
            return

        source_widget = QWidget()
        row_layout = QHBoxLayout(source_widget)
        row_layout.setContentsMargins(0,0,0,0) # Compact layout

        source_combo = QComboBox()
        source_combo.setPlaceholderText("Select Source...")
        source_combo.addItem("", None) # Placeholder
        for model in available_sources:
            source_combo.addItem(model['name'], model['id'])

        remove_button = QPushButton("Remove")

        row_layout.addWidget(source_combo, 1) # Allow combo to stretch
        row_layout.addWidget(remove_button)

        # Store references BEFORE connecting signals that might use them
        widget_tuple = (source_widget, source_combo)
        self.source_widgets.append(widget_tuple)

        # Connect remove button - use lambda to pass the specific widget tuple
        remove_button.clicked.connect(lambda _, w=widget_tuple: self.remove_source_ui(w))

        self.sources_layout.addWidget(source_widget)

        # If loading config, select the appropriate item
        if source_id_to_select:
            for i in range(source_combo.count()):
                if source_combo.itemData(i) == source_id_to_select:
                    source_combo.setCurrentIndex(i)
                    break
            else:
                # The saved source ID is no longer valid (e.g., deleted, or IS the target)
                print(f"Warning: Saved source model ID {source_id_to_select} is no longer available or valid as a source. Removing row.")
                # Remove the row we just added
                self.remove_source_ui(widget_tuple)


    def remove_source_ui(self, widget_tuple):
        """Removes a source selection row from the layout and list."""
        if widget_tuple in self.source_widgets:
            source_widget, _ = widget_tuple # Unpack the tuple
            self.source_widgets.remove(widget_tuple)
            self.sources_layout.removeWidget(source_widget)
            source_widget.deleteLater() # Clean up the widget memory

    def clear_all_sources(self):
        """Removes all source selection rows."""
        # Iterate safely while removing
        while self.source_widgets:
            widget_tuple = self.source_widgets.pop()
            source_widget, _ = widget_tuple
            self.sources_layout.removeWidget(source_widget)
            source_widget.deleteLater()

    def load_config(self):
        """Load configuration and populate the UI."""
        loaded_target_id = self.config.get(CONFIG_KEY_TARGET_MODEL)
        loaded_source_ids = self.config.get(CONFIG_KEY_SOURCE_MODELS, [])

        # Set target first (this might clear sources via signal)
        if loaded_target_id:
            for i in range(self.target_combo.count()):
                if self.target_combo.itemData(i) == loaded_target_id:
                    self.target_combo.setCurrentIndex(i) # Triggers target_model_selected
                    break
            else:
                 print(f"Warning: Saved target model ID {loaded_target_id} no longer exists.")
                 self.config[CONFIG_KEY_TARGET_MODEL] = None # Clear invalid config entry


        # Add source UIs after target is potentially set
        # Ensure target_model_selected has processed if needed (using timer)
        mw.progress.timer(0, lambda: self._load_sources(loaded_source_ids), False)


    def _load_sources(self, source_ids):
         # Make sure the target model is actually set before trying to load sources
         if not self.target_model_id:
             print("Cannot load source selections: Target model not set or invalid.")
             # Clear potentially invalid source IDs from config if target is missing
             if self.config.get(CONFIG_KEY_SOURCE_MODELS):
                 self.config[CONFIG_KEY_SOURCE_MODELS] = []
             return

         self.clear_all_sources() # Clear any defaults

         if isinstance(source_ids, list):
            for source_id in source_ids:
                 # Basic check: ensure loaded source ID is not the current target ID
                 if source_id == self.target_model_id:
                     print(f"Warning: Saved source model ID {source_id} is the same as the target. Skipping.")
                     continue
                 # Basic check: ensure model exists
                 if mw.col.models.get(source_id):
                    self.add_source_ui(source_id_to_select=source_id)
                 else:
                     print(f"Warning: Saved source model ID {source_id} no longer exists. Skipping.")

         else:
             print(f"Warning: Invalid format for '{CONFIG_KEY_SOURCE_MODELS}' in config. Expected a list.")
             self.config[CONFIG_KEY_SOURCE_MODELS] = [] # Reset to valid type

    def save_config(self):
        """Validate and save the current configuration."""
        current_target_id = self.target_combo.itemData(self.target_combo.currentIndex())

        if not current_target_id:
            showInfo("Please select a target note type.")
            return

        selected_source_ids = []
        used_source_ids = set()
        valid_config = True

        for widget_tuple in self.source_widgets:
            _, source_combo = widget_tuple # Unpack
            source_id = source_combo.itemData(source_combo.currentIndex())

            if source_id: # Check if a valid source is selected (ignore placeholders)
                # Validation 1: Source cannot be the target
                if source_id == current_target_id:
                    # This case *should* be prevented by available items, but double-check.
                    showInfo(f"Error: Source type '{source_combo.currentText()}' cannot be the same as the target type. Please remove or change it.")
                    valid_config = False
                    break

                # Validation 2: No duplicate sources
                if source_id in used_source_ids:
                    showInfo(f"Error: Source type '{source_combo.currentText()}' is selected multiple times. Please remove duplicates.")
                    valid_config = False
                    break

                used_source_ids.add(source_id)
                selected_source_ids.append(source_id)
            else:
                # A row exists but no source is selected in its dropdown
                showInfo(f"Please select a source note type in all rows or remove empty rows.")
                valid_config = False
                break

        if not valid_config:
            return # Stop saving if validation failed

        if not selected_source_ids:
             showInfo("Please add and select at least one source note type.")
             return

        # --- Save to config ---
        self.config[CONFIG_KEY_TARGET_MODEL] = current_target_id
        self.config[CONFIG_KEY_SOURCE_MODELS] = selected_source_ids

        try:
            mw.addonManager.writeConfig(__name__, self.config)
            tooltip("Configuration saved successfully.")
            self.accept() # Close the dialog
        except Exception as e:
            showInfo(f"Error saving configuration: {e}")
