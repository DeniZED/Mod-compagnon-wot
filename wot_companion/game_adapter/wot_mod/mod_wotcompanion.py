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
BUILD_TAG = "b16"               # marqueur de build : confirme que la nouvelle version tourne

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
# REGLE ABSOLUE : le thread PRINCIPAL du jeu ne doit JAMAIS faire d'I/O reseau.
# send() (appele depuis les callbacks BigWorld = thread principal) se contente
# d'empiler l'evenement (O(1), sans blocage). Un thread de fond gere connexion et
# envoi avec un timeout court. Si le compagnon n'est pas lance, les evenements
# sont simplement jetes : le jeu n'est jamais ralenti (0 fps corrige).
_CONNECT_TIMEOUT_S = 0.3     # tentative de connexion tres courte (localhost)
_CONNECT_RETRY_S = 3.0       # on ne retente pas la connexion a chaque evenement
_QUEUE_MAX = 500             # file bornee : on jette le plus ancien si pleine


class _Sender(object):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._sock = None
        self._stop = False
        self._last_attempt = 0.0
        try:
            import Queue as _q      # Python 2
        except ImportError:
            import queue as _q      # Python 3
        self._queue = _q.Queue(maxsize=_QUEUE_MAX)
        self._thread = threading.Thread(target=self._run)
        self._thread.daemon = True   # meurt avec le jeu, ne le maintient pas en vie
        try:
            self._thread.start()
        except Exception:
            _log("thread d'envoi non demarre:\n" + traceback.format_exc())

    def send(self, event_type, payload=None, battle_id=None):
        """APPELE SUR LE THREAD PRINCIPAL : empile seulement, aucune I/O ici."""
        env = {
            "schema_version": SCHEMA_VERSION,
            "timestamp_ms": int(time.time() * 1000),
            "battle_id": battle_id,
            "event_type": event_type,
            "payload": payload or {},
            "fairplay_class": "ALLOW",
        }
        try:
            line = (json.dumps(env) + "\n").encode("utf-8")
        except Exception:
            return False
        try:
            self._queue.put_nowait(line)
        except Exception:
            # File pleine (compagnon absent) : on jette le plus ancien et on
            # empile le nouveau. Jamais de blocage du thread de jeu.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(line)
            except Exception:
                pass
        return True

    def _run(self):
        """Thread de fond : draine la file et envoie. Toute l'I/O est ici."""
        while not self._stop:
            try:
                line = self._queue.get(timeout=0.5)
            except Exception:
                continue
            if line is None:      # signal d'arret
                break
            if not self._ensure_connected():
                continue          # compagnon absent : on jette silencieusement
            try:
                self._sock.sendall(line)
            except Exception:
                self._close_sock()

    def _ensure_connected(self):
        if self._sock is not None:
            return True
        now = time.time()
        if now - self._last_attempt < _CONNECT_RETRY_S:
            return False          # throttle : pas de tentative a chaque evenement
        self._last_attempt = now
        try:
            import socket          # import differe (voir en-tete)
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=_CONNECT_TIMEOUT_S)
            _log("Connecte au compagnon %s:%d" % (self.host, self.port))
            return True
        except Exception:
            self._sock = None
            return False

    def _close_sock(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def close(self):
        self._stop = True
        try:
            self._queue.put_nowait(None)   # reveille le thread pour qu'il sorte
        except Exception:
            pass
        self._close_sock()


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


def _get_bounds(arena):
    """Limites monde de l'arene [minX, minZ, maxX, maxZ] (memes bornes que la
    minimap du jeu). Permet au compagnon d'aligner ses marqueurs sur la minimap.
    boundingBox WoT = ((minX, minZ), (maxX, maxZ))."""
    bb = _first(
        lambda: arena.arenaType.boundingBox,
        lambda: arena.arenaType.geometry.boundingBox,
    )
    try:
        (minx, minz), (maxx, maxz) = bb
        vals = [float(minx), float(minz), float(maxx), float(maxz)]
        if all(abs(v) < 100000 for v in vals) and maxx > minx and maxz > minz:
            return vals
    except Exception:
        pass
    return None


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


def _as_int(v):
    """Convertit une valeur numerique en int (gere le `long` de Python 2, ex 690L).
    Retourne None si non convertible. Evite le piege isinstance(int,float)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _xz(pos):
    """Normalise une position WoT en [x, z] (plan horizontal), entiers (metres).
    Tolerant : Vector3 (.x/.y/.z), Vector2 (.x/.y), ou sequence indexable."""
    if pos is None:
        return None
    try:
        if hasattr(pos, "z") and hasattr(pos, "x"):
            return [int(round(pos.x)), int(round(pos.z))]
        if hasattr(pos, "y") and hasattr(pos, "x"):     # Vector2 : (x, y) = plan
            return [int(round(pos.x)), int(round(pos.y))]
        n = len(pos)
        if n >= 3:
            return [int(round(pos[0])), int(round(pos[2]))]
        if n == 2:
            return [int(round(pos[0])), int(round(pos[1]))]
    except (TypeError, ValueError, IndexError):
        return None
    return None


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
        self._max_hp = None            # HP max memorise (pour signaler la mort)
        self._dead_sent = False        # HP=0 deja envoye pour cette bataille
        self._player_vid = None        # id du vehicule du joueur dans l'arene
        self._pos_log_ctr = 0          # throttle du log de diagnostic positions
        self._vis_dumped = False        # dump unique du format getVisibleVehicles
        self._fb_damage = 0             # cumul degats infliges (feedback)
        self._fb_assist = 0             # cumul assist (feedback)
        self._fb_spots = 0              # nb de spots (visibilite)
        self._fb_dumped = 0             # nb d'evenements feedback deja detailles
        self._feedback_hooked = False   # hook feedback pose une fois par bataille

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
        self._dead_sent = False
        self._max_hp = None
        self._vis_dumped = False
        self._fb_damage = 0            # cumul degats infliges (feedback)
        self._fb_assist = 0            # cumul assist (feedback), si dispo
        self._fb_spots = 0             # nb de spots (visibilite)
        self._fb_dumped = 0            # nb d'evenements feedback deja detailles
        self._feedback_hooked = False  # hook feedback pose une fois par bataille
        self._player_vid = _first(lambda: p.playerVehicleID)

        self.sender.send("BATTLE_START", {"battle_id": self.battle_id}, self.battle_id)

        vid, klass, role = _normalize_vehicle(_get_vehicle_descriptor(p))
        self.sender.send("PLAYER_VEHICLE",
                         {"vehicle_id": vid, "class": klass, "role": role},
                         self.battle_id)

        map_id = _normalize_map(_get_geometry(arena))
        if map_id:
            payload = {"map_id": map_id}
            bounds = _get_bounds(arena)
            if bounds:
                payload["bounds"] = bounds
            self.sender.send("MAP_INFO", payload, self.battle_id)
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
                pv = _first(lambda: _player().playerVehicleID)
                try:
                    eff = self._eff_ctrl.getTotalEfficiency(pv)
                    _discovery_log("STATS: getTotalEfficiency(vid) = %r ; getters=%s" %
                                   (eff, [a for a in dir(eff) if not a.startswith("__")][:40]))
                except Exception as exc:
                    _discovery_log("STATS: getTotalEfficiency(vid) erreur: %s" % exc)
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

        # Degats/assist EN DIRECT via le controleur feedback (Fair Play : ta propre
        # contribution, deja affichee a l'ecran). Remplace getTotalEfficiency=0.
        try:
            sp = _resolve_session_provider()
            fb = _first(lambda: sp.shared.feedback)
            if fb is not None and hasattr(fb, "onPlayerFeedbackReceived") \
                    and not self._feedback_hooked:
                fb.onPlayerFeedbackReceived += self._on_feedback
                self._feedback_hooked = True   # une seule fois par bataille
                _discovery_log("STATS: hook onPlayerFeedbackReceived OK")
            elif fb is None:
                _discovery_log("STATS: feedback.onPlayerFeedbackReceived indisponible")
        except Exception:
            _discovery_log("STATS hook feedback:\n" + traceback.format_exc())

    def _on_feedback(self, events):
        """Callback feedback (thread principal) : accumule degats/assist et envoie.
        Sonde : detaille les premiers evenements pour verrouiller le format."""
        try:
            seq = events if isinstance(events, (list, tuple)) else [events]
        except Exception:
            seq = [events]
        for e in seq:
            try:
                self._feedback_dump_once(e)
                self._accumulate_feedback(e)
            except Exception:
                _log("feedback event:\n" + traceback.format_exc())

    def _feedback_dump_once(self, e):
        """Sonde : logge les VALEURS reelles des premiers evenements (type, degats,
        cible, role...) pour comprendre quel type porte les degats infliges."""
        if self._fb_dumped >= 3:
            return
        self._fb_dumped += 1
        etype = _first(lambda: e.getBattleEventType(), lambda: e.getType())
        extra = _first(lambda: e.getExtra())
        cls = extra.__class__.__name__ if extra is not None else None
        _log("FEEDBACK VAL type=%r extra=%s damage=%r rawdmg=%r crits=%r visible=%r target=%r role=%r count=%r"
             % (etype, cls,
                _first(lambda: e.getExtra().getDamage()),
                _first(lambda: getattr(e.getExtra(), "_DamageExtra__damage")),
                _first(lambda: e.getExtra().getCritsCount()),
                _first(lambda: bool(e.getExtra().isVisible)),
                _first(lambda: e.getTargetID()),
                _first(lambda: e.getRole()),
                _first(lambda: e.getCount())))

    def _accumulate_feedback(self, e):
        """Extrait degats/assist/spots d'un evenement feedback (best-effort) et
        envoie le cumul. Silencieux si rien d'exploitable.

        Format constate (journal b10) : type 7 = _DamageExtra.getDamage() = degats
        infliges ; type 0 = _VisibilityExtra (spot). L'assist chiffre n'est pas
        fourni cote client (calcule serveur) -> on compte les spots a la place."""
        extra = _first(lambda: e.getExtra())
        if extra is None:
            return
        # Spot : l'ennemi devient visible grace au joueur.
        if _first(lambda: bool(extra.isVisible)) is True:
            self._fb_spots += 1
        # ATTENTION : cote client Python 2, getDamage() renvoie un `long` (ex 690L),
        # pas un int -> on convertit via _as_int (isinstance(int,float) ratait tout).
        dmg = _as_int(_first(lambda: extra.getDamage(), lambda: extra.damage))
        assist = _as_int(_first(
            lambda: extra.getAssist(),
            lambda: (extra.getRadioAssist() or 0) + (extra.getTrackAssist() or 0),
        ))
        changed = False
        if dmg and dmg > 0:
            self._fb_damage += dmg
            changed = True
        if assist and assist > 0:
            self._fb_assist += assist
            changed = True
        if changed and self.battle_id is not None:
            self.sender.send("PLAYER_DAMAGE_DEALT",
                             {"total_damage": self._fb_damage}, self.battle_id)
            if self._fb_assist > 0:
                self.sender.send("PLAYER_ASSIST",
                                 {"total_assist": self._fb_assist}, self.battle_id)

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
        if max_hp:
            self._max_hp = max_hp
        if hp is not None and max_hp:
            self.sender.send("PLAYER_HP_CHANGED",
                             {"hp": max(0, hp), "max_hp": max_hp}, self.battle_id)

        arena = _get_arena(p)
        allies = enemies = 0
        counted = False
        own_alive = None
        for vid, team, klass, is_alive in _iter_arena_vehicles(arena):
            counted = True
            if vid == self._player_vid:
                own_alive = is_alive
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

        # Mort du joueur (drapeau isAlive de son propre vehicule) : signale HP=0
        # une seule fois, pour que la survie du garage soit correcte des la fin.
        if own_alive is False and not self._dead_sent and self._max_hp:
            self._dead_sent = True
            self.sender.send("PLAYER_HP_CHANGED",
                             {"hp": 0, "max_hp": self._max_hp}, self.battle_id)

        # Degats propres en direct (affiches a l'ecran par le jeu = Fair Play).
        dmg, assist = self._read_live_efficiency()
        if dmg is not None:
            self.sender.send("PLAYER_DAMAGE_DEALT", {"total_damage": dmg}, self.battle_id)
        if assist is not None:
            self.sender.send("PLAYER_ASSIST", {"total_assist": assist}, self.battle_id)

        # Positions du feed minimap (Fair Play) : soi, allies, ennemis SPOTTES.
        try:
            self._send_positions(p, arena)
        except Exception:
            _log("positions:\n" + traceback.format_exc())

    def _send_positions(self, p, arena):
        """Envoie POSITIONS a partir des entites repliquees au client.

        FAIR PLAY : un ennemi n'est inclus QUE s'il est actuellement visible pour
        le joueur, d'apres la liste que le jeu calcule lui-meme
        (feedback.getVisibleVehicles), avec repli sur le drapeau d'entite
        `isHidden`. Aucune lecture de position d'ennemi non spotte."""
        import BigWorld

        own = _first(
            lambda: _xz(p.getOwnVehiclePosition()),
            lambda: _xz(p.position),
        )
        visible_ids = self._visible_vehicle_ids()   # liste "vu par le joueur" du jeu
        allies = []
        enemies_spotted = []
        enemies_present = 0
        for vid, team, klass, is_alive in _iter_arena_vehicles(arena):
            if not is_alive or vid == self._player_vid:
                continue
            ent = _first(lambda: BigWorld.entity(vid))
            if ent is None:
                continue      # pas replique = hors de vue (ennemi non spotte, etc.)
            xz = _xz(_first(lambda: ent.position))
            if xz is None:
                continue
            if team == self.my_team:
                allies.append(xz)
            else:
                enemies_present += 1
                if self._enemy_is_spotted(ent, vid, visible_ids):
                    enemies_spotted.append(xz)

        # Diagnostic throttle (~toutes les 15 poll = 30 s) : visible dans le log
        # pour confirmer que les positions circulent en cours de bataille.
        self._pos_log_ctr += 1
        if self._pos_log_ctr % 15 == 1:
            _log("POSITIONS: own=%s allies=%d ennemis_presents=%d ennemis_spottes=%d"
                 % ("oui" if own else "non", len(allies), enemies_present,
                    len(enemies_spotted)))
            # Contribution en direct (feedback) : visible dans le python.log seul,
            # pour verifier les degats sans lancer le compagnon.
            _log("CONTRIB: degats=%d assist=%d spots=%d"
                 % (self._fb_damage, self._fb_assist, self._fb_spots))
        # Diagnostic unique : format brut de getVisibleVehicles, si un ennemi est
        # present mais aucun retenu (permet d'ajuster le parsing si besoin).
        if enemies_present and not enemies_spotted and not getattr(self, "_vis_dumped", False):
            self._vis_dumped = True
            _log("VISIBLE dump: type=%s sample=%r"
                 % (type(visible_ids).__name__, list(visible_ids)[:6] if visible_ids else visible_ids))

        if own is None and not allies and not enemies_spotted:
            return
        self.sender.send("POSITIONS", {
            "own": own, "allies": allies, "enemies_spotted": enemies_spotted,
        }, self.battle_id)

    @staticmethod
    def _visible_vehicle_ids():
        """Ensemble des vehicules ACTUELLEMENT visibles pour le joueur, tel que le
        jeu lui-meme le calcule (controleur feedback). C'est la reference Fair
        Play : exactement ce que le joueur voit. Retourne None si indisponible."""
        sp = _resolve_session_provider()
        fb = _first(lambda: sp.shared.feedback)
        if fb is None:
            return None
        vv = _first(lambda: fb.getVisibleVehicles())
        if vv is None:
            return None
        ids = set()
        try:
            for item in vv:
                vid = _first(lambda: item[0], lambda: item.vehicleID,
                             lambda: int(item))
                if vid is not None:
                    ids.add(vid)
        except Exception:
            return None
        return ids

    @staticmethod
    def _enemy_is_spotted(ent, vid, visible_ids):
        """Vrai uniquement si l'ennemi est ACTUELLEMENT visible au joueur.
        Priorite a la liste du jeu (getVisibleVehicles) ; a defaut, drapeau
        d'entite `isHidden` (masque = non spotte). Sans info fiable : EXCLU."""
        if visible_ids is not None:
            return vid in visible_ids
        hidden = _first(lambda: bool(ent.isHidden))
        return hidden is False   # explicitement non masque = visible

    def _read_live_efficiency(self):
        """Lit (degats, assist) propres via personalEfficiencyCtrl. Tolerant :
        essaie plusieurs accesseurs connus ; retourne (None, None) si indisponible
        (le nom exact sera confirme par la sonde du journal)."""
        ec = self._eff_ctrl
        if ec is None:
            return None, None
        pv = self._player_vid
        # getTotalEfficiency exige un argument (l'id du vehicule sur ce client).
        eff = _first(
            lambda: ec.getTotalEfficiency(pv),
            lambda: ec.getTotalEfficiency(),
        )
        if eff is None:
            return None, None
        dmg = _first(
            lambda: eff.getDamage(),
            lambda: eff.damage,
            lambda: eff.getDamageDealt(),
        )
        assist = _first(
            lambda: eff.getAssist(),
            lambda: eff.assist,
            lambda: (eff.getRadioAssist() or 0) + (eff.getTrackAssist() or 0),
        )
        return dmg, assist

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
        self._discover_positions(p, arena)
        self._discover_minimap()
        _discovery_log("Colle ce bloc au developpeur pour ajuster les hooks.")
        _discovery_log("=====================================")

    def _discover_minimap(self):
        """Sonde la GEOMETRIE de la minimap (resolution + taille) pour, a terme,
        caler automatiquement le radar dessus. On loggue tous les candidats : la
        formule exacte depend de la version du client, on l'ajuste depuis ce log."""
        _discovery_log("  --- MINIMAP (auto-taille radar) ---")

        def _bw():
            import BigWorld
            return BigWorld
        _probe("BigWorld.screenWidth()", lambda: _bw().screenWidth())
        _probe("BigWorld.screenHeight()", lambda: _bw().screenHeight())
        _probe("BigWorld.screenSize()", lambda: _bw().screenSize())
        # Reglage de taille de minimap (plusieurs cles/emplacements selon version).
        def _setting(key):
            from account_helpers.settings_core.SettingsCore import g_settingsCore
            return g_settingsCore.getSetting(key)
        for key in ("minimapSize", "MINIMAP_SIZE", "minimap_size"):
            _probe("getSetting(%s)" % key, (lambda k: (lambda: _setting(k)))(key))
        # Composant minimap de bataille (dimensions reelles si accessibles).
        _probe("battle app minimap size", self._probe_battle_minimap_size)

    @staticmethod
    def _probe_battle_minimap_size():
        from gui.app_loader import g_appLoader
        app = g_appLoader.getDefBattleApp()
        # On explore quelques attributs plausibles du composant minimap.
        comp = _first(
            lambda: app.containerManager.getView(1).components["minimap"],
            lambda: app.minimap,
        )
        return _first(
            lambda: comp.getMinimapSize(),
            lambda: (comp.width, comp.height),
            lambda: comp._size,
        )

    def _discover_positions(self, p, arena):
        """Sonde les positions LISIBLES cote joueur (Fair Play) : sa propre
        position + les positions du feed minimap (alliees, et ennemis DEJA
        spottes). Aucune lecture d'ennemi non spotte. On loggue seulement ce qui
        marche, pour cabler ensuite les regles spatiales."""
        _discovery_log("  --- POSITIONS (Fair Play : soi + minimap) ---")
        # 1) Position du joueur (plusieurs accesseurs connus).
        _probe("own getOwnVehiclePosition", lambda: tuple(p.getOwnVehiclePosition()))
        _probe("own player.position", lambda: tuple(p.position))
        _probe("own entity.position",
               lambda: tuple(__import__("BigWorld").entity(p.playerVehicleID).position))
        # 2) Positions via les ENTITES repliquees + liste "vu par le joueur" du jeu.
        #    Fair Play : un ennemi n'est retenu que s'il est dans getVisibleVehicles
        #    (ou, a defaut, non masque via isHidden).
        try:
            import BigWorld  # noqa: F401
            visible_ids = self._visible_vehicle_ids()
            allies = enemies_spotted = enemies_present = 0
            for vid, team, klass, alive in _iter_arena_vehicles(arena):
                if not alive or vid == p.playerVehicleID:
                    continue
                ent = _first(lambda: BigWorld.entity(vid))
                if ent is None or _xz(_first(lambda: ent.position)) is None:
                    continue
                if team == self.my_team:
                    allies += 1
                else:
                    enemies_present += 1
                    if self._enemy_is_spotted(ent, vid, visible_ids):
                        enemies_spotted += 1
            _discovery_log("  ENTITES : allies=%d ennemis_presents=%d "
                           "ennemis_spottes=%d visibleAPI=%s"
                           % (allies, enemies_present, enemies_spotted,
                              "oui" if visible_ids is not None else "non"))
        except Exception as exc:
            _discovery_log("  FAIL positions via entites : %s" % exc)


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
        _log("################################################")
        _log("#  WoT Companion  -  VERSION %-6s            #" % BUILD_TAG)
        _log("#  (garde UN seul .wotmod : supprime les vieux) #")
        _log("################################################")
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
