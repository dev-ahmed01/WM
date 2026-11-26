"""Politeness / 'what should I do' filler must not dilute the words that carry the problem (found by the real-browser
voice test: the long spoken sentence was refused while its short form found the Barcode scanner SOP)."""
from app.core.text_matching import search_terms


def test_filler_words_do_not_survive_tokenisation():
    spoken = search_terms("स्कैनर काम नहीं कर रहा है, मुझे क्या करना चाहिए?")
    short = search_terms("स्कैनर काम नहीं कर रहा है")
    assert spoken == short
    assert "चाहिए" not in spoken and "स्कैनर" in spoken and "काम" in spoken


def test_meaningful_hindi_words_are_kept():
    terms = search_terms("पैलेट पर लेबल नहीं है")
    assert "पैलेट" in terms and "लेबल" in terms and "नहीं" in terms
