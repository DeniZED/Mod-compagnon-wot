# -*- coding: utf-8 -*-
"""WoT Companion Bridge - mod client POC (Game Adapter reel).

Ce fichier tourne DANS le processus Python de World of Tanks (WoT 1.16.1+,
Python 3.8). Il est volontairement AUTONOME : il n'importe rien du paquet
`wot_companion` (indisponible cote jeu). Il se contente de lire des informations
NORMALEMENT DISPONIBLES au joueur et de les envoyer, en JSON sur un socket local
(127.0.0.1:47800), au compagnon externe qui heberge le moteur.

CONTRAT FAIR PLAY (identique a la whitelist du moteur) : ce mod ne lit et
n'envoie QUE : entree/sortie de bataille, char du joueur, carte, spawn,
composition au chargement, HP propre, degats/assist propres, comptes de
vehicules vivants, temps. Il ne lit AUCUNE donnee ennemie cachee (reload,
position non spot, direction de canon), n'automatise rien.

STATUT : POC. Les points marques "# POC:" dependent de l'API interne du client
et doivent etre valides/ajustes sur la version reelle de WoT. Tout est enveloppe
dans des try/except : une erreur d'adapter ne doit jamais faire planter le jeu
(NFR-007). Le mode DISCOVERY (voir DISCOVERY=True) journalise les attributs
disponibles dans python.log pour faciliter cette validation.
"""
from __future__ import absolute_import

import json
import socket
import threading
import time
import traceback

# --- Configuration -----------------------------------------------------------
HOST = "127.0.0.1"
PORT = 47800
POLL_INTERVAL_S = 2.0          # cadence de lecture d'etat (impact perf faible)
RECONNECT_BACKOFF_S = 3.0
DISCOVERY = True               # journalise les attributs disponibles (POC)
SCHEMA_VERSION = "1.0"

# Normalisation des cartes (geometryName WoT -> map_id du moteur). A completer.
MAP_NAME_MAP = {
    "05_prohorovka": "prokhorovka",
    "prohorovka": "prokhorovka",
    "amigo_town": "himmelsdorf",
    "01_karelia_himmelsdorf": "himmelsdorf",
    "himmelsdorf": "himmelsdorf",
    "10_hills": "malinovka",
    "malinovka": "malinovka",
    "02_malinovka": "malinovka",
    "mines": "mines",
    "35_iranian_mine": "mines",
    "08_ruinberg": "ruinberg",
    "ruinberg": "ruinberg",
}

# Normalisation de quelques chars (nom de descripteur -> vehicle_id du moteur).
# Elargir au fur et a mesure ; un char inconnu envoie quand meme sa classe.
VEHICLE_NAME_MAP = {
    "Leopard1": "leopard_1",
    "G65_Leopard1": "leopard_1",
    "E-50 Ausf. M": "e50m",
    "G78_E-50_Ausf_M": "e50m",
    "IS-7": "is7",
    "R99_IS-7": "is7",
    "E-100": "e100",
    "G88_E-100": "e100",
    "T110E5": "t110e5",
    "A86_T110E5": "t110e5",
}


def _log(msg):
    """Ecrit dans python.log (LOG_NOTE si dispo, sinon print)."""
    try:
        import debug_utils
        debug_utils.LOG_NOTE("[WoTCompanion] " + str(msg))
    except Exception:
        try:
            print("[WoTCompanion] " + str(msg))
        except Exception:
            pass


# --- Client socket non bloquant ---------------------------------------------
class _Sender(object):
    """Envoie des envelopes JSON au compagnon. N'echoue jamais bruyamment."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._sock = None
        self._lock = threading.Lock()

    def ensure_connected(self):
        if self._sock is not None:
            return True
        try:
            s = socket.create_connection((self.host, self.port), timeout=2.0)
            self._sock = s
            _log("Connecte au compagnon %s:%d" % (self.host, self.port))
            return True
        except Exception as exc:
            self._sock = None
            return False

    def send(self, event_type, payload=None, battle_id=None):
        env = {
            "schema_version": SCHEMA_VERSION,
            "timestamp_ms": int(time.time() * 1000),
            "battle_id": battle_id,
            "event_type": event_type,
            "payload": payload or {},
            "fairplay_class": "ALLOW",
        }
        line = (json.dumps(env) + "\n").encode("utf-8")
        with self._lock:
            if not self.ensure_connected():
                return False
            try:
                self._sock.sendall(line)
                return True
            except Exception:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
                return False

    def close(self):
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None


# --- Lecture d'etat du client (POC) -----------------------------------------
def _player():
    import BigWorld
    return BigWorld.player()


def _normalize_map(geometry_name):
    if not geometry_name:
        return None
    key = str(geometry_name).lower()
    if key in MAP_NAME_MAP:
        return MAP_NAME_MAP[key]
    # tente le dernier segment (ex: "spaces/05_prohorovka" -> "05_prohorovka")
    tail = key.replace("\\", "/").split("/")[-1]
    return MAP_NAME_MAP.get(tail, tail)


def _normalize_vehicle(type_descriptor):
    """Retourne (vehicle_id, class) a partir du descripteur du char joueur."""
    try:
        name = getattr(type_descriptor.type, "name", None) or ""
        short = name.split(":")[-1]
        vid = VEHICLE_NAME_MAP.get(short, VEHICLE_NAME_MAP.get(name))
        klass = None
        tags = getattr(type_descriptor.type, "tags", set())
        for t in ("heavyTank", "mediumTank", "lightTank", "AT-SPG", "SPG"):
            if t in tags:
                klass = {"heavyTank": "heavy", "mediumTank": "medium",
                         "lightTank": "light", "AT-SPG": "td", "SPG": "spg"}[t]
                break
        if vid is None:
            vid = short.lower()  # fallback : nom brut normalise
        return vid, klass
    except Exception:
        return None, None


def _read_composition(arena, my_team):
    """Composition connue au chargement (classes agregees par camp)."""
    ally = {}
    enemy = {}
    ally_n = 0
    enemy_n = 0
    try:
        for vid, info in arena.vehicles.items():  # POC: structure a valider
            team = info.get("team")
            descr = info.get("vehicleType")
            klass = None
            try:
                tags = descr.type.tags
                for t, k in (("heavyTank", "heavy"), ("mediumTank", "medium"),
                             ("lightTank", "light"), ("AT-SPG", "td"), ("SPG", "spg")):
                    if t in tags:
                        klass = k
                        break
            except Exception:
                pass
            bucket = ally if team == my_team else enemy
            if team == my_team:
                ally_n += 1
            else:
                enemy_n += 1
            if klass:
                bucket[klass] = bucket.get(klass, 0) + 1
    except Exception:
        _log("Composition indisponible:\n" + traceback.format_exc())
    return ally, enemy, ally_n, enemy_n


# --- Cycle de vie de la bataille --------------------------------------------
class CompanionBridge(object):
    def __init__(self):
        self.sender = _Sender(HOST, PORT)
        self.battle_id = None
        self.my_team = None
        self._polling = False
        self._start_time = None

    # Appele quand l'avatar du joueur est pret (debut de bataille).
    def on_avatar_ready(self):
        try:
            self._on_battle_start()
        except Exception:
            _log("on_avatar_ready:\n" + traceback.format_exc())

    def on_avatar_non_player(self):
        try:
            self._on_battle_end()
        except Exception:
            _log("on_avatar_non_player:\n" + traceback.format_exc())

    def _on_battle_start(self):
        import BigWorld
        p = _player()
        arena = getattr(p, "arena", None)
        self.battle_id = "wot-%d" % int(time.time())
        self.my_team = getattr(p, "team", None)
        self._start_time = time.time()

        if DISCOVERY:
            _log("DISCOVERY player attrs: " + ", ".join(sorted(dir(p)))[:2000])
            if arena is not None:
                _log("DISCOVERY arena attrs: " + ", ".join(sorted(dir(arena)))[:2000])

        self.sender.send("BATTLE_START", {"battle_id": self.battle_id}, self.battle_id)

        # Char du joueur (BAT-002)
        try:
            descr = getattr(p, "vehicleTypeDescriptor", None) or \
                getattr(getattr(p, "vehicle", None), "typeDescriptor", None)
            vid, klass = _normalize_vehicle(descr)
            self.sender.send("PLAYER_VEHICLE",
                             {"vehicle_id": vid, "class": klass}, self.battle_id)
        except Exception:
            _log("PLAYER_VEHICLE:\n" + traceback.format_exc())

        # Carte + spawn (BAT-003)
        try:
            geom = getattr(getattr(arena, "arenaType", None), "geometryName", None)
            map_id = _normalize_map(geom)
            if map_id:
                self.sender.send("MAP_INFO", {"map_id": map_id}, self.battle_id)
            # POC: le spawn "north/south" derive de la position de depart ou du
            # team. Heuristique simple ici, a valider par observation.
            spawn = "north" if self.my_team == 1 else "south"
            self.sender.send("SPAWN_INFO", {"spawn": spawn}, self.battle_id)
        except Exception:
            _log("MAP/SPAWN:\n" + traceback.format_exc())

        # Composition (BAT-004)
        try:
            ally, enemy, an, en = _read_composition(arena, self.my_team)
            self.sender.send("TEAM_COMPOSITION", {
                "ally_classes": ally, "enemy_classes": enemy,
                "ally_count": an, "enemy_count": en,
            }, self.battle_id)
        except Exception:
            _log("TEAM_COMPOSITION:\n" + traceback.format_exc())

        self._start_polling()

    def _on_battle_end(self):
        self._polling = False
        if self.battle_id is not None:
            self.sender.send("BATTLE_END", {"battle_id": self.battle_id}, self.battle_id)
        self.battle_id = None

    # Boucle de lecture d'etat periodique (HP, temps, comptes).
    def _start_polling(self):
        import BigWorld
        self._polling = True

        def tick():
            if not self._polling or self.battle_id is None:
                return
            try:
                self._poll_once()
            except Exception:
                _log("poll:\n" + traceback.format_exc())
            try:
                BigWorld.callback(POLL_INTERVAL_S, tick)
            except Exception:
                pass

        try:
            BigWorld.callback(POLL_INTERVAL_S, tick)
        except Exception:
            _log("Impossible de programmer le polling:\n" + traceback.format_exc())

    def _poll_once(self):
        p = _player()
        elapsed = time.time() - (self._start_time or time.time())
        self.sender.send("CLOCK_TICK", {"elapsed_s": round(elapsed, 1)}, self.battle_id)

        # HP propre (BAT / information propre)
        try:
            veh = getattr(p, "vehicle", None)
            hp = getattr(veh, "health", None)
            max_hp = getattr(veh, "maxHealth", None)
            if hp is not None and max_hp:
                self.sender.send("PLAYER_HP_CHANGED",
                                 {"hp": max(0, hp), "max_hp": max_hp}, self.battle_id)
        except Exception:
            pass

        # Comptes de vehicules vivants (visibles au tableau)
        try:
            arena = getattr(p, "arena", None)
            allies = enemies = 0
            for vid, info in arena.vehicles.items():
                if not info.get("isAlive", True):
                    continue
                if info.get("team") == self.my_team:
                    allies += 1
                else:
                    enemies += 1
            self.sender.send("TEAM_COUNT",
                             {"allies_alive": allies, "enemies_alive": enemies},
                             self.battle_id)
        except Exception:
            pass


# --- Point d'entree du mod ---------------------------------------------------
_bridge = None


def init():
    """Appele automatiquement par WoT au chargement du mod."""
    global _bridge
    try:
        _bridge = CompanionBridge()
        _log("Mod WoT Companion Bridge charge (POC).")

        # Branche les evenements de cycle de vie de l'avatar.
        try:
            from PlayerEvents import g_playerEvents
            g_playerEvents.onAvatarReady += _bridge.on_avatar_ready          # POC
            g_playerEvents.onAvatarBecomeNonPlayer += _bridge.on_avatar_non_player  # POC
            _log("Hooks g_playerEvents branches.")
        except Exception:
            _log("g_playerEvents indisponible, hooks a adapter:\n" + traceback.format_exc())
    except Exception:
        _log("Echec init:\n" + traceback.format_exc())


def fini():
    """Appele au dechargement (si supporte)."""
    global _bridge
    if _bridge is not None:
        try:
            _bridge.sender.close()
        except Exception:
            pass
        _bridge = None


# Certaines versions appellent init() automatiquement ; sinon, l'import du module
# suffit a l'enregistrer. On tente un init immediat protege.
try:
    init()
except Exception:
    _log("init differe.")
