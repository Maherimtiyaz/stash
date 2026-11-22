import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_keyword_sorting():
    from app.categories import guess
    assert guess("Push pull legs split for the gym") == "Fitness"
    assert guess("5 AI tools every developer needs") == "Tech"
    assert guess("Scandi bedroom decor on a budget") == "Home"
    assert guess("my cat being silly") == "Unsorted"
