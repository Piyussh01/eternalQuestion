"""
Seed lenses — 20 lived worldviews the pipeline researches and debates.

Each lens is a *practiced* way of orienting a life, not an abstract philosophy.
The archetype is a concrete person you could imagine; the description names
the central commitment that organizes their answer to "what is life for?"

The research phase uses `research_angles` to generate Tavily queries per lens.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Lens:
    name: str
    archetype: str
    description: str


SEED_LENSES: list[Lens] = [
    Lens(
        name="Hindu Householder",
        archetype="A grihastha following dharma across the four life stages",
        description="Life is the disciplined fulfillment of duty (dharma) within family, "
        "caste, and cosmos, working off karma across many births toward moksha.",
    ),
    Lens(
        name="Theravada Buddhist Monk",
        archetype="A forest monk in the Thai or Burmese tradition",
        description="Life is suffering caused by craving; meaning is the disciplined "
        "extinction of the illusory self through the eightfold path.",
    ),
    Lens(
        name="Zen Practitioner",
        archetype="A lay or monastic Zen student practicing zazen and koan study",
        description="Meaning is not pursued but uncovered through direct, non-conceptual "
        "presence; thinking about life is already missing it.",
    ),
    Lens(
        name="Christian Contemplative",
        archetype="A Trappist or Carmelite monastic in contemplative service",
        description="Life is participation in divine love through prayer, work, and "
        "self-emptying for others.",
    ),
    Lens(
        name="Sufi Mystic",
        archetype="A wandering dervish in the Rumi or Ibn Arabi lineage",
        description="Life is the soul's annihilation in and reunion with the Beloved; "
        "all of existence is a love story told in two directions.",
    ),
    Lens(
        name="Stoic",
        archetype="A Roman senator or general in the lineage of Marcus Aurelius",
        description="Life is the practice of virtue in accord with nature; meaning lies "
        "in what we control — our judgments and actions — not in fortune.",
    ),
    Lens(
        name="Confucian",
        archetype="A scholar-official cultivating ren (humaneness) and ritual",
        description="Life is the lifelong cultivation of moral character within a web of "
        "relationships — family, ruler, community — each requiring proper form.",
    ),
    Lens(
        name="Taoist",
        archetype="A recluse practicing wu wei in harmony with the Tao",
        description="Life is alignment with the natural flow of things; striving distorts, "
        "non-action accomplishes, the soft overcomes the hard.",
    ),
    Lens(
        name="Indigenous Animist",
        archetype="A member of a kin-with-the-land tradition (e.g., Lakota, Aboriginal)",
        description="Life is reciprocal relationship with a community of more-than-human "
        "persons — rivers, animals, ancestors — to whom we owe care and ceremony.",
    ),
    Lens(
        name="Existentialist",
        archetype="A Sartrean intellectual confronting radical freedom",
        description="There is no given meaning; existence precedes essence; we are "
        "condemned to be free and must construct meaning by what we choose.",
    ),
    Lens(
        name="Absurdist",
        archetype="A Camusian reader of Sisyphus",
        description="The universe offers no answer to our demand for meaning; the only "
        "honest response is lucid revolt — to live fully despite the silence.",
    ),
    Lens(
        name="Nihilist",
        archetype="A post-Nietzschean who has stared into the abyss",
        description="No claim to meaning survives scrutiny; talk of purpose is "
        "self-soothing fiction; the task is to live without that comfort.",
    ),
    Lens(
        name="Hedonist",
        archetype="An Epicurean or modern subjective-wellbeing maximizer",
        description="Life is the pursuit of pleasure and the avoidance of pain, refined "
        "by reflection on which pleasures actually compound.",
    ),
    Lens(
        name="Effective Altruist",
        archetype="A utilitarian optimizing aggregate welfare per dollar and hour",
        description="Life is meaningful in proportion to the suffering it reduces and the "
        "flourishing it enables, weighted impartially across all sentient beings.",
    ),
    Lens(
        name="Banker",
        archetype="A capital allocator funding the productive economy",
        description="Life is meaningful through stewardship of resources — pricing risk, "
        "funding ventures, compounding capital that builds the material world.",
    ),
    Lens(
        name="Artist",
        archetype="A working painter, novelist, or composer",
        description="Life is meaningful as the making of objects that did not exist before "
        "— meaning is what survives in the made thing after the maker is gone.",
    ),
    Lens(
        name="Scientist",
        archetype="A working researcher chasing nature's patterns",
        description="Life is meaningful as participation in the multigenerational project "
        "of understanding — adding a verified sentence to humanity's notebook.",
    ),
    Lens(
        name="Soldier",
        archetype="A career officer serving a cause larger than self",
        description="Life is meaningful through service, sacrifice, and fidelity to "
        "comrades and country — meaning forged in willingness to die for it.",
    ),
    Lens(
        name="Parent",
        archetype="A lifelong steward of the next generation",
        description="Life is meaningful as the patient making of another person — the "
        "child as the work, the relationship as the wage.",
    ),
    Lens(
        name="Transhumanist",
        archetype="An engineer building post-human futures",
        description="Life is the prelude to something greater; meaning lies in extending, "
        "augmenting, and ultimately transcending the biological substrate.",
    ),
]


# Eight research angles per lens — produces concrete Tavily queries
# when formatted with the lens name.
RESEARCH_ANGLES: list[tuple[str, str]] = [
    ("founding_text", "{name} primary texts and founding sources on the meaning of life"),
    ("daily_practice", "{name} daily practice and lived routine"),
    ("on_suffering", "{name} view on suffering and its origin"),
    ("on_death", "{name} teachings about death and what follows"),
    ("modern_critique", "modern critiques and failure modes of the {name} worldview"),
    ("exemplar", "exemplary {name} practitioner biography and life"),
    ("testimony", "first person accounts of living as a {name}"),
    ("defection", "why people leave or abandon the {name} life"),
]


def get_seed_lenses() -> list[Lens]:
    return list(SEED_LENSES)


def angles_for(lens: Lens) -> list[tuple[str, str]]:
    return [(angle, template.format(name=lens.name)) for angle, template in RESEARCH_ANGLES]
