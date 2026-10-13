"""Read a saved job description: an optional JSON header (fields from the job feed) followed
by the posting text. A plain-text file with no header also works."""
import json


def load(path):
    return parse(open(path).read())


def parse(raw):
    """(meta dict, posting text)."""
    s = raw.lstrip()
    if s.startswith("{"):
        try:
            meta, end = json.JSONDecoder().raw_decode(s)
            return meta, s[end:].strip()
        except ValueError:
            pass
    return {}, raw.strip()
