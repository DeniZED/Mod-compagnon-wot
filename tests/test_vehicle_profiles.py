"""Tests des Vehicle Tactical Profiles (§6, §24) : hiérarchie de fallback."""
from __future__ import annotations

from wot_companion.tactical_knowledge.models import (
    Archetype, VehicleClass, VehicleTacticalProfile)
from wot_companion.tactical_knowledge.vehicle_profiles import (
    VehicleProfileResolver, resolve_profile)


# ---- Fallback exact -> archétype -> classe -> neutre (§6.3, §24) ------------
def test_exact_profile_wins():
    exact = VehicleTacticalProfile(
        vehicle_id="germany:G56_E-100", vehicle_class=VehicleClass.HEAVY,
        archetype=Archetype.SUPER_HEAVY, armor=0.99)
    r = VehicleProfileResolver({"germany:G56_E-100": exact}).resolve(
        vehicle_id="germany:G56_E-100", vehicle_class="heavy")
    assert r.source == "exact"
    assert r.profile.armor == 0.99
    assert r.confidence == 0.9


def test_archetype_fallback_from_known_tag():
    # Tag connu dans ARCHETYPE_BY_TAG -> profil archétype (super heavy).
    r = resolve_profile(vehicle_id="germany:G56_E-100", vehicle_class="heavy")
    assert r.source == "archetype"
    assert r.profile.archetype is Archetype.SUPER_HEAVY
    assert r.profile.vehicle_class is VehicleClass.HEAVY
    assert r.profile.armor > 0.9            # super heavy = très blindé


def test_explicit_archetype_used():
    r = resolve_profile(vehicle_id="unknown:tank", archetype=Archetype.SNIPER_TD)
    assert r.source == "archetype"
    assert r.profile.accuracy > 0.8         # sniper TD = précis


def test_class_fallback_for_unknown_vehicle():
    # Tag inconnu mais classe live fournie -> repli classe.
    r = resolve_profile(vehicle_id="unknown:tank", vehicle_class="light")
    assert r.source == "class"
    assert r.profile.vehicle_class is VehicleClass.LIGHT
    assert r.profile.view_range > 0.7       # light = bonne vue
    assert r.confidence == 0.5


def test_default_when_nothing_known():
    r = resolve_profile()
    assert r.source == "default"
    assert r.confidence == 0.3
    assert r.profile.armor == 0.5           # neutre


def test_class_string_is_coerced():
    r = resolve_profile(vehicle_class="TD")     # majuscule tolérée
    assert r.profile.vehicle_class is VehicleClass.TD
    assert r.source == "class"


def test_profiles_are_bounded():
    # Toutes les tables produisent des indices dans [0,1] (post_init clamp).
    for arch in Archetype:
        r = resolve_profile(archetype=arch)
        p = r.profile
        for f in ("mobility", "armor", "dpm", "camouflage", "accuracy",
                  "hp_role_value"):
            assert 0.0 <= getattr(p, f) <= 1.0


def test_confidence_ordering():
    # exact > archetype > class > default (§14).
    exact = VehicleTacticalProfile(
        vehicle_id="t", vehicle_class=VehicleClass.MEDIUM,
        archetype=Archetype.FLEXIBLE_MEDIUM)
    res = VehicleProfileResolver({"t": exact})
    c_exact = res.resolve(vehicle_id="t").confidence
    c_arch = resolve_profile(archetype=Archetype.SNIPER_MEDIUM).confidence
    c_class = resolve_profile(vehicle_class="medium").confidence
    c_def = resolve_profile().confidence
    assert c_exact > c_arch > c_class > c_def


def test_autoloader_has_clip():
    r = resolve_profile(archetype=Archetype.AUTOLOADER_MEDIUM)
    assert r.profile.is_autoloader
    assert r.profile.clip >= 3
