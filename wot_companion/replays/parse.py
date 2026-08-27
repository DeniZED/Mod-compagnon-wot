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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# --------------------------------------------------------------------------- #
# Resultats par vehicule (bloc 1) — base pour selectionner les "meilleurs".
# --------------------------------------------------------------------------- #
@dataclass
class VehicleResult:
    """Performance d'un vehicule de la bataille (verite terrain du replay).

    `vehicle_id` est l'ID d'entite BigWorld, identique a la cle des trajectoires
    decodees : c'est le pont entre stats et deplacements pour batir les clusters.
    """
    vehicle_id: int
    account_id: Optional[int] = None
    name: Optional[str] = None
    vehicle_type: Optional[str] = None   # tag, ex 'usa:A179_Black_Rock'
    team: Optional[int] = None
    is_player: bool = False              # le proprietaire du replay
    damage: int = 0
    assist_radio: int = 0
    assist_track: int = 0
    kills: int = 0
    spotted: int = 0
    survived: Optional[bool] = None
    max_health: int = 0
    life_time_s: Optional[int] = None

    @property
    def assist_total(self) -> int:
        return self.assist_radio + self.assist_track

    @property
    def combat_score(self) -> int:
        """Impact combat brut : degats + assistance (radio + chenilles)."""
        return self.damage + self.assist_total


def vehicle_results(blocks: List[dict]) -> Dict[int, VehicleResult]:
    """Extrait {vehicle_id: VehicleResult} depuis le bloc de resultats (bloc 1).

    Renvoie {} si le replay n'a pas de bloc resultats (bataille en cours).
    """
    if len(blocks) < 2:
        return {}
    root = _results_root(blocks[1])
    if root is None:
        return {}
    vehicles = root.get("vehicles") or {}
    players = root.get("players") or {}
    # Le tag du char et son nom lisible vivent dans le roster du bloc 0 ;
    # `playerID` y identifie le compte du proprietaire du replay.
    meta = blocks[0] if blocks and isinstance(blocks[0], dict) else {}
    roster = meta.get("vehicles") or {}
    owner_account = meta.get("playerID")

    out: Dict[int, VehicleResult] = {}
    for vid_key, entry in vehicles.items():
        veh = entry[0] if isinstance(entry, list) and entry else entry
        if not isinstance(veh, dict):
            continue
        try:
            vid = int(vid_key)
        except (TypeError, ValueError):
            continue
        account_id = _num(veh.get("accountDBID")) or None
        pinfo = players.get(str(account_id)) or players.get(account_id) or {}
        rinfo = roster.get(str(vid)) or roster.get(vid) or {}
        health = veh.get("health")
        out[vid] = VehicleResult(
            vehicle_id=vid,
            account_id=account_id,
            name=(rinfo.get("name") or pinfo.get("realName") or pinfo.get("name")),
            vehicle_type=rinfo.get("vehicleType"),
            team=_num(veh.get("team")) or (_num(rinfo.get("team")) if rinfo else None),
            is_player=(account_id is not None and account_id == owner_account),
            damage=_num(veh.get("damageDealt")),
            assist_radio=_num(veh.get("damageAssistedRadio")),
            assist_track=_num(veh.get("damageAssistedTrack")),
            kills=_num(veh.get("kills")),
            spotted=_num(veh.get("spotted")),
            survived=(_num(health) > 0) if health is not None else None,
            max_health=_num(veh.get("maxHealth")),
            life_time_s=_num(veh.get("lifeTime")) if veh.get("lifeTime") is not None else None,
        )
    return out


def _results_root(results: Any) -> Optional[dict]:
    """Trouve l'entree porteuse de vehicles/players (1re entree de la liste)."""
    if isinstance(results, list):
        for part in results:
            if isinstance(part, dict) and "vehicles" in part:
                return part
        return None
    if isinstance(results, dict) and "vehicles" in results:
        return results
    return None


@dataclass
class ReplayDataset:
    """Vue complete d'un replay : synthese + resultats par char + trajectoires."""
    summary: ReplaySummary
    vehicles: Dict[int, VehicleResult]
    trajectories: Dict[int, List[Tuple[float, float, float]]]

    def best_performers(self, n: int = 3, team: Optional[int] = None,
                        winners_only: bool = False) -> List[VehicleResult]:
        """Meilleurs vehicules par impact combat (degats + assist).

        Sert a selectionner les references pour la Tactical Knowledge Base :
        on n'apprend que des vehicules a fort impact, pas du joueur moyen.
        """
        winner = self.summary_winner_team() if winners_only else None
        cands = [
            v for v in self.vehicles.values()
            if (team is None or v.team == team)
            and (winner is None or v.team == winner)
        ]
        cands.sort(key=lambda v: v.combat_score, reverse=True)
        return cands[:n]

    def summary_winner_team(self) -> Optional[int]:
        """Equipe gagnante deduite du resultat du joueur, ou None."""
        me = next((v for v in self.vehicles.values() if v.is_player), None)
        if me is None or me.team is None or self.summary.result is None:
            return None
        if self.summary.result == "victory":
            return me.team
        if self.summary.result == "defeat":
            return 2 if me.team == 1 else 1
        return None

    def trajectory_of(self, vehicle_id: int) -> List[Tuple[float, float, float]]:
        return self.trajectories.get(vehicle_id, [])


def parse_replay_full(path: str | Path, min_move: float = 3.0) -> ReplayDataset:
    """Parse complet : en-tete + resultats par vehicule + trajectoires decodees.

    100 % local/hors-ligne. Le flux de positions est dechiffre et decompresse
    (voir replays.decode). Point d'entree unique pour bâtir la base tactique.
    """
    from .decode import decrypt_decompress, extract_trajectories

    data = Path(path).read_bytes()
    blocks, binary_bytes = read_json_blocks(path)
    summary = parse_replay(path)
    vehicles = vehicle_results(blocks)

    trajectories: Dict[int, List[Tuple[float, float, float]]] = {}
    if binary_bytes > 0:
        binary = data[len(data) - binary_bytes:]
        try:
            stream = decrypt_decompress(binary)
            trajectories = extract_trajectories(stream, min_move=min_move)
        except Exception:
            trajectories = {}   # replay illisible cote positions : stats seules
    return ReplayDataset(summary=summary, vehicles=vehicles, trajectories=trajectories)
