"""Configuration du compagnon.

Les valeurs par defaut reprennent celles proposees dans le cahier des charges
(section 7.2 scoring, section 11.1 anti-spam). Tout est ajustable via un simple
dict, ce qui permet de calibrer par playtest sans toucher au code.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Personality(str, Enum):
    """Personnalites textuelles (section 4.2)."""
    COACH = "coach"            # pedagogique, explique la raison
    COMMANDANT = "commandant"  # tres court et direct
    DETENDU = "detendu"        # naturel, un peu plus leger
    SILENCIEUX = "silencieux"  # seulement les conseils critiques


class AdviceCategory(str, Enum):
    """Familles de conseils (section 5.1)."""
    INITIAL_PLAN = "INITIAL_PLAN"
    HP = "HP"
    TEMPO = "TEMPO"
    RETREAT = "RETREAT"
    ROTATION = "ROTATION"
    ENDGAME = "ENDGAME"
    POSITIVE = "POSITIVE"
    REACTION = "REACTION"      # reactions breves aux evenements (tir recu...)
    POSITIONING = "POSITIONING"  # placement (isolement, surextension, menace locale)
    GARAGE = "GARAGE"


class Severity(str, Enum):
    INFO = "INFO"
    ATTENTION = "ATTENTION"
    CRITICAL = "CRITICAL"
    POSITIVE = "POSITIVE"


@dataclass
class ScoringWeights:
    """Bornes des composantes de score (section 7.2)."""
    urgency_max: int = 30       # 0-30
    confidence_max: int = 20    # 0-20
    impact_max: int = 25        # 0-25
    player_context_max: int = 10  # 0-10
    repetition_penalty_max: int = 30  # 0 a -30
    intrusion_penalty_max: int = 20   # 0 a -20


@dataclass
class AntiSpamSettings:
    """Regles anti-spam (section 11.1). Durees en secondes."""
    global_cooldown_s: float = 12.0          # espace deux conseils quelconques
    # Cooldown de categorie abaisse (parties souvent rapides) : une meme famille
    # peut redevenir pertinente plus vite, tout en evitant la repetition immediate.
    category_cooldown_s: float = 45.0        # empeche de repeter LA MEME famille
    bubble_duration_s: float = 5.0
    critical_duration_s: float = 8.0         # 7-9 s
    max_early_advices: int = 3               # hors critique
    positive_enabled: bool = True
    positive_rare_cooldown_s: float = 240.0
    # Seuil calibre par playtests : a 45 seul le plan initial passait (retour
    # joueur "un seul commentaire puis plus rien"). A 38, les conseils de milieu
    # de partie remontent, tout en restant filtres par les cooldowns.
    min_score_threshold: int = 38


@dataclass
class UISettings:
    """Reglages d'affichage (section 4.1)."""
    anchor: str = "top_right"          # coin d'ancrage (evite la minimap bas-droite)
    offset_x: int = 0                  # decalage horizontal supplementaire (px)
    offset_y: int = 0                  # decalage vertical supplementaire (px)
    max_bubble_chars: int = 140
    character_visible: bool = True
    streamer_mode: bool = False
    text_scale: float = 1.0
    click_through: bool = True         # laisse passer les clics (Windows)
    overlay_kind: str = "console"      # console / tk / none — memorise entre lancements
    radar_enabled: bool = False        # radar tactique (2e fenetre) — opt-in
    color_scheme: tuple[str, ...] = ("normal", "attention", "critical", "positive")


@dataclass
class Settings:
    personality: Personality = Personality.COACH
    intensity: float = 1.0  # 0 (rare) -> 1.5 (bavard) ; multiplie le seuil de score
    enabled_categories: set[str] = field(
        default_factory=lambda: {c.value for c in AdviceCategory}
    )
    session_objective: str | None = None  # survie / degats / assistance / discipline_early
    scoring: ScoringWeights = field(default_factory=ScoringWeights)
    anti_spam: AntiSpamSettings = field(default_factory=AntiSpamSettings)
    ui: UISettings = field(default_factory=UISettings)
    language: str = "fr"

    # Base tactique (zones efficaces issues des replays). Chemin d'un JSON produit
    # par `tools.build_tk`. None => aucune base, les conseils de zone restent muets.
    tactical_kb_path: str | None = None

    # Integrations optionnelles, desactivees par defaut (local-first, section 10.3).
    wargaming_api_enabled: bool = False
    wargaming_api_key: str | None = None
    llm_enabled: bool = False
    telemetry_enabled: bool = False

    def effective_score_threshold(self) -> float:
        """Le seuil effectif depend de l'intensite choisie par le joueur.

        Intensite haute -> seuil plus bas -> plus de conseils.
        Intensite basse -> seuil plus haut -> le moteur prefere le silence.
        """
        base = self.anti_spam.min_score_threshold
        # intensity 1.0 => facteur 1.0 ; 0.5 => 1.25 ; 1.5 => 0.75
        factor = 1.5 - self.intensity / 2.0
        return max(1.0, base * factor)

    def category_enabled(self, category: str) -> bool:
        return category in self.enabled_categories

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["personality"] = self.personality.value
        d["enabled_categories"] = sorted(self.enabled_categories)
        d["ui"]["color_scheme"] = list(self.ui.color_scheme)
        return d


DEFAULT_SETTINGS = Settings()
