"""Pont IPC local par socket TCP (contrat EventEnvelope, section 9.2).

Protocole simple et robuste : une ligne = un objet JSON EventEnvelope, encodage
UTF-8, separateur '\\n'. Ecoute sur la boucle locale uniquement (127.0.0.1) :
l'IPC est limite au poste (section 10.2).

Deux roles :
  - `SocketEventServerAdapter` (cote compagnon) : serveur `GameAdapter` qui
    accepte une connexion (le mod / l'injecteur) et produit des `RawEvent`.
  - `EnvelopeClient` (cote source) : petit client qui envoie des envelopes.
    Utilisable depuis le mod WoT ou l'injecteur de test.

Messages de controle : un envelope dont `event_type` commence par "CTRL_" n'est
PAS un evenement de jeu (il ne passe pas par le FairPlayFilter) ; il pilote le
compagnon (ex: CTRL_SILENCE_TOGGLE, BAT-008).
"""
from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Iterator

from ..core.events import RawEvent
from .base import EventEnvelope, GameAdapter

logger = logging.getLogger("wot_companion.ipc")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 47800  # port local par defaut du pont WoT Companion
CONTROL_PREFIX = "CTRL_"


def envelope_to_line(env: EventEnvelope) -> bytes:
    return (json.dumps(env.as_dict(), ensure_ascii=False) + "\n").encode("utf-8")


def line_to_envelope(line: str) -> EventEnvelope | None:
    line = line.strip()
    if not line:
        return None
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("Ligne IPC illisible ignoree: %.80r", line)
        return None
    if not isinstance(d, dict) or "event_type" not in d:
        logger.warning("Envelope IPC invalide ignoree: %.80r", line)
        return None
    return EventEnvelope(
        event_type=d["event_type"],
        payload=d.get("payload", {}) or {},
        timestamp_ms=int(d.get("timestamp_ms", 0) or 0),
        battle_id=d.get("battle_id"),
        schema_version=d.get("schema_version", "1.0"),
        fairplay_class=d.get("fairplay_class", "ALLOW"),
    )


def is_control(event_type: str) -> bool:
    return event_type.startswith(CONTROL_PREFIX)


class SocketEventServerAdapter(GameAdapter):
    """Serveur GameAdapter : ecoute et transforme les envelopes en RawEvent.

    Accepte les connexions successives (le mod se connecte au lancement d'une
    partie, se reconnecte apres un patch/crash) : le flux d'evenements ne
    s'interrompt pas cote compagnon.

    Les messages de controle (CTRL_*) sont transmis au `control_handler`
    (s'il est fourni) plutot que produits comme evenements de jeu.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        control_handler=None,
        single_connection: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.control_handler = control_handler
        self.single_connection = single_connection
        self._server: socket.socket | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(1)
        srv.settimeout(0.5)
        self._server = srv
        # Port effectif (si port=0 demande, l'OS en choisit un).
        self.port = srv.getsockname()[1]
        logger.info("Pont IPC en ecoute sur %s:%d", self.host, self.port)

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass

    def close(self) -> None:
        self.stop()

    def events(self) -> Iterator[RawEvent]:
        if self._server is None:
            self.start()
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            logger.info("Source connectee: %s", addr)
            with conn:
                yield from self._handle_connection(conn)
            logger.info("Source deconnectee: %s", addr)
            if self.single_connection:
                break

    def _handle_connection(self, conn: socket.socket) -> Iterator[RawEvent]:
        conn.settimeout(0.5)
        buffer = b""
        while not self._stop.is_set():
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                break  # source deconnectee
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                env = line_to_envelope(raw.decode("utf-8", errors="replace"))
                if env is None:
                    continue
                if is_control(env.event_type):
                    if self.control_handler is not None:
                        try:
                            self.control_handler(env)
                        except Exception:
                            logger.exception("control_handler a echoue")
                    continue
                yield env.to_raw_event()


class EnvelopeClient:
    """Client leger pour ENVOYER des envelopes au compagnon (mod / injecteur).

    Conçu pour ne JAMAIS perturber l'appelant : toute erreur reseau est capturee
    (un mod ne doit pas planter le jeu, NFR-007). `connect(retry=...)` tente
    plusieurs fois si le compagnon n'est pas encore lance.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 timeout_s: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None

    def connect(self, retries: int = 0, backoff_s: float = 1.0) -> bool:
        import time
        for attempt in range(retries + 1):
            try:
                s = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
                self._sock = s
                return True
            except OSError as exc:
                logger.warning("Connexion au compagnon impossible (%d): %s", attempt + 1, exc)
                if attempt < retries:
                    time.sleep(backoff_s * (attempt + 1))
        return False

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def send(self, env: EventEnvelope) -> bool:
        if self._sock is None:
            return False
        try:
            self._sock.sendall(envelope_to_line(env))
            return True
        except OSError as exc:
            logger.warning("Envoi IPC echoue: %s", exc)
            self.close()
            return False

    def send_event(self, event_type: str, payload: dict | None = None,
                   battle_id: str | None = None, timestamp_ms: int = 0) -> bool:
        return self.send(EventEnvelope(
            event_type=event_type, payload=payload or {},
            battle_id=battle_id, timestamp_ms=timestamp_ms,
        ))

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
