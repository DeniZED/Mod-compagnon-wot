"""Construit le paquet .wotmod installable a partir de ce dossier.

Un .wotmod est une archive ZIP (sans compression) avec la structure :

    meta.xml
    res/scripts/client/gui/mods/mod_wotcompanion.py

Usage :
    python -m wot_companion.game_adapter.wot_mod.build_wotmod
    python wot_companion/game_adapter/wot_mod/build_wotmod.py --out dist/

Le fichier produit se copie dans :
    <World_of_Tanks>/mods/<version_du_jeu>/com.wotcompanion.bridge_0.1.0.wotmod
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

_HERE = Path(__file__).parent
_MOD_ID = "com.wotcompanion.bridge"
_VERSION = "0.1.0"
_SCRIPT_ARCNAME = "res/scripts/client/gui/mods/mod_wotcompanion.py"


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{_MOD_ID}_{_VERSION}.wotmod"
    # .wotmod = ZIP STORED (non compresse), comme l'exige le client.
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as z:
        z.write(_HERE / "meta.xml", "meta.xml")
        z.write(_HERE / "mod_wotcompanion.py", _SCRIPT_ARCNAME)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build .wotmod")
    parser.add_argument("--out", default=str(_HERE / "dist"))
    args = parser.parse_args(argv)
    target = build(Path(args.out))
    print(f"Paquet cree : {target}")
    print("Copie-le dans : <World_of_Tanks>/mods/<version_du_jeu>/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
