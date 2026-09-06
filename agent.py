"""
Kaggriculture submission agent.

Strategy: 9 workers (farmer + 8 hired hands), each permanently assigned a
fixed cluster of 3 adjacent structures in the NW quadrant -- one COW
pasture, one SHEEP pasture, one GOOSE coop (27 slots requested, 25 exist
in NW, so 2 sit idle -- harmless). Diversifying across three different
animal products, rather than stacking one type, was the single biggest
stability win in testing: an all-COW strategy occasionally saw its milk
price crash to near-zero on seeds where no milk-relevant town shop
happened to unlock (town-shop unlocks are random and there is no price
recovery mechanism for oversupply in this game other than town/shop
consumption). Spreading output across milk/wool/egg means a bad-luck
outcome for one product's demand doesn't sink the whole farm's income.

Validated with harness.py, n=15 trials vs. a random opponent:
  mean ~56,000 | min ~45,600 | max ~71,000  (717-step episodes)
This is well above the previously-submitted baseline (~38k-41k avg).

Key mechanics this design is built around (confirmed against the actual
env source, kaggle_environments/envs/kaggriculture/kaggriculture.py):

  * Hands reset to an EMPTY list every single day -- you must re-hire from
    scratch each morning. The n-th hire of a day costs mult*fib(n)
    (fib(0)=1,1,2,3,5,...), reset daily but paid every day forever. This
    cost grows exponentially with headcount, so the practical ceiling on
    total workers (for a 30-day episode) is small (~9-12) -- scaling
    animal count further has to come from each worker tending MULTIPLE
    animals, not from hiring more workers.
  * BUILD_PASTURE / BUILD_COOP are free; only the animal itself costs
    money (COW 400, SHEEP 500, GOOSE 300).
  * PICKUP/DROP (shed <-> personal inventory) only works standing on one
    of the 4 shed-access tiles; everything else works anywhere.
  * Feed wheat is bought directly (BUY_PRODUCT WHEAT) -- it lands straight
    in the shed, skipping growing it entirely.
  * Animals passively generate 1 free FERTILIZER/day (COLLECT_FERTILIZER);
    with no crops in this design, it's just sold for extra cash.
  * Hiring the full target headcount on day 0 -- before any income exists
    (first milk isn't until day ~10) -- is a "poverty trap": payroll
    outruns cash before revenue arrives, and once broke you can't hire OR
    buy feed, which is unrecoverable. Fixed by ramping headcount up in
    lockstep with animals actually owned, and never letting the headcount
    shrink again even if a temporary setback (e.g. an animal escaping
    after 2 missed feeds) briefly lowers the owned count.
  * Land purchase (unlocking NE/SW/SE quadrants, 25 more tiles each) was
    tested and made things WORSE within a single 30-day episode -- the
    land cost + extra travel distance + extra Fibonacci payroll for more
    workers outweighs the extra animal output in the time available. This
    design deliberately stays inside the free NW quadrant.

To adapt: `make_agent(worker_animal_lists)` is the general building block
(see the bottom of this file for how `my_agent` is constructed from it) --
swap in a different worker/animal-count pattern if you want to explore
further before the fib-cost ceiling and market-price fragility win out.
"""

SHED = (4, 4)
ANIMAL_STRUCTURE = {"COW": "PASTURE", "SHEEP": "PASTURE", "GOOSE": "COOP"}
ANIMAL_COST = {"COW": 400, "SHEEP": 500, "GOOSE": 300}
# WHEAT deliberately absent: it's bought purely as feed and must never be
# resold (an early bug here sold wheat back the same turn it was bought,
# starving every animal of feed).
SELL_CAP = {"MILK": 4, "WOOL": 3, "EGG": None, "FERTILIZER": None}
MAX_ORDERS = 10
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]


def _quadrant_rank(x, y, board_size=10):
    half = board_size // 2
    ns = 0 if y < half else 1
    we = 0 if x < half else 1
    return {(0, 0): 0, (0, 1): 1, (1, 0): 2, (1, 1): 3}[(ns, we)]


def _all_positions(n, board_size=10):
    """All board tiles, quadrant-major (NW fully first, matching the free
    starting quadrant), closest-to-shed within each quadrant."""
    cells = [(x, y) for y in range(board_size) for x in range(board_size)]
    cells.sort(key=lambda p: (_quadrant_rank(p[0], p[1], board_size), abs(p[0] - 4) + abs(p[1] - 4)))
    return cells[:n]


def _walk(pos, dest):
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


def _needs_attention(tile):
    if tile is None:
        return True
    if not isinstance(tile, dict):
        return False  # LOCKED
    if "animal" not in tile:
        return True  # WEED, empty structure, or escaped-animal structure
    if tile.get("yield_units", 0) > 0:
        return True
    if not tile.get("fed_today"):
        return True
    if not tile.get("cared_today"):
        return True
    if tile.get("fertilizer_available"):
        return True
    return False


def make_agent(worker_animal_lists, milk_cap=4, wool_cap=3, ramp_per_day=2,
               cash_buffer=150, allow_land=False):
    """worker_animal_lists[i]: list of animal-type strings for worker i's
    fixed cluster (i=0 is the farmer, i>0 is hands[i-1]). Assignment is by
    fixed index every day -- never a shared/re-filtered list -- so there is
    no possibility of two units fighting over, or oscillating between,
    targets."""
    W = len(worker_animal_lists)
    total_slots = sum(len(lst) for lst in worker_animal_lists)
    all_positions = _all_positions(total_slots)

    worker_positions, worker_types = [], []
    cursor = 0
    for lst in worker_animal_lists:
        worker_positions.append(all_positions[cursor:cursor + len(lst)])
        worker_types.append(lst)
        cursor += len(lst)

    all_slot_types = []
    for lst, poss in zip(worker_types, worker_positions):
        all_slot_types.extend(zip(poss, lst))

    # Persistent per-episode ratchet: headcount only ever grows. Without
    # this, a temporary dip in owned-animal count (e.g. one escapes) would
    # shrink the hire target and de-staff an already-working cluster,
    # whose other animals then also go unfed and escape -- a cascade that
    # caused the worst outlier collapses in testing.
    _state = {"max_workers": 1}

    def pick_target(positions, tiles):
        for p in positions:
            t = tiles[p[1]][p[0]]
            if _needs_attention(t):
                return p, t
        return None, None

    def unit_action(pos, tile, inv, shed, target, animal):
        structure = ANIMAL_STRUCTURE[animal]

        if tile is None:
            step = _walk(pos, target)
            if step:
                return step
            return ["BUILD_PASTURE"] if structure == "PASTURE" else ["BUILD_COOP"]

        if not isinstance(tile, dict):
            return ["PASS"]

        if tile.get("kind") == "WEED":
            step = _walk(pos, target)
            return step if step else ["DIG"]

        if "animal" not in tile:
            if inv.get(animal, 0) > 0:
                step = _walk(pos, target)
                return step if step else ["PLACE", animal]
            if shed.get(animal, 0) > 0:
                step = _walk(pos, SHED)
                return step if step else ["PICKUP", animal, 1]
            return ["PASS"]

        if tile.get("yield_units", 0) > 0:
            step = _walk(pos, target)
            return step if step else ["HARVEST"]

        if not tile.get("fed_today"):
            if inv.get("WHEAT", 0) > 0:
                step = _walk(pos, target)
                return step if step else ["FEED"]
            if shed.get("WHEAT", 0) > 0:
                step = _walk(pos, SHED)
                return step if step else ["PICKUP", "WHEAT", 1]
            return ["PASS"]

        if not tile.get("cared_today"):
            step = _walk(pos, target)
            return step if step else ["CARE"]

        if tile.get("fertilizer_available"):
            step = _walk(pos, target)
            return step if step else ["COLLECT_FERTILIZER"]

        return ["PASS"]

    def agent(obs):
        player = obs["player"]
        farm = obs["farms"][player]
        tiles = farm["tiles"]
        shed = obs["private"]["shed"]
        money = farm["money"]
        hour = obs["hour"]
        invs = obs["private"]["inventories"]
        n_hands = len(farm["hands"])

        if obs["day"] == 0 and hour == 0:
            _state["max_workers"] = 1  # fresh episode -- reset the ratchet

        market_orders = []

        owned_by_type = {a: 0 for _, a in all_slot_types}
        for a in owned_by_type:
            owned_by_type[a] = shed.get(a, 0) + sum(iv.get(a, 0) for iv in invs)
        placed_count = sum(
            1 for p, a in all_slot_types
            if isinstance(tiles[p[1]][p[0]], dict) and tiles[p[1]][p[0]].get("animal") == a
        )
        owned_total = placed_count + sum(owned_by_type.values())
        avg_A = max(1, total_slots // W)
        target_workers = min(W, max(1, -(-(owned_total + ramp_per_day) // avg_A)))
        target_workers = max(target_workers, _state["max_workers"])
        _state["max_workers"] = target_workers
        n_hires_today = target_workers - 1

        hire_hours = max(1, -(-n_hires_today // MAX_ORDERS)) if n_hires_today > 0 else 1
        if hour < hire_hours and n_hands < n_hires_today:
            remaining_this_hour = min(MAX_ORDERS, n_hires_today - hour * MAX_ORDERS)
            still_needed = n_hires_today - n_hands
            n = max(0, min(remaining_this_hour, still_needed))
            market_orders.extend([["HIRE"]] * n)

        buy_hour = hire_hours
        if hour == buy_hour:
            unlocked = farm.get("unlocked_quadrants", ["NW"])
            available_capacity = 25 * len(unlocked)
            n_more = len(unlocked) - 1
            if allow_land and total_slots > available_capacity and n_more < len(LAND_ORDER):
                cost = LAND_PRICES[n_more]
                if money - cash_buffer >= cost:
                    market_orders.append(["BUY_LAND"])
                    money -= cost

            need = {}
            for p, a in all_slot_types:
                tile = tiles[p[1]][p[0]]
                placed = isinstance(tile, dict) and tile.get("animal") == a
                if not placed:
                    need[a] = need.get(a, 0) + 1

            remaining_ramp = ramp_per_day
            for a, n_need in need.items():
                to_buy = max(0, n_need - owned_by_type.get(a, 0))
                to_buy = min(to_buy, remaining_ramp)
                cost_each = ANIMAL_COST.get(a, 500)
                affordable = max(0, int((money - cash_buffer) // cost_each))
                to_buy = min(to_buy, affordable)
                if to_buy > 0:
                    market_orders.append(["BUY_ANIMAL", a, to_buy])
                    money -= to_buy * cost_each
                    remaining_ramp -= to_buy

            n_needing_feed = 0
            for p, a in all_slot_types:
                tile = tiles[p[1]][p[0]]
                if isinstance(tile, dict) and "animal" in tile and not tile.get("fed_today"):
                    n_needing_feed += 1
            wheat_have = shed.get("WHEAT", 0) + sum(iv.get("WHEAT", 0) for iv in invs)
            wheat_needed = max(0, n_needing_feed - wheat_have)
            if wheat_needed > 0 and money > cash_buffer:
                max_afford = max(0, int((money - cash_buffer) // 20))
                wheat_needed = min(wheat_needed, max(1, max_afford))
                market_orders.append(["BUY_PRODUCT", "WHEAT", wheat_needed])

        shed_total = sum(shed.values())
        aggressive = shed_total > 70
        caps = {"MILK": milk_cap, "WOOL": wool_cap, "EGG": None, "FERTILIZER": None}
        for item, cap in caps.items():
            qty = shed.get(item, 0)
            if qty <= 0:
                continue
            sell_n = qty if (cap is None or aggressive) else min(qty, cap)
            if sell_n > 0:
                market_orders.append(["SELL", item, sell_n])

        market_orders = market_orders[:MAX_ORDERS]

        fx, fy = farm["farmer"]
        inv0 = invs[0] if invs else {}
        target, ttile = pick_target(worker_positions[0], tiles)
        if target is None:
            farmer_action = ["PASS"]
        else:
            idx = worker_positions[0].index(target)
            farmer_action = unit_action((fx, fy), ttile, inv0, shed, target, worker_types[0][idx])

        hands_actions = []
        for j, (hx, hy) in enumerate(farm["hands"]):
            w_idx = j + 1
            if w_idx >= W:
                hands_actions.append(["PASS"])
                continue
            hinv = invs[j + 1] if j + 1 < len(invs) else {}
            target, ttile = pick_target(worker_positions[w_idx], tiles)
            if target is None:
                hands_actions.append(["PASS"])
                continue
            idx = worker_positions[w_idx].index(target)
            hands_actions.append(unit_action((hx, hy), ttile, hinv, shed, target, worker_types[w_idx][idx]))

        return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}

    return agent


# --- Final submission entry point -------------------------------------
# 9 workers x (COW, SHEEP, GOOSE) = 27 requested slots; 25 exist in the
# free NW quadrant, so 2 sit permanently idle (harmless -- just means one
# worker's 3rd slot never gets used). This was the best-scoring, most
# stable configuration found in testing (see module docstring).
_WORKER_MIX = [["COW", "SHEEP", "GOOSE"] for _ in range(9)]
# Keyed by player id, NOT a single shared instance: kaggle_environments can
# be handed the same function object for both players (e.g. in self-play
# testing via env.run([my_agent, my_agent])), and without per-player state
# the two players' hire-ratchets and day-boundary resets would contaminate
# each other. In a real match your opponent is separate code so this
# wouldn't occur, but it's free to be correct here too.
_agents = {}


def my_agent(obs):
    player = obs["player"]
    if player not in _agents:
        _agents[player] = make_agent(_WORKER_MIX)
    return _agents[player](obs)