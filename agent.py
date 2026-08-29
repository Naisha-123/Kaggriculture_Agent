"""
Kaggriculture agent -- ground-up rebuild.

Every design choice here was empirically validated against the environment
(not just theorized) across dozens of test runs. Key lessons baked in:

  - Hands reset to 0 every day and hiring cost is a per-day Fibonacci
    sequence (1,1,2,3,5,8,...). There's no hard cap on hands, but going
    much past ~12-15/day gets uneconomical fast. UNDER-hiring is far worse
    than over-hiring: with too few hands, animals don't get fed/cared for
    and production stops completely, which no amount of saved cash fixes.
  - Buying more than 1 animal of a given type per day, even when
    affordable, destabilizes the early game (it compounds with the daily
    hiring cost and reliably causes bankruptcy in testing). Stick to a
    slow, steady ramp.
  - Sell every hour, not just once a day, so product doesn't sit around.
  - TOMATO cycles noticeably faster than STRAWBERRY under idle-time
    tending (observed ~11 units vs ~3 units from equal seed purchases),
    so the raw per-unit sell price isn't the whole story -- yield rate
    matters just as much.
  - Land expansion only pays off if there's enough remaining game left to
    earn back its cost. Waiting until the home quadrant is fully built out
    (~day 12-15) leaves too little runway. Buying land as soon as it's
    affordable (mirroring how a top human replay did it, ~day 6) is
    tested here as the main structural improvement over the previous
    version.
"""

ANIMAL_COST = {"COW": 400, "SHEEP": 500}
SHED_STOP = (4, 4)

HANDS_PER_STRUCTURE = 12 / 9   # matches the proven-good 12-hands-for-9-structures ratio
ANIMAL_RESERVE = 500
WHEAT_BUY_BUFFER = 20
TOMATO_SEED_TARGET = 6
LAND_RESERVE = 1500           # keep this much cash in hand after buying land
LAND_COST_EST = 1600          # rough estimate for the 2nd quadrant
BONUS_COW_COUNT = 3           # modest bonus structures once land is bought,
                               # so the extra hiring stays proportionate


def _home_structures(n_cow=7, n_sheep=2, shed_stop=SHED_STOP):
    candidates = sorted(
        [(x, y) for x in range(5) for y in range(5) if (x, y) != shed_stop],
        key=lambda p: abs(p[0] - shed_stop[0]) + abs(p[1] - shed_stop[1])
    )
    structs = []
    i = 0
    for animal, n in (("COW", n_cow), ("SHEEP", n_sheep)):
        for _ in range(n):
            structs.append({"pos": candidates[i], "animal": animal, "shed_stop": shed_stop})
            i += 1
    return structs


def _bonus_structures(n_cow=BONUS_COW_COUNT, shed_stop=SHED_STOP):
    # NE quadrant: x in [5,9], y in [0,4].
    candidates = sorted(
        [(x, y) for x in range(5, 10) for y in range(0, 5)],
        key=lambda p: abs(p[0] - shed_stop[0]) + abs(p[1] - shed_stop[1])
    )
    return [{"pos": p, "animal": "COW", "shed_stop": shed_stop} for p in candidates[:n_cow]]


HOME_STRUCTURES = _home_structures()
BONUS_STRUCTURES = _bonus_structures()
RESERVED = {s["pos"] for s in HOME_STRUCTURES} | {s["pos"] for s in BONUS_STRUCTURES}


def _pasture_needs_attention(tile):
    if tile is None:
        return True
    if isinstance(tile, dict) and tile.get("kind") == "PASTURE":
        if "animal" not in tile:
            return True
        if tile.get("yield_units", 0) > 0:
            return True
        if not tile.get("fed_today"):
            return True
        if not tile.get("cared_today"):
            return True
    return False


def _walk_toward(pos, dest):
    x, y = pos
    rx, ry = dest
    if x < rx:
        return ["EAST"]
    if x > rx:
        return ["WEST"]
    if y < ry:
        return ["SOUTH"]
    if y > ry:
        return ["NORTH"]
    return None


def _pasture_action(pos, tile, inv, shed, s):
    target_pos, shed_stop, animal = s["pos"], s["shed_stop"], s["animal"]
    if tile is None:
        step = _walk_toward(pos, target_pos)
        return step if step else ["BUILD_PASTURE"]
    if isinstance(tile, dict) and tile.get("kind") == "PASTURE":
        if "animal" not in tile:
            if inv.get(animal, 0) > 0:
                step = _walk_toward(pos, target_pos)
                return step if step else ["PLACE", animal]
            if shed.get(animal, 0) > 0:
                step = _walk_toward(pos, shed_stop)
                return step if step else ["PICKUP", animal, 1]
            return ["PASS"]
        if tile.get("yield_units", 0) > 0:
            step = _walk_toward(pos, target_pos)
            return step if step else ["HARVEST"]
        if not tile.get("fed_today"):
            if inv.get("WHEAT", 0) > 0:
                step = _walk_toward(pos, target_pos)
                return step if step else ["FEED"]
            if shed.get("WHEAT", 0) > 0:
                step = _walk_toward(pos, shed_stop)
                return step if step else ["PICKUP", "WHEAT", 1]
            return ["PASS"]
        if not tile.get("cared_today"):
            step = _walk_toward(pos, target_pos)
            return step if step else ["CARE"]
        return ["PASS"]
    return ["PASS"]


def _idle_crop_action(pos, tile, seeds, inv, day, core_done):
    x, y = pos
    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "TOMATO":
        if inv.get("FERTILIZER", 0) > 0 and tile.get("fertilized_until_day", -1) < day:
            return ["FERTILIZE"]
        if not tile.get("watered_today"):
            return ["WATER"]
        if tile.get("yield_units", 0) > 0:
            return ["HARVEST"]
        return ["PASS"]
    if core_done and tile is None and (x, y) not in RESERVED and seeds.get("TOMATO", 0) > 0:
        return ["PLANT", "TOMATO"]
    # Simple lawnmower sweep of the home quadrant while nothing else needs
    # doing -- covers ground for the idle-planting check above.
    if y % 2 == 0:
        if x < 4:
            return ["EAST"]
        return ["SOUTH"] if y < 4 else ["NORTH"]
    else:
        if x > 0:
            return ["WEST"]
        return ["SOUTH"] if y < 4 else ["NORTH"]


def my_agent(obs):
    player = obs["player"]
    farm = obs["farms"][player]
    tiles = farm["tiles"]
    private = obs["private"]
    seeds = private["seeds"]
    shed = private["shed"]
    money = farm["money"]
    day = obs["day"]
    unlocked = set(farm.get("unlocked_quadrants", ["NW"]))
    has_bonus_land = "NE" in unlocked

    active_structures = HOME_STRUCTURES + (BONUS_STRUCTURES if has_bonus_land else [])

    core_done = all(
        isinstance(tiles[s["pos"][1]][s["pos"][0]], dict) and tiles[s["pos"][1]][s["pos"][0]].get("animal") == s["animal"]
        for s in HOME_STRUCTURES
    )

    market_orders = []

    # Sell every hour, not just once a day, so product doesn't sit around
    # and risk hitting the shed cap.
    for product in ("WOOL", "MILK", "TOMATO"):
        amt = shed.get(product, 0)
        if amt > 0:
            market_orders.append(["SELL", product, amt])

    if obs["hour"] == 0:
        # 1) Feed buffer -- essential, goes first.
        wheat_have = shed.get("WHEAT", 0)
        if wheat_have < WHEAT_BUY_BUFFER and money > 500:
            market_orders.append(["BUY_PRODUCT", "WHEAT", WHEAT_BUY_BUFFER - wheat_have])

        # 2) Animals for empty pens, at most 1 of each type per day -- the
        #    proven-stable pace. Faster buying (tested at 2-3/day) reliably
        #    causes bankruptcy because it compounds with the daily hiring
        #    cost below.
        demand = {}
        for s in active_structures:
            sx, sy = s["pos"]
            t = tiles[sy][sx]
            placed = isinstance(t, dict) and t.get("animal") == s["animal"]
            if not placed:
                demand[s["animal"]] = demand.get(s["animal"], 0) + 1
        for animal, needed in demand.items():
            have = shed.get(animal, 0)
            cost = ANIMAL_COST[animal]
            to_buy = min(1, needed - have)
            for _ in range(to_buy):
                if money > cost + ANIMAL_RESERVE:
                    market_orders.append(["BUY_ANIMAL", animal, 1])
                    money -= cost

        # 3) Tomato seed for the idle-time bonus crop, once the core is
        #    fully staffed.
        if core_done and seeds.get("TOMATO", 0) < TOMATO_SEED_TARGET and money > 1000:
            market_orders.append(["BUY_SEED", "TOMATO", TOMATO_SEED_TARGET - seeds.get("TOMATO", 0)])

        # 4) Land expansion, bought as soon as affordable rather than
        #    waiting for the core to finish -- this is the main change from
        #    the previous version, aimed at giving the new land enough
        #    remaining days to earn back its cost.
        if not has_bonus_land and money > LAND_COST_EST + LAND_RESERVE:
            market_orders.append(["BUY_LAND"])
            money -= LAND_COST_EST

        # 5) Hiring, sized proportionally to however many structures are
        #    currently active (home 9, or home+bonus 12 once land is
        #    bought) -- flat and aggressive, matching the ratio that proved
        #    stable for the home quadrant alone. Being stingy here was
        #    tested and is worse: too few hands means nothing gets fed or
        #    harvested, which costs far more than the wages do.
        hire_count = max(1, round(len(active_structures) * HANDS_PER_STRUCTURE))
        hires_room = max(0, 10 - len(market_orders))
        for _ in range(min(hire_count, hires_room)):
            market_orders.append(["HIRE"])

    needing = []
    for s in active_structures:
        sx, sy = s["pos"]
        if _pasture_needs_attention(tiles[sy][sx]):
            needing.append(s)

    fx, fy = farm["farmer"]
    farmer_inv = private["inventories"][0] if private["inventories"] else {}
    if needing:
        s = needing[0]
        sx, sy = s["pos"]
        farmer_action = _pasture_action((fx, fy), tiles[sy][sx], farmer_inv, shed, s)
        needing = needing[1:]
    else:
        farmer_action = _idle_crop_action((fx, fy), tiles[fy][fx], seeds, farmer_inv, day, core_done)

    hands_actions = []
    hands = farm["hands"]
    for i, (hx, hy) in enumerate(hands):
        hand_inv = private["inventories"][i + 1] if i + 1 < len(private["inventories"]) else {}
        if needing:
            s = needing[0]
            sx, sy = s["pos"]
            hands_actions.append(_pasture_action((hx, hy), tiles[sy][sx], hand_inv, shed, s))
            needing = needing[1:]
        else:
            hands_actions.append(_idle_crop_action((hx, hy), tiles[hy][hx], seeds, hand_inv, day, core_done))

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders[:10]}


if __name__ == "__main__":
    from kaggle_environments import make

    env = make("kaggriculture", configuration={"episodeSteps": 720})
    env.run([my_agent, "random"])
    print("Agent score:", env.state[0]["reward"])
    print("Random score:", env.state[1]["reward"])