"""Tests du decodeur binaire de replay (decode.py).

On ne versionne aucun vrai replay (prives). On fabrique un flux synthetique,
on le chiffre exactement comme WoT (Blowfish ECB + feedback XOR + zlib), puis on
verifie le round-trip decrypt + l'extraction des trajectoires.
"""
from __future__ import annotations

import struct
import zlib

import pytest

pytest.importorskip("cryptography")   # decode.py requiert 'cryptography'

from wot_companion.replays.decode import (  # noqa: E402
    ReplayDecodeError, decrypt_decompress, extract_trajectories, iter_packets)

_KEY = bytes.fromhex("DE72BEA0DE04BEB1DEFEBEEFDEADBEEF")


def _blowfish_encrypt(clear: bytes) -> bytes:
    import warnings
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        enc = Cipher(algorithms.Blowfish(_KEY), modes.ECB(),
                     backend=default_backend()).encryptor()
        return enc.update(clear) + enc.finalize()


def _encode_stream(stream: bytes) -> bytes:
    """Inverse exact de decrypt_decompress : produit le flux binaire du replay."""
    comp = zlib.compress(stream)
    comp += b"\x00" * ((8 - len(comp) % 8) % 8)          # padding bloc de 8
    # Feedback XOR inverse : raw[i] = clear[i] ^ clear[i-1] (par blocs de 8).
    raw = bytearray(comp[:8])
    prev = comp[:8]
    for i in range(8, len(comp), 8):
        blk = bytes(a ^ b for a, b in zip(comp[i:i + 8], prev))
        raw += blk
        prev = comp[i:i + 8]
    cipher = _blowfish_encrypt(bytes(raw))
    return struct.pack("<II", len(stream), len(comp)) + cipher


def _packet(clock: float, ptype: int, payload: bytes) -> bytes:
    return struct.pack("<II", len(payload), ptype) + struct.pack("<f", clock) + payload


def _pos_payload(vid: int, x: float, y: float, z: float) -> bytes:
    return struct.pack("<II", vid, 0) + struct.pack("<fff", x, y, z) + b"\x00" * 8


def test_decrypt_decompress_roundtrip():
    stream = b"hello-bigworld-packet-stream" * 10
    binary = _encode_stream(stream)
    assert decrypt_decompress(binary) == stream


def test_decrypt_too_short_raises():
    with pytest.raises(ReplayDecodeError):
        decrypt_decompress(b"\x00\x00\x00")


def test_iter_packets_reads_all():
    stream = (_packet(1.0, 10, _pos_payload(7, 1.0, 0.0, 2.0))
              + _packet(2.0, 99, b"\xaa\xbb")
              + _packet(3.0, 10, _pos_payload(7, 50.0, 0.0, 60.0)))
    got = list(iter_packets(stream))
    assert [p[1] for p in got] == [10, 99, 10]
    assert got[0][0] == pytest.approx(1.0)


def test_extract_trajectories_filters_small_moves():
    # vid 7 bouge nettement ; vid 8 reste quasi immobile (< min_move).
    stream = (
        _packet(0.0, 10, _pos_payload(7, 0.0, 5.0, 0.0))
        + _packet(1.0, 10, _pos_payload(7, 1.0, 5.0, 1.0))     # < 3 m -> ignore
        + _packet(2.0, 10, _pos_payload(7, 100.0, 5.0, 100.0)) # grand pas -> garde
        + _packet(0.0, 10, _pos_payload(8, 300.0, 5.0, 300.0))
        + _packet(1.0, 10, _pos_payload(8, 300.5, 5.0, 300.5)) # immobile -> ignore
    )
    traj = extract_trajectories(stream, min_move=3.0)
    assert set(traj) == {7, 8}
    assert len(traj[7]) == 2          # depart + grand pas
    assert len(traj[8]) == 1          # depart seul
    assert traj[7][1] == (2.0, 100.0, 100.0)


def test_extract_trajectories_skips_out_of_bounds_and_origin():
    stream = (
        _packet(0.0, 10, _pos_payload(1, 0.0, 0.0, 0.0))        # origine -> ignore
        + _packet(1.0, 10, _pos_payload(1, 9999.0, 0.0, 0.0))  # hors carte -> ignore
        + _packet(2.0, 10, _pos_payload(1, 40.0, 0.0, 40.0))   # valide
    )
    traj = extract_trajectories(stream)
    assert traj == {1: [(2.0, 40.0, 40.0)]}
