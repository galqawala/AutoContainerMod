from mods_base import build_mod, get_pc, hook, SliderOption
from unrealsdk.hooks import Type
from unrealsdk import logging
import unrealsdk
import time

open_range = SliderOption("Open Range", 1000, 100, 2000, 100)
tick_counter = 0

def get_distance(a, b):
    """Calculate distance between two location structs."""
    dx = a.X - b.X
    dy = a.Y - b.Y
    dz = a.Z - b.Z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def is_treasure(target):
    """Check if object is a treasure using InteractiveObjectDefinition."""
    interactive_def = getattr(target, "InteractiveObjectDefinition", None)
    if not interactive_def:
        return False
    def_str = str(interactive_def)
    return def_str.startswith("InteractiveObjectDefinition'gd_Balance_Treasure.InteractiveObjects.")


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
    valid_treasures = [obj for obj in all_objects if is_treasure(obj)]

    for treasure in valid_treasures:
        # Check location and distance
        obj_location = getattr(treasure, "Location", None)
        if not obj_location:
            continue

        distance = get_distance(obj_location, pawn_location)
        if distance > open_range.value:
            continue

        # Try to open
        try:
            treasure.UsedBy(pc.Pawn)
        except Exception as e:
            logging.error(f"[AutoContainer] Failed to open: {e}")

build_mod()
