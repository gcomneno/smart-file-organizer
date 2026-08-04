"""Built-in taxonomy data, intentionally separate from evidence mechanics."""

from collections.abc import Mapping
from types import MappingProxyType

from smart_file_organizer.models import (
    SemanticFolderRule,
    TaxonomyProfileName,
)


PERSONAL_IT_RULES: tuple[SemanticFolderRule, ...] = (
    ("documents/utilities/fastweb", ("fastweb", "conto fastweb")),
    ("documents/utilities/water", ("acque spa", "acque", "acqua")),
    (
        "documents/inps-sfl",
        (
            "inps",
            "sfl",
            "adi",
            "isee",
            "dsu",
            "naspi",
            "domanda inps",
            "prestazioni a sostegno",
            "modelloattestazionedsu",
            "modelloattestazionedso",
        ),
    ),
    (
        "documents/taxes",
        (
            "730",
            "cu2026",
            "cu 2026",
            "ade 2024",
            "agenzia entrate",
            "certificazione unica",
        ),
    ),
    (
        "documents/identity",
        ("ci fronte", "ci retro", "carta identita", "carta d identita", "identity"),
    ),
    (
        "documents/health",
        (
            "urologia",
            "urinocoltura",
            "ecoaddome",
            "deambulazione",
            "verbale invalidita",
            "verbale invalidità",
            "verbale handicap",
            "commissione medica",
            "legge 104",
            "l104",
        ),
    ),
    (
        "documents/legal-notifications",
        ("pn aar", "pn legal facts", "pn notification attachments"),
    ),
    (
        "documents/bank-poste",
        (
            "documentopostawebrapporto",
            "documento postaweb rapporto",
            "prospettopagamento",
            "poste",
            "costimutuo",
            "costi mutuo",
            "mutuo",
        ),
    ),
    (
        "documents/vehicle",
        ("mazda", "rinnovo parcheggio", "contrassegno", "bollo", "ricevuta"),
    ),
    ("documents/insurance", ("zurich", "ass ne", "pol ", "polizza")),
    ("documents/work-admin", ("pre assunzione", "coop zefiro")),
    ("learning/kleis", ("kleis corso", "kleis references", "vademecum stage")),
    ("learning/yocto", ("yocto",)),
    (
        "books/programming",
        (
            "algoritmi",
            "algorithms",
            "strutture dati",
            "csharp",
            "c sharp",
            "python",
            "modern cpp",
            "c++",
            "cpp",
            "lean architectures",
            "hacking secret ciphers",
            "makinggames",
            "esp idf",
            "esp-idf",
            "software architecture",
            "oreilly",
            "o reilly",
            "wiley",
            "programming",
            "regular expressions",
            "object oriented programming",
        ),
    ),
    ("photos/2026", ("foto2026",)),
)


# These short or generic terms are useful in personal-it filenames, but are too
# incidental to treat as descriptive extracted-content evidence on their own.
# This is profile policy: configured rules deliberately remain eligible to use
# the terms when a user has reviewed them for their own taxonomy.
PERSONAL_IT_CONTENT_TOKEN_EXCLUSIONS = frozenset(
    {"adi", "bollo", "dsu", "inps", "isee", "pol", "poste", "ricevuta", "sfl"}
)
_MINIMAL_CONTENT_TOKEN_EXCLUSIONS = frozenset()


# These are reviewed policy values, rather than an implication of the tuple's
# declaration order.  They preserve the overlap resolution users received from
# the historical personal-it rules while leaving generic evidence collection and
# ranking independent of this profile.
PERSONAL_IT_RULE_PRIORITIES: Mapping[str, int] = MappingProxyType(
    {
        "builtin:documents/utilities/fastweb": 10,
        "builtin:documents/utilities/water": 20,
        "builtin:documents/inps-sfl": 30,
        "builtin:documents/taxes": 40,
        "builtin:documents/identity": 50,
        "builtin:documents/health": 60,
        "builtin:documents/legal-notifications": 70,
        "builtin:documents/bank-poste": 80,
        "builtin:documents/vehicle": 90,
        "builtin:documents/insurance": 100,
        "builtin:documents/work-admin": 110,
        "builtin:learning/kleis": 120,
        "builtin:learning/yocto": 130,
        "builtin:books/programming": 140,
        "builtin:photos/2026": 150,
    }
)
_NO_BUILTIN_PRIORITIES: Mapping[str, int] = MappingProxyType({})


def builtin_rules(profile: TaxonomyProfileName) -> tuple[SemanticFolderRule, ...]:
    """Return the profile's semantic rules in stable taxonomy order."""
    if profile is TaxonomyProfileName.MINIMAL:
        return ()
    return PERSONAL_IT_RULES


def builtin_rule_priorities(profile: TaxonomyProfileName) -> Mapping[str, int]:
    """Return reviewed priority policy for the selected built-in profile."""
    if profile is TaxonomyProfileName.MINIMAL:
        return _NO_BUILTIN_PRIORITIES
    return PERSONAL_IT_RULE_PRIORITIES


def builtin_content_token_exclusions(profile: TaxonomyProfileName) -> frozenset[str]:
    """Return immutable profile policy for built-in content-token matching."""
    if profile is TaxonomyProfileName.MINIMAL:
        return _MINIMAL_CONTENT_TOKEN_EXCLUSIONS
    return PERSONAL_IT_CONTENT_TOKEN_EXCLUSIONS
