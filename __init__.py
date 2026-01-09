from mods_base import build_mod, get_pc, hook, SliderOption
from unrealsdk.hooks import Type
from unrealsdk import logging
import unrealsdk
import time

# Cooldown tracking
attempted_containers = {}
COOLDOWN_SECONDS = 30

open_range = SliderOption("Open Range", 300, 100, 1000, 50)

# Cache containers
cached_containers = []
last_cache_time = 0
CACHE_INTERVAL = 5.0
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
    if tick_counter % 30 != 0:  # Check every 30 ticks
        return
    
    pc = get_pc()
    if not pc or not pc.Pawn:
        return
    
    pawn_location = getattr(pc.Pawn, "Location", None)
    if not pawn_location:
        return
    
    current_time = time.time()
    
    # Refresh container cache periodically
    if current_time - last_cache_time > CACHE_INTERVAL:
        all_objects = unrealsdk.find_all("WillowInteractiveObject")
        cached_containers = [obj for obj in all_objects if obj]
        last_cache_time = current_time
    
    # Check each container
    for container in cached_containers:
        # Skip map transits
        if is_map_transit(container):
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
        if container_id in attempted_containers:
            if current_time - attempted_containers[container_id] < COOLDOWN_SECONDS:
                continue
        
        # Try to open
        if hasattr(container, "UsedBy") and callable(container.UsedBy):
            try:
                container.UsedBy(pc.Pawn)
                obj_name = getattr(container, "Name", "Unknown")
                logging.info(f"[AutoContainer] Opened {obj_name}")
                attempted_containers[container_id] = current_time
            except Exception as e:
                logging.error(f"[AutoContainer] Failed to open: {e}")


build_mod()
