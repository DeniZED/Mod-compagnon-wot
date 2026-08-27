"""Décodage du flux binaire d'un .wotreplay -> trajectoires des véhicules.

Le flux (après les blocs JSON) est : [taille_decompressee:u32][taille_compressee:u32]
puis un payload chiffré Blowfish (clé WoT connue, feedback XOR bloc-à-bloc) et
compressé zlib. Une fois déchiffré/décompressé, c'est un flux de paquets BigWorld :
    [payload_len:u32][type:u32][clock:f32][payload]
Les paquets de type 10 (position) portent : [vehicleID:u32][?:u32][x,y,z:3f32]...

100 % hors-ligne, local. Aucune donnée live. Sert à bâtir la Tactical Knowledge
Base à partir de replays (les tiens, ou de bonnes parties téléchargées).
"""
from __future__ import annotations

import struct
import zlib
from typing import Dict, Iterator, List, Tuple

# Clé Blowfish des replays WoT (publique, utilisée par les parseurs open-source).
_BLOWFISH_KEY = bytes.fromhex("DE72BEA0DE04BEB1DEFEBEEFDEADBEEF")
_POSITION_PACKET = 10
XZ = Tuple[float, float]


class ReplayDecodeError(Exception):
    pass


def decrypt_decompress(binary: bytes) -> bytes:
    """Déchiffre (Blowfish + XOR) puis décompresse (zlib) le flux binaire."""
    if len(binary) < 8:
        raise ReplayDecodeError("flux binaire trop court")
    usize = struct.unpack("<I", binary[:8][:4])[0]
    payload = binary[8:]
    payload = payload[: len(payload) - (len(payload) % 8)]
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")       # Blowfish deprecie mais fonctionnel
        try:
            from cryptography.hazmat.primitives.ciphers import (
                Cipher, algorithms, modes)
            from cryptography.hazmat.backends import default_backend
        except Exception as exc:  # pragma: no cover
            raise ReplayDecodeError("bibliotheque 'cryptography' requise: %s" % exc)
        dec = Cipher(algorithms.Blowfish(_BLOWFISH_KEY), modes.ECB(),
                     backend=default_backend()).decryptor()
        raw = dec.update(payload) + dec.finalize()
    # Feedback XOR : bloc de 8 octets XORé avec le bloc CLAIR précédent.
    out = bytearray(raw[:8])
    prev = raw[:8]
    for i in range(8, len(raw), 8):
        clear = bytes(a ^ b for a, b in zip(raw[i:i + 8], prev))
        out += clear
        prev = clear
    try:
        result = zlib.decompress(bytes(out))
    except zlib.error as exc:
        raise ReplayDecodeError("zlib: %s" % exc)
    if usize and len(result) != usize:
        # tolérant : on continue même si la taille diffère légèrement
        pass
    return result


def iter_packets(stream: bytes) -> Iterator[Tuple[float, int, bytes]]:
    """Itère (clock, type, payload) sur le flux de paquets décompressé."""
    off = 0
    n = len(stream)
    while off + 12 <= n:
        plen, ptype = struct.unpack("<II", stream[off:off + 8])
        clock = struct.unpack("<f", stream[off + 8:off + 12])[0]
        end = off + 12 + plen
        if plen < 0 or end > n:
            break
        yield clock, ptype, stream[off + 12:end]
        off = end


def extract_trajectories(stream: bytes, min_move: float = 3.0
                         ) -> Dict[int, List[Tuple[float, float, float]]]:
    """Trajectoires {vehicleID: [(t, x, z), ...]} depuis les paquets de position.

    On saute les points identiques/quasi-immobiles (< min_move m) pour alléger.
    """
    traj: Dict[int, List[Tuple[float, float, float]]] = {}
    last: Dict[int, XZ] = {}
    for clock, ptype, pay in iter_packets(stream):
        if ptype != _POSITION_PACKET or len(pay) < 20:
            continue
        vid = struct.unpack("<I", pay[0:4])[0]
        x, _y, z = struct.unpack("<fff", pay[8:20])
        if not (-2000.0 < x < 2000.0 and -2000.0 < z < 2000.0):
            continue
        if x == 0.0 and z == 0.0:
            continue                      # spawn non initialisé
        prev = last.get(vid)
        if prev is not None:
            dx, dz = x - prev[0], z - prev[1]
            if dx * dx + dz * dz < min_move * min_move:
                continue
        last[vid] = (x, z)
        traj.setdefault(vid, []).append((round(clock, 1), round(x, 1), round(z, 1)))
    return traj
