import re
import time
from typing import Optional, List, Dict, Any
from anki import version as anki_version
from anki.errors import NotFoundError
from anki.hooks import wrap
from anki.notes import Note
from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.utils import showWarning

# Attempt import for modern Anki versions
try:
    from aqt.gui_hooks import AddCardsDidAddNoteContext
    ADD_NOTE_HOOK = gui_hooks.add_cards_did_add_note_history
except ImportError:
    # Fallback for versions before history hook or if context isn't needed
    ADD_NOTE_HOOK = gui_hooks.add_cards_did_add_note


# Import necessary components from the config dialog module
try:
    # Assuming config_dialog.py is in the same directory
    from .config_dialog import (
        ConfigDialog,
        CONFIG_KEY_SOURCE_MODELS,
        CONFIG_KEY_TARGET_MODEL
    )
except ImportError as e:
    print(f"ERROR: Could not import ConfigDialog or config keys: {e}")
    # Define placeholders so the rest of the script *might* load, but config won't work
    ConfigDialog = None
    CONFIG_KEY_SOURCE_MODELS = "source_model_ids"
    CONFIG_KEY_TARGET_MODEL = "target_model_id"


# --- Constants and Globals ---
ANKI_VERSION_TUPLE = tuple(int(i) for i in anki_version.split("."))
CLOZE_RE = r"\{\{c\d+::.*?\}\}"

# Safely get addon identifier and load initial config
config: Optional[Dict[str, Any]] = None # Use Dict type hint
source_model_ids: List[int] = []
target_model_id: Optional[int] = None
ADDON_IDENTIFIER: Optional[str] = None # Initialize ADDON_IDENTIFIER

try:
    # Ensure mw is fully loaded before accessing addonManager
    if mw:
        ADDON_IDENTIFIER = mw.addonManager.addonFromModule(__name__)
        if ADDON_IDENTIFIER:
             config = mw.addonManager.getConfig(ADDON_IDENTIFIER)
        else:
            print("Error: Could not determine Addon Identifier.")
    else:
        print("Error: Anki's main window (mw) not available for initial config load.")

except Exception as e:
    print(f"Error getting addon identifier or initial config: {e}")
    # Proceed with defaults even if identifier/config fails, but saving/loading might not work

# Provide default values if config is None or empty
if config is None:
    config = {} # Ensure config is a dict

# Use .get() for safe access and provide defaults, using imported keys
source_model_ids = [int(mid) for mid in config.get(CONFIG_KEY_SOURCE_MODELS, []) if mid is not None]
_raw_target_id = config.get(CONFIG_KEY_TARGET_MODEL, None)
target_model_id = int(_raw_target_id) if _raw_target_id is not None else None

# --- NoteFieldsCheckResult Import ---
NoteFieldsCheckResult = None
try:
    from anki.notes import NoteFieldsCheckResult # Anki 2.1.45+
except ImportError:
    print("NoteFieldsCheckResult not available (likely Anki < 2.1.45)")
    pass

# --- MODEL_CLOZE Import ---
MODEL_CLOZE = 1
try:
    from aqt.editor import MODEL_CLOZE as EDITOR_MODEL_CLOZE
    MODEL_CLOZE = EDITOR_MODEL_CLOZE
except ImportError:
    try:
        from anki.models import MODEL_CLOZE as ANKI_MODEL_CLOZE
        MODEL_CLOZE = ANKI_MODEL_CLOZE
    except ImportError:
        print("Could not import MODEL_CLOZE constant, using default value 1.")
        pass


# --- Configuration ---
def show_config_dialog():
    """Shows the configuration dialog and updates global vars if saved."""
    global source_model_ids, target_model_id, config

    # Create the dialog -
    dialog = ConfigDialog()

    # Execute the dialog. exec() returns True if the user clicks OK/Save (dialog.accept() was called),
    # False if they click Cancel or close the window (dialog.reject() was called).
    if dialog.exec():
        # Dialog already saved the config to disk via writeConfig within its save_config method.
        # Now, update the global variables in *this* script (change_logic.py)
        # to reflect the newly saved configuration immediately, so the hooks use the new values.
        # Read the config state directly from the dialog instance *after* it closes.
        new_config = dialog.config

        if new_config:
            source_model_ids = [int(mid) for mid in new_config.get(CONFIG_KEY_SOURCE_MODELS, []) if mid is not None]
            _raw_target_id_new = new_config.get(CONFIG_KEY_TARGET_MODEL, None)
            target_model_id = int(_raw_target_id_new) if _raw_target_id_new is not None else None
            config = new_config

            # print(f"Config updated and loaded into add-on: Source MIDs={source_model_ids}, Target MID={target_model_id}")
        else:
            pass
            # print("Configuration dialog returned no config after closing successfully (This is unexpected).")

mw.addonManager.setConfigAction(__name__, show_config_dialog)

# --- Cloze Detection --- using re
def contains_cloze(note: Note) -> bool:
    if not note or not note.fields:
        return False
    try:
        for fld_content in note.fields:
            if isinstance(fld_content, str) and re.search(CLOZE_RE, fld_content, flags=re.DOTALL):
                return True
    except Exception as e:
        print(f"Error during cloze detection for note {note.id if note.id else 'new note'}: {e}")
    return False

# --- Note Type Conversion (Runs *after* successful add) ---
def on_add_note_change_type(note: Note):
    global target_model_id, source_model_ids
    # Check if configuration is valid
    if not source_model_ids:
        return
    if target_model_id is None:
        return

    current_mid = note.mid
    note_type = note.note_type()

    if not note_type or note_type["id"] not in source_model_ids: # Source Card is not in to change
        return

    if not contains_cloze(note):
        return

    target_model_dict = mw.col.models.get(target_model_id)
    if not target_model_dict:
        print(f"Error: Target model ID {target_model_id} is invalid or not found. Cannot convert note {note.id}.")
        return

    if current_mid == target_model_id:
        return

    # print(f"Auto Cloze: Found note {note.id} with source MID {current_mid} and cloze. Attempting conversion to {target_model_id}...")

    try:
        new_field_count = len(target_model_dict['flds'])
        old_fields = list(note.fields)
        old_field_count = len(old_fields)

        new_fields = [""] * new_field_count
        copy_len = min(old_field_count, new_field_count)
        for i in range(copy_len):
            new_fields[i] = old_fields[i]

        note.mid = target_model_id
        note.fields = new_fields
        note.mod = int(time.time())
        if mw and mw.col:
            note.usn = mw.col.usn()

        note.flush()
        # print(f"Note {note.id} successfully converted to MID {target_model_id} and fields adjusted.")

    except Exception as e:
        print(f"ERROR during note type conversion for note {note.id} (original MID {current_mid}) to {target_model_id}: {e}")


# --- Register Add Note Hook ---
if 'ADD_NOTE_HOOK' in locals() and ADD_NOTE_HOOK:
    ADD_NOTE_HOOK.append(on_add_note_change_type)
    print(f"Auto Cloze: Registered add note hook: {ADD_NOTE_HOOK}")
else:
    print("Auto Cloze: Could not determine appropriate add note hook.")


# --- Editor Setup: Show Cloze Button --- (This also adds the cloze shortcuts xD)
def show_cloze_button_if_source(editor: Editor):
    """Shows the cloze button in the editor if the current note type is a source type."""
    global source_model_ids
    if not source_model_ids: return

    if not editor or not hasattr(editor, 'note') or not editor.note:
        return
    current_note_type = editor.note.note_type()
    if not current_note_type:
        return

    if current_note_type["id"] not in source_model_ids:
        return

    # print(f"Editor Hook: Note type {current_note_type['id']} is a source model. Ensuring cloze button is visible.")
    try:
        if ANKI_VERSION_TUPLE >= (2, 1, 52): # Check specific version for Qt6/JS changes
            editor.web.eval(
                """
                try {
                    if (window.require) {
                         require("anki/ui").loaded.then(() =>
                             require("anki/NoteEditor").instances[0].toolbar.toolbar.show("cloze")
                         ).catch(e => console.error("AutoCloze Addon: Error showing cloze button (>=2.1.52):", e));
                     } else { console.warn("AutoCloze Addon: Require API not found (>=2.1.52)") }
                } catch (e) { console.error("AutoCloze Addon: JS Error (>=2.1.52):", e); }
                """
            )
        elif ANKI_VERSION_TUPLE >= (2, 1, 50):
             editor.web.eval(
                 """
                 try {
                     if (window.require) {
                         require("anki/ui").loaded.then(() =>
                             require("anki/NoteEditor").instances[0].toolbar.templateButtons.show("cloze")
                         ).catch(e => console.error("AutoCloze Addon: Error showing cloze button (>=2.1.50):", e));
                     } else { console.warn("AutoCloze Addon: Require API not found (>=2.1.50)") }
                 } catch (e) { console.error("AutoCloze Addon: JS Error (>=2.1.50):", e); }
                 """
             )
        elif ANKI_VERSION_TUPLE >= (2, 1, 45):
            editor.web.eval(
                """
                try {
                    if (window.$editorToolbar) {
                        $editorToolbar.then(({ templateButtons }) => templateButtons.showButton("cloze"))
                                       .catch(e => console.error("AutoCloze Addon: Error showing cloze button (>=2.1.45):", e));
                    } else { console.warn("AutoCloze Addon: $editorToolbar not found (>=2.1.45)") }
                } catch (e) { console.error("AutoCloze Addon: JS Error (>=2.1.45):", e); }
                """
            )
    except Exception as e:
        print(f"Error trying to show cloze button via JS eval: {e}")

gui_hooks.editor_did_load_note.append(show_cloze_button_if_source)


# --- Core Logic: Suppress Validation Error ---
_original_fields_check = None

if NoteFieldsCheckResult:
    # print(f"Auto Cloze: Anki version >= 2.1.45 detected. Attempting to wrap Note.fields_check.")

    def wrapped_fields_check(note_instance: Note, *_args, **_kwargs) -> NoteFieldsCheckResult:
        """Wraps Note.fields_check to suppress cloze errors for configured source models."""
        global source_model_ids # Ensure access to configured IDs

        original_result = NoteFieldsCheckResult.NORMAL
        if _original_fields_check:
             try:
                 original_result = _original_fields_check(note_instance)
             except Exception as e:
                  print(f"Error calling original Note.fields_check: {e}")
                  return original_result
        else:
             print("Warning: Original Note.fields_check not found in wrapper!")
             try:
                 original_result = Note.fields_check(note_instance)
             except Exception as e:
                 print(f"Error calling Note.fields_check directly in wrapper: {e}")
                 return NoteFieldsCheckResult.INVALID_INPUT


        try:
            note_type = mw.col.models.get(note_instance.mid)
            if not note_type:
                return original_result

            is_source_model = note_type["id"] in source_model_ids

            is_cloze_related_error = (
                original_result == NoteFieldsCheckResult.NOTETYPE_NOT_CLOZE
                or original_result == NoteFieldsCheckResult.FIELD_NOT_CLOZE
            )

            has_cloze_syntax = contains_cloze(note_instance)

            if is_source_model and is_cloze_related_error and has_cloze_syntax:
                # print(f"FieldsCheckWrap: Suppressing cloze validation error ({original_result}) for note (MID: {note_instance.mid}) because cloze syntax found in source model. Allowing add.")
                return NoteFieldsCheckResult.NORMAL
            else:
                return original_result

        except Exception as e:
             print(f"Error during fields_check suppression logic for note MID {note_instance.mid}: {e}")
             return original_result


    if hasattr(Note, 'fields_check') and not hasattr(Note, '_fields_check_original_auto_cloze'):
        _original_fields_check = Note.fields_check
        Note._fields_check_original_auto_cloze = _original_fields_check
        Note.fields_check = wrapped_fields_check
        # print("Auto Cloze: Applied wrapper to Note.fields_check.")
    elif hasattr(Note, '_fields_check_original_auto_cloze'):
        pass
        # print("Auto Cloze: Note.fields_check already wrapped by this add-on, skipping.")
    else:
        print("Auto Cloze: Could not find Note.fields_check to wrap.")


# --- Fallback/Compatibility Logic ---
elif ANKI_VERSION_TUPLE >= (2, 1, 40):
    # print("Auto Cloze: Applying compatibility hook for Editor._onCloze (Anki ~2.1.40-44)")
    if hasattr(Editor, '_onCloze'):
        def _onClozeNew_40(self: Editor, *, _old):
            global source_model_ids
            note_type = self.note.note_type()
            if not note_type: return
            model_id = note_type["id"]
            result = None
            if model_id in source_model_ids and hasattr(self, 'addMode') and self.addMode:
                model_type_backup = note_type.get("type")
                needs_restore = False
                try:
                    if model_type_backup != MODEL_CLOZE:
                        self.note.note_type()['type'] = MODEL_CLOZE
                        needs_restore = True
                    result = _old(self)
                finally:
                    if needs_restore:
                        if model_type_backup is not None:
                            self.note.note_type()['type'] = model_type_backup
                        else:
                            if 'type' in self.note.note_type():
                                del self.note.note_type()['type']
                return result
            else:
                return _old(self)

        if not hasattr(Editor, '_onCloze_wrapped_by_auto_cloze'):
            try:
                 Editor._onCloze = wrap(Editor._onCloze, _onClozeNew_40, "around")
                 Editor._onCloze_wrapped_by_auto_cloze = True
                 print("Auto Cloze: Wrapped Editor._onCloze for compatibility.")
            except Exception as e:
                 print(f"Auto Cloze: Failed to wrap Editor._onCloze: {e}")
        else:
            pass
             # print("Auto Cloze: Editor._onCloze already wrapped by this add-on, skipping.")
    else:
        pass
        # print("Auto Cloze: Editor._onCloze not found for wrapping (Anki ~2.1.40-44).")

else: # < 2.1.40
    # print("Auto Cloze: Applying compatibility hook using re.search (Anki < 2.1.40). This is fragile.")
    _oldReSearch = None
    _clozeCheckerTemplateRegex = r"\{\{(?:[^:]+?:)*cloze:"
    _re_search_hooked_by_auto_cloze = False

    def hook_re_search_if_needed():
        global _oldReSearch, _re_search_hooked_by_auto_cloze
        if _re_search_hooked_by_auto_cloze: return
        if not hasattr(re, 'search') or not callable(re.search): return
        if _oldReSearch is None:
             _oldReSearch = re.search
        def newSearch(pattern, string, flags=0):
            original_search_func = _oldReSearch or re.search
            if pattern == _clozeCheckerTemplateRegex:
                return True
            return original_search_func(pattern, string, flags)
        re.search = newSearch
        _re_search_hooked_by_auto_cloze = True

    def unhook_re_search_if_hooked():
        global _oldReSearch, _re_search_hooked_by_auto_cloze
        if _re_search_hooked_by_auto_cloze and _oldReSearch:
            re.search = _oldReSearch
            _oldReSearch = None
            _re_search_hooked_by_auto_cloze = False

    if hasattr(Editor, '_onCloze'):
        def _onClozeNew_old(self: Editor, *, _old):
            global source_model_ids
            note_type = self.note.note_type()
            if not note_type: return
            model_id = note_type["id"]
            result = None
            was_hooked = False
            if model_id in source_model_ids and hasattr(self, 'addMode') and self.addMode:
                template_has_cloze_format = False
                try:
                    for tmpl in note_type.get('tmpls', []):
                        if re.search(_clozeCheckerTemplateRegex, tmpl.get('qfmt', '')):
                            template_has_cloze_format = True; break
                        if re.search(_clozeCheckerTemplateRegex, tmpl.get('afmt', '')):
                            template_has_cloze_format = True; break
                except Exception: pass
                if not template_has_cloze_format:
                    hook_re_search_if_needed()
                    was_hooked = True
            try:
                result = _old(self)
            finally:
                if was_hooked:
                    unhook_re_search_if_hooked()
            return result

        if not hasattr(Editor, '_onCloze_wrapped_by_auto_cloze'):
            try:
                 Editor._onCloze = wrap(Editor._onCloze, _onClozeNew_old, "around")
                 Editor._onCloze_wrapped_by_auto_cloze = True
                 print("Auto Cloze: Wrapped Editor._onCloze for compatibility (< 2.1.40).")
            except Exception as e:
                 print(f"Auto Cloze: Failed to wrap Editor._onCloze (< 2.1.40): {e}")
        else:
            pass
            # print("Auto Cloze: Editor._onCloze already wrapped by this add-on, skipping.")
    else:
        pass
        # print("Auto Cloze: Editor._onCloze not found for wrapping (Anki < 2.1.40).")


# --- Add Menu Item --- (uncomment if you want this)
"""
try:
    # Ensure mw and mw.form are available
    if mw and hasattr(mw, 'form') and mw.form:
         action = mw.form.menuTools.addAction("Automatic Cloze Options")
         action.triggered.connect(show_config_dialog)
         print("Auto Cloze: Added configuration menu item.")
    else:
        print("Auto Cloze: Could not add menu item (mw.form not available yet?).")
except Exception as e:
    print(f"Auto Cloze: Failed to add menu item: {e}")
"""