"""Tests du parseur .wotreplay (en-tete JSON). Construit un replay synthetique
minimal — les vrais replays sont prives, on ne les versionne pas."""
from __future__ import annotations

import json
import struct

import pytest

from wot_companion.replays import parse_replay
from wot_companion.replays.parse import ReplayParseError, read_json_blocks

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
