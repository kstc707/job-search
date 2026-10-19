"""Our own application-form filler for public ATS forms (Greenhouse first).

Three layers, the same split commercial autofill tools use:
- schema:  what the form asks (read from the ATS's public job API, not guessed from HTML)
- answers: which approved answer goes in each field, or why it cannot be answered
- greenhouse: drive a real browser to fill, verify, screenshot and (only on request) submit
"""
