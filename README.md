# Automatic Cloze Cards Add-on for Anki

This Anki add-on automates the creation of cloze deletion cards from your notes.

## Features

* Automatically generates cloze cards.
* Configuration options to customize the cloze generation process.

## Configuration

The add-on's settings can be found in Anki:

1.  Go to "Tools" -> "Add-ons".
2.  Select "Automatic cloze cards"
3.  Click on "Config".

## Advanced Configuration

For advanced users:

* The main logic of the add-on is located in the `change_logic.py` file.
* You can uncomment the last part of the `change_logic.py` file if you want to have the settings/configuration options directly accessible in the "Tools" menu. This provides a more direct way to access the add-on's settings.

## Usage

1.  **Configure Source and Target Card Types:** In the add-on's configuration, you can specify multiple source card types and one target card type.
2.  **Create Cloze Deletions:** When creating a note using one of the source card types, include cloze deletions in your text (e.g., `{{c1::example}}`).
3.  **Automatic Conversion:** Even if you initially select a basic card type, the add-on will automatically convert the note to the cloze card type specified as the target in the configuration when the note is added.

## Installation

1.  (Describe the installation steps.  This might involve getting the add-on from AnkiWeb or installing from a file.)
2.  ...

## Dependencies

* `re`
* `time`
* `typing` (`Optional`, `List`, `Dict`, `Any`)
* `anki` (`version as anki_version`, `errors.NotFoundError`, `hooks.wrap`, `notes.Note`)
* `aqt` (`gui_hooks`, `mw`, `editor.Editor`, `utils.showWarning`)

## Contributing

Contributions are welcome! Please submit pull requests to suggest improvements or new features.
