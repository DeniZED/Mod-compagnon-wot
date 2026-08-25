# -*- coding: utf-8 -*-
"""WoT Companion Bridge - mod client POC (Game Adapter reel).

Ce fichier tourne DANS le processus Python de World of Tanks / Mir Tankov
(clients recents, Python 3). Il est volontairement AUTONOME : il n'importe rien
du paquet `wot_companion` (indisponible cote jeu). Il lit uniquement des
informations NORMALEMENT DISPONIBLES au joueur et les envoie, en JSON sur un
socket local (127.0.0.1:47800), au compagnon externe qui heberge le moteur.

CONTRAT FAIR PLAY : bataille, char du joueur, carte, spawn, composition au
chargement, HP propre, temps, comptes de vehicules vivants. Aucune donnee
ennemie cachee, aucune automatisation.

STATUT : POC. Tout est enveloppe dans des try/except : une erreur d'adapter ne
doit jamais faire planter le jeu. Le mod ecrit TOUS ses messages a la fois dans
python.log ET dans un fichier dedie `wot_companion.log` place dans un dossier
sur pour etre facilement retrouve (profil utilisateur en priorite).
"""
from __future__ import absolute_import, print_function

import io
import json
import os
import threading
import time
import traceback
# Compatible Python 2.7 ET 3.x : le client WoT peut embarquer l'un ou l'autre
# selon la version. Pas de f-strings, io.open pour l'encodage, print_function.
# NB: `socket` est importe PLUS TARD, dans _Sender (certains clients restreignent
# son import au niveau module ; le differer evite un echec d'import silencieux).

# --- Configuration -----------------------------------------------------------
HOST = "127.0.0.1"
PORT = 47800
POLL_INTERVAL_S = 2.0
DISCOVERY = True
DISCOVERY_DELAY_S = 6.0
SCHEMA_VERSION = "1.0"
BUILD_TAG = "b2"               # marqueur de build : confirme que la nouvelle version tourne

MAP_NAME_MAP = {
    # Noms internes reels du client WoT (geometryName) -> map_id du moteur.
    "05_prohorovka": "prokhorovka", "prohorovka": "prokhorovka",
    "04_himmelsdorf": "himmelsdorf", "himmelsdorf": "himmelsdorf",
    "02_malinovka": "malinovka", "malinovka": "malinovka",
    "10_hills": "mines", "mines": "mines",              # Mines = 10_hills en interne
    "08_ruinberg": "ruinberg", "ruinberg": "ruinberg",
    "06_ensk": "ensk", "06_ensk_big": "ensk", "ensk": "ensk",
}
VEHICLE_NAME_MAP = {
    "Leopard1": "leopard_1", "G65_Leopard1": "leopard_1",
    "E-50 Ausf. M": "e50m", "G78_E-50_Ausf_M": "e50m",
    "IS-7": "is7", "R99_IS-7": "is7",
    "E-100": "e100", "G88_E-100": "e100",
    "T110E5": "t110e5", "A86_T110E5": "t110e5",
}
_CLASS_TAGS = (
    ("heavyTank", "heavy"), ("mediumTank", "medium"), ("lightTank", "light"),
    ("AT-SPG", "td"), ("SPG", "spg"),
)

# Rôle metier deduit des tags "role_*" du char (information visible au joueur).
_ROLE_TAG_MAP = {
    "role_HT_assault": "assault_heavy",
    "role_HT_break": "assault_heavy",
    "role_HT_support": "support_heavy",
    "role_HT_universal": "support_heavy",
    "role_MT_assault": "brawler_medium",
    "role_MT_support": "sniper_medium",
    "role_MT_sniper": "sniper_medium",
    "role_MT_universal": "brawler_medium",
    "role_LT": "scout",
    "role_LT_universal": "scout",
    "role_LT_wheeled": "scout",
    "role_ATSPG_assault": "td_assault",
    "role_ATSPG_support": "td_sniper",
    "role_ATSPG_sniper": "td_sniper",
    "role_ATSPG_universal": "td_sniper",
}


# --- Journalisation robuste --------------------------------------------------
def _candidate_dirs():
    dirs = []
    try:
        appd = os.environ.get("APPDATA")
        if appd:
            dirs.append(os.path.join(appd, "Wargaming.net", "WorldOfTanks"))
            dirs.append(appd)
    except Exception:
        pass
    try:
        dirs.append(os.path.expanduser("~"))
    except Exception:
        pass
    try:
        dirs.append(os.getcwd())
    except Exception:
        pass
    return dirs


def _resolve_out_dir():
    for d in _candidate_dirs():
        try:
            if d and os.path.isdir(d) and os.access(d, os.W_OK):
                return d
        except Exception:
            continue
    try:
        return os.path.expanduser("~")
    except Exception:
        return "."


_OUT_DIR = _resolve_out_dir()
_LOG_FILE = os.path.join(_OUT_DIR, "wot_companion.log")
_DISCOVERY_FILE = os.path.join(_OUT_DIR, "wot_companion_discovery.log")


def _file_append(path, msg):
    try:
        with io.open(path, "a", encoding="utf-8") as fh:  # io.open : encodage OK en 2.7 et 3
            fh.write(u"" + str(msg) + u"\n")
    except Exception:
        pass


def _log(msg):
    line = "[WoTCompanion] " + str(msg)
    try:
        import debug_utils
        debug_utils.LOG_NOTE(line)
    except Exception:
        try:
            print(line)
        except Exception:
            pass
    _file_append(_LOG_FILE, line)


def _discovery_log(msg):
    _log(msg)
    _file_append(_DISCOVERY_FILE, msg)


def _first(*getters):
    for g in getters:
        try:
            v = g()
            if v is not None:
                return v
        except Exception:
            continue
    return None


def _probe(label, getter):
    try:
        val = getter()
        _discovery_log("  OK   %-28s = %r" % (label, val))
        return val
    except Exception as exc:
        _discovery_log("  FAIL %-28s : %s" % (label, exc))
        return None


# Marqueur de demarrage IMMEDIAT : si cette ligne apparait, le module a bien ete
# importe et execute par le client.
_log("=== Module importe (build %s). Journal: %s ===" % (BUILD_TAG, _LOG_FILE))


# --- Client socket non bloquant ---------------------------------------------
class _Sender(object):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._sock = None
        self._lock = threading.Lock()

    def ensure_connected(self):
        if self._sock is not None:
            return True
        try:
            import socket  # import differe (voir en-tete)
            self._sock = socket.create_connection((self.host, self.port), timeout=2.0)
            _log("Connecte au compagnon %s:%d" % (self.host, self.port))
            return True
        except Exception:
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
                self._close_locked()
                return False

    def _close_locked(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def close(self):
        with self._lock:
            self._close_locked()


# --- Normalisation -----------------------------------------------------------
def _normalize_map(geometry_name):
    if not geometry_name:
        return None
    key = str(geometry_name).lower()
    if key in MAP_NAME_MAP:
        return MAP_NAME_MAP[key]
    tail = key.replace("\\", "/").split("/")[-1]
    return MAP_NAME_MAP.get(tail, tail)


def _class_from_tags(tags):
    try:
        for tag, klass in _CLASS_TAGS:
            if tag in tags:
                return klass
    except Exception:
        pass
    return None


def _role_from_tags(tags):
    try:
        for t in tags:
            if t in _ROLE_TAG_MAP:
                return _ROLE_TAG_MAP[t]
    except Exception:
        pass
    return None


def _normalize_vehicle(type_descriptor):
    """Retourne (vehicle_id, class, role) depuis le descripteur du char joueur."""
    try:
        vtype = getattr(type_descriptor, "type", type_descriptor)
        name = getattr(vtype, "name", None) or ""
        short = str(name).split(":")[-1]
        vid = VEHICLE_NAME_MAP.get(short) or VEHICLE_NAME_MAP.get(name)
        tags = getattr(vtype, "tags", ()) or ()
        klass = _class_from_tags(tags)
        role = _role_from_tags(tags)
        if vid is None and short:
            vid = short.lower()
        return vid, klass, role
    except Exception:
        return None, None, None


# --- Acces client, multi-chemins (POC) --------------------------------------
def _player():
    import BigWorld
    return BigWorld.player()


def _get_arena(p):
    import BigWorld
    return _first(lambda: p.arena, lambda: BigWorld.player().arena)


def _get_geometry(arena):
    return _first(
        lambda: arena.arenaType.geometryName,
        lambda: arena.arenaType.geometry,
        lambda: arena.arenaType.name,
    )


def _get_vehicle_descriptor(p):
    return _first(
        lambda: p.vehicleTypeDescriptor,
        lambda: p.vehicle.typeDescriptor,
        lambda: p.getVehicleDescriptor(),
    )


def _get_health(p):
    veh = _first(lambda: p.vehicle, lambda: p.getVehicleAttached())
    hp = _first(lambda: veh.health, lambda: p.vehicle.health)
    max_hp = _first(
        lambda: veh.maxHealth,
        lambda: veh.typeDescriptor.maxHealth,
        lambda: p.vehicle.maxHealth,
    )
    return hp, max_hp


def _iter_arena_vehicles(arena):
    out = []
    vehicles = _first(lambda: arena.vehicles)
    if not vehicles:
        return out
    for vid, info in vehicles.items():
        try:
            team = info.get("team")
            descr = info.get("vehicleType")
            vtype = getattr(descr, "type", descr)
            klass = _class_from_tags(getattr(vtype, "tags", ()) or ())
            is_alive = info.get("isAlive", True)
            out.append((vid, team, klass, is_alive))
        except Exception:
            continue
    return out


def _resolve_session_provider():
    """Recupere le fournisseur de session de bataille (plusieurs chemins connus)."""
    sp = _first(
        lambda: __import__("gui.battle_control", fromlist=["g_sessionProvider"]).g_sessionProvider,
    )
    if sp is None:
        try:
            from helpers import dependency
            from skeletons.gui.battle_session import IBattleSessionProvider
            sp = dependency.instance(IBattleSessionProvider)
        except Exception:
            sp = None
    return sp


# --- Cycle de vie de la bataille --------------------------------------------
class CompanionBridge(object):
    def __init__(self):
        self.sender = _Sender(HOST, PORT)
        self.battle_id = None
        self.my_team = None
        self._polling = False
        self._start_time = None
        self._eff_ctrl = None          # personalEfficiencyCtrl (degats/assist live)
        self._results_hooked = False   # hook onBattleResultsReceived pose une fois
        self._ended_battle_id = None   # id conserve pour rattacher les resultats tardifs

    def on_avatar_ready(self):
        _log("Evenement: avatar pret (debut de bataille).")
        try:
            self._on_battle_start()
        except Exception:
            _log("on_avatar_ready:\n" + traceback.format_exc())

    def on_avatar_non_player(self):
        _log("Evenement: sortie de bataille.")
        try:
            self._on_battle_end()
        except Exception:
            _log("on_avatar_non_player:\n" + traceback.format_exc())

    def _on_battle_start(self):
        p = _player()
        arena = _get_arena(p)
        self.battle_id = "wot-%d" % int(time.time())
        self.my_team = _first(lambda: p.team)
        self._start_time = time.time()

        self.sender.send("BATTLE_START", {"battle_id": self.battle_id}, self.battle_id)

        vid, klass, role = _normalize_vehicle(_get_vehicle_descriptor(p))
        self.sender.send("PLAYER_VEHICLE",
                         {"vehicle_id": vid, "class": klass, "role": role},
                         self.battle_id)

        map_id = _normalize_map(_get_geometry(arena))
        if map_id:
            self.sender.send("MAP_INFO", {"map_id": map_id}, self.battle_id)
        spawn = "north" if self.my_team == 1 else "south"
        self.sender.send("SPAWN_INFO", {"spawn": spawn}, self.battle_id)

        self._send_composition(arena)

        if DISCOVERY:
            self.discover(p, arena, phase="start")
            self._schedule(DISCOVERY_DELAY_S,
                           lambda: self.discover(_player(), _get_arena(_player()),
                                                 phase="delayed"))
        # Sondes degats/assist + resultats (log-only pour l'instant, a cabler
        # ensuite au vu du log). Ne modifie aucun comportement existant.
        self._hook_stats_discovery()
        self._start_polling()

    # ---- Statistiques : resultat de bataille (cable) + sonde efficacite live -
    def _hook_stats_discovery(self):
        # Sonde de l'efficacite personnelle (degats/assist en direct) : on
        # journalise ses accesseurs pour cabler le live au prochain tour.
        try:
            sp = _resolve_session_provider()
            shared = getattr(sp, "shared", None) if sp else None
            self._eff_ctrl = getattr(shared, "personalEfficiencyCtrl", None) if shared else None
            if self._eff_ctrl is not None and DISCOVERY:
                getters = [a for a in dir(self._eff_ctrl) if a.startswith("get")]
                _discovery_log("STATS: personalEfficiencyCtrl getters = " + repr(getters)[:400])
                for name in ("getTotalEfficiency", "getDamage", "getDamageDealt"):
                    if hasattr(self._eff_ctrl, name):
                        try:
                            val = getattr(self._eff_ctrl, name)()
                            _discovery_log("STATS: %s() = %r (attrs=%s)" %
                                           (name, val, [a for a in dir(val) if a.startswith("get")][:20]))
                        except Exception as exc:
                            _discovery_log("STATS: %s() erreur: %s" % (name, exc))
        except Exception:
            _discovery_log("STATS efficiency probe:\n" + traceback.format_exc())

        # Resultat de bataille (cable) : source autoritaire pour le garage.
        try:
            from PlayerEvents import g_playerEvents
            if hasattr(g_playerEvents, "onBattleResultsReceived") and not self._results_hooked:
                g_playerEvents.onBattleResultsReceived += self._on_results
                self._results_hooked = True
                _discovery_log("STATS: hook onBattleResultsReceived OK")
        except Exception:
            _discovery_log("STATS hook resultats:\n" + traceback.format_exc())

    def _on_results(self, *args):
        """Resultats de bataille -> envoie degats/assist reels + resultat."""
        try:
            results = args[-1] if args else None
            if not hasattr(results, "get"):
                return
            personal = results.get("personal", {}) or {}
            common = results.get("common", {}) or {}

            dmg = assist = kills = 0
            survived = None
            for key, v in personal.items():
                if not isinstance(v, dict) or "damageDealt" not in v:
                    continue  # ignore la cle 'avatar' et autres non-vehicules
                dmg += v.get("damageDealt", 0) or 0
                assist += (v.get("damageAssistedRadio", 0) or 0) \
                    + (v.get("damageAssistedTrack", 0) or 0) \
                    + (v.get("damageAssistedStun", 0) or 0)
                kills += v.get("kills", 0) or 0
                dr = v.get("deathReason", -1)
                surv = (dr == -1)
                survived = surv if survived is None else (survived and surv)

            winner = common.get("winnerTeam", 0)
            if winner == 0:
                result = "draw"
            elif winner == self.my_team:
                result = "victory"
            else:
                result = "defeat"

            bid = self._ended_battle_id or self.battle_id
            if bid is None:
                return
            if dmg:
                self.sender.send("PLAYER_DAMAGE_DEALT", {"total_damage": dmg}, bid)
            if assist:
                self.sender.send("PLAYER_ASSIST", {"total_assist": assist}, bid)
            self.sender.send("BATTLE_RESULT", {
                "result": result, "damage": dmg, "assist": assist,
                "survived": 1 if survived else 0, "kills": kills,
            }, bid)
            _discovery_log("RESULT envoye: %s dmg=%d assist=%d kills=%d survived=%r" %
                           (result, dmg, assist, kills, survived))
        except Exception:
            _discovery_log("RESULT parse:\n" + traceback.format_exc())

    def _send_composition(self, arena):
        ally, enemy = {}, {}
        an = en = 0
        for vid, team, klass, _alive in _iter_arena_vehicles(arena):
            if team == self.my_team:
                an += 1
                if klass:
                    ally[klass] = ally.get(klass, 0) + 1
            else:
                en += 1
                if klass:
                    enemy[klass] = enemy.get(klass, 0) + 1
        self.sender.send("TEAM_COMPOSITION", {
            "ally_classes": ally, "enemy_classes": enemy,
            "ally_count": an, "enemy_count": en,
        }, self.battle_id)

    def _on_battle_end(self):
        self._polling = False
        # On conserve l'id : les resultats de bataille arrivent souvent APRES la
        # sortie de l'arene, et doivent pouvoir s'y rattacher (garage a jour).
        if self.battle_id is not None:
            self._ended_battle_id = self.battle_id
            self.sender.send("BATTLE_END", {"battle_id": self.battle_id}, self.battle_id)
        self.battle_id = None

    def _schedule(self, delay, fn):
        try:
            import BigWorld
            BigWorld.callback(delay, fn)
        except Exception:
            _log("scheduling indisponible:\n" + traceback.format_exc())

    def _start_polling(self):
        self._polling = True

        def tick():
            if not self._polling or self.battle_id is None:
                return
            try:
                self._poll_once()
            except Exception:
                _log("poll:\n" + traceback.format_exc())
            self._schedule(POLL_INTERVAL_S, tick)

        self._schedule(POLL_INTERVAL_S, tick)

    def _poll_once(self):
        p = _player()
        elapsed = time.time() - (self._start_time or time.time())
        self.sender.send("CLOCK_TICK", {"elapsed_s": round(elapsed, 1)}, self.battle_id)

        hp, max_hp = _get_health(p)
        if hp is not None and max_hp:
            self.sender.send("PLAYER_HP_CHANGED",
                             {"hp": max(0, hp), "max_hp": max_hp}, self.battle_id)

        arena = _get_arena(p)
        allies = enemies = 0
        counted = False
        for vid, team, klass, is_alive in _iter_arena_vehicles(arena):
            counted = True
            if not is_alive:
                continue
            if team == self.my_team:
                allies += 1
            else:
                enemies += 1
        if counted:
            self.sender.send("TEAM_COUNT",
                             {"allies_alive": allies, "enemies_alive": enemies},
                             self.battle_id)

    def discover(self, p, arena, phase):
        _discovery_log("===== DISCOVERY (%s) %s =====" %
                       (phase, time.strftime("%Y-%m-%d %H:%M:%S")))
        _probe("player.team", lambda: p.team)
        _probe("player.playerVehicleID", lambda: p.playerVehicleID)
        _probe("arena present", lambda: arena is not None)
        _probe("arena.arenaType.geometryName", lambda: arena.arenaType.geometryName)
        _probe("normalized map_id", lambda: _normalize_map(_get_geometry(arena)))
        descr = _get_vehicle_descriptor(p)
        _probe("vehicle descriptor type.name", lambda: descr.type.name)
        _probe("vehicle descriptor type.tags", lambda: list(descr.type.tags))
        _probe("normalized (vehicle_id,class)", lambda: _normalize_vehicle(descr))
        hp, max_hp = _get_health(p)
        _discovery_log("  hp=%r max_hp=%r" % (hp, max_hp))
        vehicles = _iter_arena_vehicles(arena)
        _discovery_log("  arena.vehicles: %d entrees" % len(vehicles))
        for row in vehicles[:4]:
            _discovery_log("    sample vid=%r team=%r class=%r alive=%r" % row)
        _probe("arena.period", lambda: arena.period)
        _discovery_log("Colle ce bloc au developpeur pour ajuster les hooks.")
        _discovery_log("=====================================")


# --- Point d'entree du mod ---------------------------------------------------
_bridge = None
_inited = False


def init():
    """Appele automatiquement par WoT au chargement du mod (et a l'import)."""
    global _bridge, _inited
    if _inited:
        return
    _inited = True
    try:
        _bridge = CompanionBridge()
        _log("Mod charge (build %s). En attente d'une bataille." % BUILD_TAG)
        try:
            from PlayerEvents import g_playerEvents
            g_playerEvents.onAvatarReady += _bridge.on_avatar_ready
            g_playerEvents.onAvatarBecomeNonPlayer += _bridge.on_avatar_non_player
            _log("Hooks g_playerEvents branches (onAvatarReady / onAvatarBecomeNonPlayer).")
        except Exception:
            _log("g_playerEvents indisponible, hooks a adapter:\n" + traceback.format_exc())
    except Exception:
        _log("Echec init:\n" + traceback.format_exc())


def fini():
    global _bridge
    if _bridge is not None:
        try:
            _bridge.sender.close()
        except Exception:
            pass
        _bridge = None


# Auto-init a l'import (au cas ou le loader n'appelle pas init()).
try:
    init()
except Exception:
    _log("init differe:\n" + traceback.format_exc())
