"""HistoryStore : persistance locale SQLite (GAR-002).

Local-first (section 10.3). Stockage transactionnel, consultable sur des
milliers de batailles sans ralentissement (index sur vehicle/date).
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import APP_VERSION
from ..core.context.battle_context import BattleContext

SCHEMA_VERSION = 2
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
EARLY_HP_LOSS_WINDOW_S = 180.0  # 3 min

# Migration v2 : trace tactique legere (Moteur V2, §34). Une ligne par instant
# echantillonne d'une bataille -> base pour PositionCluster / coach personnel.
_MIGRATION_V2 = """
CREATE TABLE IF NOT EXISTS battle_states (
    battle_id     TEXT,
    t_s           REAL,      -- temps de bataille (s)
    x             REAL,      -- position propre (plan horizontal)
    z             REAL,
    hp_ratio      REAL,
    damage        REAL,
    assist        REAL,
    allies_near   INTEGER,
    enemies_near  INTEGER,   -- ennemis SPOTTES proches (Fair Play)
    phase         TEXT,
    FOREIGN KEY (battle_id) REFERENCES battles(id)
);
CREATE INDEX IF NOT EXISTS idx_states_battle ON battle_states(battle_id);
"""


@dataclass
class BattleRecord:
    id: str
    map_id: str | None
    spawn: str | None
    vehicle_id: str | None
    vehicle_role: str | None
    result: str | None
    damage: float
    assist: float
    survived: bool
    kills: int
    hp_ratio_end: float | None
    hp_lost_early: bool
    started_ms: int | None = None
    ended_ms: int | None = None


@dataclass
class BattleState:
    """Instant echantillonne d'une bataille (trace tactique legere, V2 §34)."""
    t_s: float
    x: float | None
    z: float | None
    hp_ratio: float | None
    damage: float = 0.0
    assist: float = 0.0
    allies_near: int = 0
    enemies_near: int = 0
    phase: str | None = None


class HistoryStore:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        # check_same_thread=False : avec l'overlay graphique, le moteur tourne dans
        # un thread separe de la boucle Tk. Les acces DB restent serialises (seul le
        # thread moteur ecrit), donc c'est sûr.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    # ---- Migration versionnee (section 12.3) -------------------------------
    def _migrate(self) -> None:
        cur = self.conn.cursor()
        version = cur.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            cur.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
            version = 1
        if version < 2:
            cur.executescript(_MIGRATION_V2)
            version = 2
        cur.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()
        # Les migrations futures (version 3...) s'ajoutent ici, incrementales et
        # couvertes par des tests.

    # ---- Ecriture ----------------------------------------------------------
    def record_from_context(self, ctx: BattleContext) -> BattleRecord:
        """Construit et enregistre un BattleRecord depuis un contexte termine."""
        hp_lost_early = self._compute_hp_lost_early(ctx)
        # Survie : donnee autoritaire du resultat si disponible, sinon heuristique HP.
        if ctx.result_survived is not None:
            survived = ctx.result_survived
        else:
            survived = bool(ctx.hp_ratio and ctx.hp_ratio > 0)
        rec = BattleRecord(
            id=ctx.battle_id, map_id=ctx.map_id, spawn=ctx.spawn,
            vehicle_id=ctx.vehicle_id, vehicle_role=ctx.vehicle_role,
            result=ctx.result, damage=ctx.total_damage, assist=ctx.total_assist,
            survived=survived, kills=ctx.kills,
            hp_ratio_end=ctx.hp_ratio, hp_lost_early=hp_lost_early,
            started_ms=ctx.start_ms, ended_ms=ctx.end_ms,
        )
        self.save_battle(rec)
        return rec

    def _compute_hp_lost_early(self, ctx: BattleContext) -> bool:
        # Heuristique locale : si le joueur est deja bas tot dans la partie.
        if ctx.hp_ratio is None:
            return False
        return ctx.elapsed_s <= EARLY_HP_LOSS_WINDOW_S and ctx.hp_ratio < 0.5

    def save_battle(self, rec: BattleRecord) -> None:
        with self.conn:  # transaction (REC-08)
            self.conn.execute(
                """INSERT OR REPLACE INTO battles
                   (id, started_ms, ended_ms, map_id, spawn, vehicle_id, vehicle_role,
                    result, damage, assist, survived, kills, hp_ratio_end,
                    hp_lost_early, app_version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec.id, rec.started_ms, rec.ended_ms, rec.map_id, rec.spawn,
                 rec.vehicle_id, rec.vehicle_role, rec.result, rec.damage, rec.assist,
                 int(rec.survived), rec.kills, rec.hp_ratio_end,
                 int(rec.hp_lost_early), APP_VERSION),
            )

    def add_metric(self, battle_id: str, code: str, value: float,
                   timestamp_ms: int | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO battle_metrics (battle_id, metric_code, value, timestamp_ms)"
                " VALUES (?,?,?,?)",
                (battle_id, code, value, timestamp_ms or int(time.time() * 1000)),
            )

    # ---- Trace tactique legere (V2, §34) -----------------------------------
    def record_state(self, battle_id: str, state: "BattleState") -> None:
        """Enregistre un instant echantillonne d'une bataille."""
        with self.conn:
            self.conn.execute(
                """INSERT INTO battle_states
                   (battle_id, t_s, x, z, hp_ratio, damage, assist,
                    allies_near, enemies_near, phase)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (battle_id, state.t_s, state.x, state.z, state.hp_ratio,
                 state.damage, state.assist, state.allies_near,
                 state.enemies_near, state.phase),
            )

    def battle_states(self, battle_id: str) -> list["BattleState"]:
        rows = self.conn.execute(
            "SELECT * FROM battle_states WHERE battle_id = ? ORDER BY t_s",
            (battle_id,),
        ).fetchall()
        return [BattleState(
            t_s=r["t_s"], x=r["x"], z=r["z"], hp_ratio=r["hp_ratio"],
            damage=r["damage"], assist=r["assist"], allies_near=r["allies_near"],
            enemies_near=r["enemies_near"], phase=r["phase"],
        ) for r in rows]

    def count_states(self, battle_id: str | None = None) -> int:
        if battle_id:
            return self.conn.execute(
                "SELECT COUNT(*) FROM battle_states WHERE battle_id = ?",
                (battle_id,)).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM battle_states").fetchone()[0]

    # ---- Lecture -----------------------------------------------------------
    def recent_battles(self, limit: int = 20, vehicle_id: str | None = None
                       ) -> list[BattleRecord]:
        q = "SELECT * FROM battles"
        params: list[Any] = []
        if vehicle_id:
            q += " WHERE vehicle_id = ?"
            params.append(vehicle_id)
        q += " ORDER BY started_ms DESC, rowid DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(q, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def count_battles(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0]

    def _row_to_record(self, r: sqlite3.Row) -> BattleRecord:
        return BattleRecord(
            id=r["id"], map_id=r["map_id"], spawn=r["spawn"],
            vehicle_id=r["vehicle_id"], vehicle_role=r["vehicle_role"],
            result=r["result"], damage=r["damage"], assist=r["assist"],
            survived=bool(r["survived"]), kills=r["kills"],
            hp_ratio_end=r["hp_ratio_end"], hp_lost_early=bool(r["hp_lost_early"]),
            started_ms=r["started_ms"], ended_ms=r["ended_ms"],
        )

    # ---- Gestion des donnees (section 8.2) ---------------------------------
    def delete_all(self) -> None:
        """Option "supprimer toutes mes donnees"."""
        with self.conn:
            self.conn.execute("DELETE FROM battle_metrics")
            self.conn.execute("DELETE FROM battles")

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
                (key, value, int(time.time() * 1000)),
            )

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def close(self) -> None:
        self.conn.close()
