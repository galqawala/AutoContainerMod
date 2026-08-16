from mods_base import build_mod, get_pc, hook, SliderOption
from unrealsdk.hooks import Type
from unrealsdk import logging
import unrealsdk

open_range = SliderOption("Open Range", 1000, 100, 2000, 100)
tick_counter = 0
# Same non-treasure objects (turrets, barrels, map changers, story props)
# stay in range for as long as the player stands near them, and the
# discovery log below used to fire every scan tick for every one of them -
# confirmed spamming the log with dozens of repeats of the exact same
# InteractiveObjectDefinition path per session. Logging each distinct path
# once is enough to spot a missing treasure prefix; nothing is lost by not
# repeating it.
_logged_non_treasure = set()
_warned_remote_client = False


def is_host(pc) -> bool:
    """Whether the LOCAL player has authority - the host, not a remote
    client in someone else's game.

    WillowInteractiveObject.UsedBy() is a plain function - calling it
    directly only ever runs LOCALLY, with no replication at all. Vanilla's
    own F-key interact (Engine.PlayerController.uc: exec function Use())
    never calls UsedBy() locally on a client: on the host it runs
    PerformedUseAction() (which reaches UsedBy()) directly, and also fires
    ServerUse() - a same-process no-op there since the host already IS the
    server; on a CLIENT, Use() only ever fires the ServerUse() RPC, which
    executes purely server-side, and the client waits for ordinary actor
    replication to show the result.

    Calling UsedBy() directly from a client, as this mod used to
    unconditionally, opens the container as a purely local, non-replicated
    cosmetic effect the server never learns about - the very next
    replication tick then snaps the container's real (still-closed) state
    back, and the next scan (every ~1s) sees it "still closed" and reopens
    it locally again, forever. Confirmed in play: a lid visibly opening,
    snapping shut, and reopening in a loop, specifically when joining
    another player's game.

    ROLE_Authority=3 (Engine.Actor.ENetRole, confirmed in the BL1E dump) -
    an unreadable Role fails toward "not the host" rather than risking the
    same loop.
    """
    try:
        return int(pc.Role) == 3
    except Exception:  # noqa: BLE001
        return False


def get_distance(a, b):
    """Calculate distance between two location structs."""
    dx = a.X - b.X
    dy = a.Y - b.Y
    dz = a.Z - b.Z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


# Every InteractiveObjectDefinition package prefix confirmed (by the actual
# def_str logged below, not guessed) to be a lootable container rather than
# a door/switch/vending machine/story object - WillowInteractiveObject
# covers ALL of those, so this list is deliberately an allow-list, not a
# single hardcoded name. Extend it as new prefixes are confirmed.
TREASURE_PACKAGE_PREFIXES = (
    "InteractiveObjectDefinition'gd_Balance_Treasure.InteractiveObjects.",
)


def is_treasure(target):
    """Check if object is a treasure using InteractiveObjectDefinition."""
    interactive_def = getattr(target, "InteractiveObjectDefinition", None)
    if not interactive_def:
        return False
    def_str = str(interactive_def)
    return def_str.startswith(TREASURE_PACKAGE_PREFIXES)


@hook("WillowGame.WillowPlayerController:PlayerTick", Type.POST)
def on_player_tick(obj, __args, __ret, __func):
    """Check for nearby treasures to auto-open."""
    global tick_counter
    
    tick_counter += 1
    if tick_counter % 60 != 0:
        return
    
    pc = get_pc()
    if not pc or not pc.Pawn:
        return

    if not is_host(pc):
        global _warned_remote_client
        if not _warned_remote_client:
            _warned_remote_client = True
            logging.warning(
                "[AutoContainer] this player is a remote client, not the host -"
                " auto-open only works for the host (see is_host() for why),"
                " so it's disabled here. Manual use is unaffected. (Not logged"
                " again this session.)"
            )
        return

    pawn_location = getattr(pc.Pawn, "Location", None)
    if not pawn_location:
        return

    # Always query fresh objects to avoid stale pointers across map transitions (fast travel)
    try:
        all_objects = unrealsdk.find_all("WillowInteractiveObject")
    except Exception as e:
        logging.error(f"[AutoContainer] find_all failed: {e}")
        return

    for obj_candidate in all_objects:
        obj_location = getattr(obj_candidate, "Location", None)
        if not obj_location:
            continue
        if get_distance(obj_location, pawn_location) > open_range.value:
            continue
        interactive_def = getattr(obj_candidate, "InteractiveObjectDefinition", None)
        if not interactive_def:
            continue
        if is_treasure(obj_candidate):
            try:
                obj_candidate.UsedBy(pc.Pawn)
            except Exception as e:
                logging.error(f"[AutoContainer] Failed to open {interactive_def}: {e}")
        else:
            # Logged once per distinct InteractiveObjectDefinition path, not
            # every tick - the whole point is to see the real path for
            # containers this mod is currently missing (TREASURE_PACKAGE_
            # PREFIXES is an allow-list, not exhaustive), rather than
            # guessing at package names. See _logged_non_treasure above.
            def_str = str(interactive_def)
            if def_str not in _logged_non_treasure:
                _logged_non_treasure.add(def_str)
                logging.info(f"[AutoContainer] in range but not a recognised treasure: {def_str}")

build_mod()
