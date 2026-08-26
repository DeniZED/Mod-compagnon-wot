"""Parseur d'en-tete .wotreplay (blocs JSON) — verite terrain d'une bataille.

Format du fichier :
    magic   : 4 octets (0x12323411)
    nblocks : uint32 little-endian (1 en cours de bataille, 2 apres)
    puis nblocks fois : uint32 longueur + JSON
    puis    : flux binaire de paquets (positions) — non lu ici.

Le bloc 0 = metadonnees de debut (carte, char, joueurs). Le bloc 1 (si present)
= resultats : une liste [common, avatars..., ...] dont la 1re entree a la meme
forme que l'event live `onBattleResultsReceived` (personal / common / players).
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

_MAGIC = b"\x12\x32\x34\x11"   # octets d'en-tete d'un .wotreplay


class ReplayParseError(Exception):
    pass


def read_json_blocks(path: str | Path) -> tuple[List[dict], int]:
    """Retourne (liste de blocs JSON decodes, taille du flux binaire restant)."""
    data = Path(path).read_bytes()
    if len(data) < 8:
        raise ReplayParseError("fichier trop court")
    if data[:4] != _MAGIC:
        raise ReplayParseError("magic invalide: %s" % data[:4].hex())
    (nblocks,) = struct.unpack("<I", data[4:8])
    if not (0 < nblocks < 100):
        raise ReplayParseError("nombre de blocs aberrant: %d" % nblocks)
    blocks: List[dict] = []
    off = 8
    for i in range(nblocks):
        if off + 4 > len(data):
            raise ReplayParseError("bloc %d tronque (longueur)" % i)
        (ln,) = struct.unpack("<I", data[off:off + 4])
        off += 4
        raw = data[off:off + ln]
        if len(raw) < ln:
            raise ReplayParseError("bloc %d tronque (%d/%d octets)" % (i, len(raw), ln))
        off += ln
        try:
            blocks.append(json.loads(raw.decode("utf-8", "replace")))
        except ValueError as exc:
            raise ReplayParseError("bloc %d JSON illisible: %s" % (i, exc))
    return blocks, len(data) - off


@dataclass
class ReplaySummary:
    """Verite terrain d'une bataille, extraite de l'en-tete du replay."""
    map_id: Optional[str]
    map_label: Optional[str]
    vehicle: Optional[str]              # tag brut, ex 'usa-A179_Black_Rock'
    player_name: Optional[str]
    battle_type: Optional[int]
    gameplay: Optional[str]
    client_version: Optional[str]
    has_results: bool = False
    damage: int = 0
    assist_radio: int = 0
    assist_track: int = 0
    kills: int = 0
    spotted: int = 0
    survived: Optional[bool] = None
    life_time_s: Optional[int] = None
    result: Optional[str] = None        # victory / defeat / draw / unknown
    binary_bytes: int = 0               # taille du flux positions (a decoder plus tard)

    @property
    def assist_total(self) -> int:
        return self.assist_radio + self.assist_track


def _num(v: Any) -> int:
    return int(v) if isinstance(v, (int, float)) else 0


def parse_replay(path: str | Path) -> ReplaySummary:
    blocks, binary_bytes = read_json_blocks(path)
    meta = blocks[0] if blocks else {}

    s = ReplaySummary(
        map_id=meta.get("mapName"),
        map_label=meta.get("mapDisplayName"),
        vehicle=meta.get("playerVehicle"),
        player_name=meta.get("playerName"),
        battle_type=meta.get("battleType"),
        gameplay=meta.get("gameplayID"),
        client_version=meta.get("clientVersionFromExe"),
        binary_bytes=binary_bytes,
    )

    if len(blocks) < 2:
        return s   # replay en cours / sans resultats : metadonnees seules

    results = blocks[1]
    common, personal = _extract_common_personal(results)
    if personal is None:
        return s
    s.has_results = True

    # `personal` est indexe par vehicleID (parfois plusieurs vehicules), plus une
    # cle 'avatar'. On additionne les vehicules pilotes.
    player_team = None
    for key, veh in personal.items():
        if key == "avatar" or not isinstance(veh, dict) or "damageDealt" not in veh:
            continue
        s.damage += _num(veh.get("damageDealt"))
        s.assist_radio += _num(veh.get("damageAssistedRadio"))
        s.assist_track += _num(veh.get("damageAssistedTrack"))
        s.kills += _num(veh.get("kills"))
        s.spotted += _num(veh.get("spotted"))
        if veh.get("health") is not None:
            s.survived = _num(veh.get("health")) > 0
        if veh.get("lifeTime") is not None:
            s.life_time_s = _num(veh.get("lifeTime"))
        if player_team is None and veh.get("team") is not None:
            player_team = _num(veh.get("team"))

    s.result = _result(common, player_team)
    return s


def _extract_common_personal(results: Any):
    """Tolerant : la 1re entree de la liste des resultats porte common/personal."""
    root = None
    if isinstance(results, list):
        for part in results:
            if isinstance(part, dict) and "personal" in part and "common" in part:
                root = part
                break
    elif isinstance(results, dict) and "personal" in results:
        root = results
    if root is None:
        return {}, None
    return root.get("common", {}) or {}, root.get("personal", {}) or {}


def _result(common: dict, player_team: Optional[int]) -> str:
    winner = common.get("winnerTeam")
    if winner is None or player_team is None:
        return "unknown"
    winner = _num(winner)
    if winner == 0:
        return "draw"
    return "victory" if winner == player_team else "defeat"
