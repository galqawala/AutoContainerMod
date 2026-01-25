from mods_base import build_mod, get_pc, hook, SliderOption
from unrealsdk.hooks import Type
from unrealsdk import logging
import unrealsdk
import time

# Cooldown tracking
attempted_containers = {}
COOLDOWN_SECONDS = 30

open_range = SliderOption("Open Range", 1000, 100, 2000, 50)

tick_counter = 0


def get_distance(a, b):
    """Calculate distance between two location structs."""
    dx = a.X - b.X
    dy = a.Y - b.Y
    dz = a.Z - b.Z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def is_map_transit(target):
    """Check if object is a map transit using InteractiveObjectDefinition."""
    interactive_def = getattr(target, "InteractiveObjectDefinition", None)
    if not interactive_def:
        return False
    def_str = str(interactive_def)
    return "MapChangeObjects" in def_str or "MapChanger" in def_str


@hook("WillowGame.WillowPlayerController:PlayerTick", Type.POST)
def on_player_tick(obj, __args, __ret, __func):
    """Check for nearby containers to auto-open."""
    global cached_containers, last_cache_time, tick_counter
    
    tick_counter += 1
    if tick_counter % 60 != 0:
        return
    
    pc = get_pc()
    if not pc or not pc.Pawn:
        return
    
    pawn_location = getattr(pc.Pawn, "Location", None)
    if not pawn_location:
        return
    
    current_time = time.time()

    # Always query fresh objects to avoid stale pointers across map transitions (fast travel)
    try:
        all_objects = unrealsdk.find_all("WillowInteractiveObject")
    except Exception as e:
        logging.error(f"[AutoContainer] find_all failed: {e}")
        return

    # Filter only objects that look usable right now
    valid_containers = [obj for obj in all_objects if obj and hasattr(obj, "Location") and hasattr(obj, "UsedBy") and callable(getattr(obj, "UsedBy", None))]
    logging.info(f"[AutoContainer] Checking {len(valid_containers)} containers...")

    current_container_ids = set()
    for container in valid_containers:
        current_container_ids.add(id(container))
        logging.info(f"[AutoContainer] Checking container: {container}")

        # Skip map transits (guard with try/except in case of odd objects)
        try:
            if is_map_transit(container):
                continue
        except Exception as e:
            logging.warning(f"[AutoContainer] is_map_transit check failed: {e}")
            continue

        # Check location and distance
        obj_location = getattr(container, "Location", None)
        if not obj_location:
            continue

        distance = get_distance(obj_location, pawn_location)
        if distance > open_range.value:
            continue

        # Check cooldown
        container_id = id(container)
        last_attempt = attempted_containers.get(container_id)
        if last_attempt and (current_time - last_attempt) < COOLDOWN_SECONDS:
            continue

        # Try to open
        try:
            obj_name = getattr(container, "Name", "Unknown")
            logging.info(f"[AutoContainer] Opening {obj_name}")
            container.UsedBy(pc.Pawn)
            attempted_containers[container_id] = current_time
        except Exception as e:
            logging.error(f"[AutoContainer] Failed to open: {e}")

    # Prune cooldown entries for containers no longer present
    stale_ids = [cid for cid in list(attempted_containers.keys()) if cid not in current_container_ids]
    for cid in stale_ids:
        del attempted_containers[cid]

    logging.info(f"[AutoContainer] containers processed.")

build_mod()
