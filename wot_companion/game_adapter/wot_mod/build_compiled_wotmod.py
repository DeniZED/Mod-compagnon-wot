"""Construit un .wotmod contenant le mod COMPILE (.pyc).

Les clients WoT de release n'executent pas le code source `.py` embarque dans un
wotmod : ils n'importent que du bytecode `.pyc` compile pour LEUR version exacte
de Python (constatee sur les clients 2.x). Ce script compile
`mod_wotcompanion.py` avec l'interpreteur fourni, puis empaquette le `.pyc`.

Le `.pyc` doit etre compile avec la MEME version mineure de Python que le client
(3.8 -> 3.8). La version de correctif (3.8.x) n'a pas d'importance : le magic
bytecode est identique pour tout 3.8.

Usage :
    # compile avec l'interpreteur courant
    python -m wot_companion.game_adapter.wot_mod.build_compiled_wotmod

    # compile avec un interpreteur precis (recommande : celui du client)
    python .../build_compiled_wotmod.py --python /chemin/python3.8 --pyver 38
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

_HERE = Path(__file__).parent
_MOD_ID = "com.wotcompanion.bridge"
_SRC = _HERE / "mod_wotcompanion.py"
_ARCNAME = "res/scripts/client/gui/mods/mod_wotcompanion.pyc"


def compile_pyc(python_exe: str, out_pyc: Path) -> str:
    """Compile la source en .pyc avec l'interpreteur donne. Retourne le magic hex."""
    code = (
        "import py_compile;"
        f"py_compile.compile(r'{_SRC}', cfile=r'{out_pyc}', doraise=True)"
    )
    subprocess.run([python_exe, "-c", code], check=True)
    with open(out_pyc, "rb") as fh:
        return fh.read(4).hex()


def _build_tag() -> str:
    """Lit BUILD_TAG dans la source pour nommer le paquet (ex. b11)."""
    import re
    src = _SRC.read_text(encoding="utf-8")
    m = re.search(r'BUILD_TAG\s*=\s*"([^"]+)"', src)
    return m.group(1) if m else "dev"


def build(out_dir: Path, pyc: Path, pyver: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Nom VERSIONNE : une seule version a garder, l'ancienne se supprime sans
    # ambiguite. WoT charge n'importe quel *.wotmod du dossier.
    target = out_dir / f"WoTCompanion_{_build_tag()}.wotmod"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as z:
        z.write(_HERE / "meta.xml", "meta.xml")
        z.write(pyc, _ARCNAME)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build compiled .wotmod")
    parser.add_argument("--python", default=sys.executable,
                        help="Interpreteur pour compiler (idealement la version du client).")
    parser.add_argument("--pyver", default="",
                        help="Etiquette de version, ex. 38 (sinon deduite).")
    parser.add_argument("--out", default=str(_HERE / "dist"))
    args = parser.parse_args(argv)

    pyver = args.pyver
    if not pyver:
        info = subprocess.check_output(
            [args.python, "-c", "import sys;print('%d%d'%sys.version_info[:2])"]
        ).decode().strip()
        pyver = info

    pyc = _HERE / "mod_wotcompanion.pyc"
    magic = compile_pyc(args.python, pyc)
    target = build(Path(args.out), pyc, pyver)
    print(f"Compile avec {args.python} (py{pyver}), magic={magic}")
    print(f"Paquet compile cree : {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
