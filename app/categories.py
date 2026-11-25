"""The shelves every save is sorted onto. Keyword rules for now; an AI step can replace `guess()` later.

Order matters: it is the order shelves appear in the app.
"""

CATEGORIES: dict[str, tuple[str, ...]] = {
    "Tech": ("tech", "code", "coding", "python", "javascript", "sql", "system design", "developer", "programming",
             "api", "ai ", "chatgpt", "gadget", "iphone", "android", "laptop", "app ", "startup", "interview", "excel"),
    "Travel": ("travel", "trip", "goa", "beach", "hotel", "cafe", "café", "itinerary", "flight", "places to visit",
               "visa", "trek", "island", "scuba", "road trip", "hidden gem"),
    "Recipes": ("recipe", "cook", "dinner", "lunch", "breakfast", "paneer", "pasta", "protein", "bake", "chai",
                "dessert", "snack", "meal prep", "curry", "biryani", "salad"),
    "Fitness": ("workout", "gym", "abs", "core", "exercise", "yoga", "plank", "squat", "cardio", "deadlift",
                "kettlebell", "push up", "pushup", "run", "stretch", "mobility"),
    "Fashion": ("outfit", "fashion", "style", "wear", "linen", "dress", "sneakers", "ootd", "saree", "kurta"),
    "Health": ("sleep", "health", "skin", "skincare", "habit", "mental", "doctor", "diet", "gut", "hair"),
    "Money": ("money", "budget", "invest", "salary", "finance", "saving", "stocks", "tax", "mutual fund", "sip "),
    "Books": ("book", "reading", "novel", "author", "summary"),
    "Home": ("decor", "bedroom", "living room", "plants", "flat", "apartment", "furniture", "kitchen", "diy"),
}
UNSORTED = "Unsorted"
ALL = (*CATEGORIES, UNSORTED)

# Words people type in `in:` that mean a category.
ALIASES = {
    "tech": "Tech", "coding": "Tech", "code": "Tech",
    "travel": "Travel", "trips": "Travel",
    "recipes": "Recipes", "recipe": "Recipes", "food": "Recipes", "cooking": "Recipes",
    "fitness": "Fitness", "gym": "Fitness", "workout": "Fitness", "workouts": "Fitness",
    "fashion": "Fashion", "outfits": "Fashion", "style": "Fashion",
    "health": "Health", "money": "Money", "finance": "Money", "books": "Books",
    "home": "Home", "decor": "Home", "unsorted": UNSORTED,
}


def guess(caption: str, url: str = "") -> str:
    text = f" {caption} {url} ".lower()
    scores = {cat: sum(k in text for k in kws) for cat, kws in CATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else UNSORTED


def normalise(name: str) -> str | None:
    """A category name from user input, or None if it isn't one."""
    n = (name or "").strip()
    for c in ALL:
        if c.lower() == n.lower():
            return c
    return ALIASES.get(n.lower())
