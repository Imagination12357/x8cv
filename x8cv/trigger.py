"""Parse a complete filename-plus-Enter command; no GTK or filesystem access.

Returns the exact .x8cv basename, or None for ordinary document contents.
The Xed plugin resolves the returned name in its configured video directory.
LIST_TRIGGER is the separate exact command for displaying that directory.
"""

LIST_TRIGGER = ":videos\n"


def parse_trigger(text):
    if not text.endswith("\n") or text.count("\n") != 1:
        return None
    filename = text[:-1]
    if not filename.endswith(".x8cv"):
        return None
    if any(char in filename for char in ("/", "\\", "\r", "\x00")):
        return None
    return filename
