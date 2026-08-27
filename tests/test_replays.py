"""Tests du parseur .wotreplay (en-tete JSON). Construit un replay synthetique
minimal — les vrais replays sont prives, on ne les versionne pas."""
from __future__ import annotations

import json
import struct

import pytest

from wot_companion.replays import parse_replay
from wot_companion.replays.parse import (
    ReplayParseError, parse_replay_full, read_json_blocks, vehicle_results)

_MAGIC = b"\x12\x32\x34\x11"


def _make_replay(blocks: list, binary: bytes = b"") -> bytes:
    out = _MAGIC + struct.pack("<I", len(blocks))
    for b in blocks:
        raw = json.dumps(b).encode("utf-8")
        out += struct.pack("<I", len(raw)) + raw
    return out + binary


def _meta():
    return {
        "mapName": "08_ruinberg", "mapDisplayName": "Ruinberg",
        "playerVehicle": "usa-A179_Black_Rock", "playerName": "_darkhell_",
        "battleType": 1, "gameplayID": "ctf", "clientVersionFromExe": "2.3.1.0",
        "vehicles": {},
    }


def _results(team=1, winner=2, dmg=4979, assist_r=946, kills=4, health=0, life=554):
    common = {"winnerTeam": winner, "finishReason": 1}
    personal = {"67361": {
        "team": team, "damageDealt": dmg, "damageAssistedRadio": assist_r,
        "damageAssistedTrack": 0, "kills": kills, "spotted": 0,
        "health": health, "maxHealth": 1950, "lifeTime": life,
    }, "avatar": {}}
    return [{"common": common, "personal": personal, "players": {}, "vehicles": {}}, {}, {}]


def test_parse_full_replay(tmp_path):
    p = tmp_path / "b.wotreplay"
    p.write_bytes(_make_replay([_meta(), _results()], binary=b"\x00" * 2048))
    s = parse_replay(str(p))
    assert s.map_id == "08_ruinberg" and s.map_label == "Ruinberg"
    assert s.vehicle == "usa-A179_Black_Rock"
    assert s.has_results and s.damage == 4979
    assert s.assist_total == 946 and s.kills == 4
    assert s.survived is False and s.life_time_s == 554
    assert s.result == "defeat"          # team 1, winner 2
    assert s.binary_bytes == 2048


def test_victory_and_survival(tmp_path):
    p = tmp_path / "v.wotreplay"
    p.write_bytes(_make_replay([_meta(), _results(team=1, winner=1, health=800)]))
    s = parse_replay(str(p))
    assert s.result == "victory" and s.survived is True


def test_draw(tmp_path):
    p = tmp_path / "d.wotreplay"
    p.write_bytes(_make_replay([_meta(), _results(winner=0)]))
    assert parse_replay(str(p)).result == "draw"


def test_metadata_only_when_no_results(tmp_path):
    # Replay en cours (1 seul bloc) : metadonnees seules, pas de resultats.
    p = tmp_path / "m.wotreplay"
    p.write_bytes(_make_replay([_meta()]))
    s = parse_replay(str(p))
    assert s.map_id == "08_ruinberg" and s.has_results is False and s.damage == 0


def test_bad_magic_raises(tmp_path):
    p = tmp_path / "x.wotreplay"
    p.write_bytes(b"XXXX" + struct.pack("<I", 1) + b"\x00")
    with pytest.raises(ReplayParseError):
        parse_replay(str(p))


def test_truncated_block_raises(tmp_path):
    p = tmp_path / "t.wotreplay"
    # annonce un bloc de 999 octets mais n'en fournit aucun
    p.write_bytes(_MAGIC + struct.pack("<I", 1) + struct.pack("<I", 999))
    with pytest.raises(ReplayParseError):
        read_json_blocks(str(p))


# --------------------------------------------------------------------------- #
# Resultats par vehicule + parse complet (base "meilleurs joueurs").
# --------------------------------------------------------------------------- #
def _meta_roster():
    m = _meta()
    m["playerID"] = 5000            # compte du proprietaire du replay
    m["vehicles"] = {
        "101": {"vehicleType": "usa:A179_Black_Rock", "name": "_darkhell_", "team": 1},
        "102": {"vehicleType": "ussr:R132_VNII_100LT", "name": "Ally", "team": 1},
        "201": {"vehicleType": "germany:G56_E-100", "name": "Foe", "team": 2},
    }
    return m


def _results_multi():
    common = {"winnerTeam": 1, "finishReason": 1}
    personal = {"67361": {"team": 1, "damageDealt": 4512}, "avatar": {}}
    players = {
        "5000": {"realName": "_darkhell_", "name": "_darkhell_", "team": 1},
        "6000": {"realName": "Ally", "name": "Ally", "team": 1},
        "7000": {"realName": "Foe", "name": "Foe", "team": 2},
    }
    vehicles = {
        "101": [{"accountDBID": 5000, "team": 1, "damageDealt": 4512,
                 "damageAssistedRadio": 179, "damageAssistedTrack": 0,
                 "kills": 0, "spotted": 3, "health": 900, "maxHealth": 1950,
                 "lifeTime": 400}],
        "102": [{"accountDBID": 6000, "team": 1, "damageDealt": 2363,
                 "damageAssistedRadio": 2063, "damageAssistedTrack": 100,
                 "kills": 1, "spotted": 5, "health": 0, "maxHealth": 1500,
                 "lifeTime": 300}],
        "201": [{"accountDBID": 7000, "team": 2, "damageDealt": 6000,
                 "damageAssistedRadio": 200, "damageAssistedTrack": 0,
                 "kills": 3, "spotted": 1, "health": 0, "maxHealth": 2500,
                 "lifeTime": 350}],
    }
    return [{"common": common, "personal": personal,
             "players": players, "vehicles": vehicles}, {}, {}]


def test_vehicle_results_extraction(tmp_path):
    p = tmp_path / "r.wotreplay"
    p.write_bytes(_make_replay([_meta_roster(), _results_multi()]))
    blocks, _ = read_json_blocks(str(p))
    res = vehicle_results(blocks)
    assert set(res) == {101, 102, 201}
    me = res[101]
    assert me.is_player and me.name == "_darkhell_"
    assert me.vehicle_type == "usa:A179_Black_Rock"
    assert me.damage == 4512 and me.assist_total == 179 and me.survived is True
    ally = res[102]
    assert ally.is_player is False and ally.assist_total == 2163
    assert ally.combat_score == 2363 + 2163 and ally.survived is False


def test_parse_full_best_performers(tmp_path):
    p = tmp_path / "f.wotreplay"
    p.write_bytes(_make_replay([_meta_roster(), _results_multi()]))
    ds = parse_replay_full(str(p))
    assert ds.summary.result == "victory"
    assert ds.summary_winner_team() == 1
    # Le meilleur toutes equipes est l'ennemi (6000 impact), mais en "winners_only"
    # on ne retient que l'equipe gagnante (1) : l'allie (4426) devant le joueur (4691?).
    top_all = ds.best_performers(1)
    assert top_all[0].vehicle_id == 201            # ennemi, plus fort impact brut
    winners = ds.best_performers(2, winners_only=True)
    assert {v.vehicle_id for v in winners} == {101, 102}
    assert all(v.team == 1 for v in winners)


def test_parse_full_no_results_is_safe(tmp_path):
    p = tmp_path / "n.wotreplay"
    p.write_bytes(_make_replay([_meta_roster()]))   # bataille en cours
    ds = parse_replay_full(str(p))
    assert ds.vehicles == {} and ds.trajectories == {}
    assert ds.summary.has_results is False
