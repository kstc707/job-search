"""Read the parts of a resume .tex file that the checks need: bullets, summary, skills."""
import hashlib
import re

_BOLD = re.compile(r"\\textbf\{([^}]*)\}")
_ITEM = re.compile(r"\\item\s+(.*?)(?=\\item|\\end\{itemize\})", re.S)


def clean(text):
    """Strip simple LaTeX markup and collapse whitespace."""
    text = _BOLD.sub(r"\1", text)
    text = text.replace("\\%", "%").replace("\\$", "$").replace("\\&", "&")
    text = text.replace("$-$", "-").replace("--", "-")
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def bullets(tex):
    """Every \\item in the file, cleaned, in order."""
    return [clean(b) for b in _ITEM.findall(tex)]


def summary(tex):
    m = re.search(r"\\section\*\{Professional Summary\}(.*?)\\section\*", tex, re.S)
    return clean(m.group(1)) if m else ""


def normalize(text):
    """Lowercase, numbers kept, punctuation dropped: used for IDs and similarity."""
    return re.sub(r"[^a-z0-9% ]+", "", text.lower()).strip()


def bullet_id(text):
    """Stable short ID for a bullet's wording."""
    return "b_" + hashlib.sha1(normalize(clean(text)).encode()).hexdigest()[:10]
