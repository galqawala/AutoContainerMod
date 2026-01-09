from mods_base import build_mod, get_pc, hook, BoolOption, SliderOption
from unrealsdk.hooks import Type
import unrealsdk
import time
import os
from datetime import datetime

# Setup logging
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"autocontainer_{datetime.now().strftime('%Y%m%d')}.log")

def log_message(msg):
    print(msg)
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except:
        pass

# Cooldown and cache tracking
attempted_containers = {}
COOLDOWN_SECONDS = 30

# Object cache with TTL
_cached_containers = []
_cache_time = 0
CACHE_INTERVAL_SEC = 5.0  # Refresh cache every 5 seconds


def _safe_get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _is_map_transit(target):
    """Check if object is a map transit (fast, direct property check)."""
    interactive_def = _safe_get(target, "InteractiveObjectDefinition", None)
    if not interactive_def:
        return False
    def_str = str(interactive_def)
    return "MapChangeObjects" in def_str or "MapChanger" in def_str


def _try_call(target, method_name, argsets):
    """Try calling target.method_name with each args tuple in argsets."""
    if not hasattr(target, method_name):
        return False
    fn = getattr(target, method_name)
    for args in argsets:
        try:
            fn(*args)
            return True
        except Exception:
            continue
    return False


def get_distance(a, b):
    dx = a.X - b.X
    dy = a.Y - b.Y
    dz = a.Z - b.Z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def try_open(target, pawn, pc):
    """Try to open container. Block map transits based on InteractiveObjectDefinition."""
    obj_name = _safe_get(target, "Name", "Unknown")
    
    # Early exit for map transits
    if _is_map_transit(target):
        return False
    
    # Try to open the container
    if _try_call(target, "UsedBy", [(pawn,), (pawn, get_pc())]):
        log_message(f"[AutoContainer] Opened {obj_name}")
        return True
    
    return False


def _get_nearby_containers(player_location, max_distance):
    """Get cached containers filtered by distance. Cache updates every 5 seconds."""
    global _cached_containers, _cache_time
    
    current_time = time.time()
    
    # Refresh cache periodically (expensive operation)
    if current_time - _cache_time > CACHE_INTERVAL_SEC:
        all_objects = unrealsdk.find_all("WillowInteractiveObject")
        _cached_containers = [obj for obj in all_objects 
                             if obj and _safe_get(obj, "Location", None)]
        _cache_time = current_time
    
    # Filter cached results by distance (fast)
    nearby = []
    for obj in _cached_containers:
        obj_loc = _safe_get(obj, "Location", None)
        if obj_loc:
            dist = get_distance(obj_loc, player_location)
            if dist <= max_distance:
                nearby.append((obj, dist))
    
    return nearby

auto_open_enabled = BoolOption("Auto Open Enabled", True)
open_range = SliderOption("Open Range", 300, 100, 1000, 50)

check_counter = 0


@hook("WillowGame.WillowPlayerController:PlayerTick", Type.POST)
def auto_open_containers(obj, __args, __ret, __func):
    global check_counter

    if not auto_open_enabled.value:
        return

    check_counter += 1
    if check_counter % 30 != 0:  # Check ~2x per second (60 Hz / 30 = ~2 Hz)
        return

    pc = get_pc()
    if pc is None or pc.Pawn is None:
        return

    pawn = pc.Pawn
    player_location = _safe_get(pawn, "Location", None)
    if not player_location:
        return

    try:
        # Get nearby containers from cache
        nearby = _get_nearby_containers(player_location, open_range.value)
        
        if not nearby:
            return

        # Get closest container
        nearest = min(nearby, key=lambda x: x[1])[0]
        container_id = id(nearest)
        current_time = time.time()

        # Check cooldown
        if container_id in attempted_containers:
            if current_time - attempted_containers[container_id] < COOLDOWN_SECONDS:
                return

        # Try to open (this calls try_open which checks for transits)
        try_open(nearest, pawn, pc)
        attempted_containers[container_id] = current_time

    except Exception:
        pass


build_mod()
