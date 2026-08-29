import json

# Compare both players side-by-side
with open(r"c:\Users\Admin\Desktop\Kaggriculture_Agent\replays\Version1\102458048.json") as f:
    data = json.load(f)

agents = [a['Name'] for a in data['info']['Agents']]
rewards = data['rewards']
steps = data['steps']

print("="*80)
print(f"HEAD-TO-HEAD COMPARISON: {agents[0]} (${rewards[0]:.0f}) vs {agents[1]} (${rewards[1]:.0f})")
print("="*80)

# Sample every 6 days
check_days = [0, 6, 12, 18, 24, 29]

for day in check_days:
    step_idx = min(day * 24, len(steps) - 1)
    if step_idx >= len(steps):
        break
        
    step = steps[step_idx]
    
    print(f"\n--- DAY {day} ---")
    for player_idx in [0, 1]:
        if player_idx >= len(step):
            continue
        
        obs = step[player_idx].get('observation', {})
        if not obs:
            continue
        
        farms = obs.get('farms', [])
        if player_idx >= len(farms):
            continue
        
        farm = farms[player_idx]
        private = obs.get('private', {})
        
        money = farm.get('money', 0)
        hands = len(farm.get('hands', []))
        unlocked = farm.get('unlocked_quadrants', [])
        
        # Count animals and their status
        animals_dict = {}
        tiles = farm.get('tiles', [])
        for row in tiles:
            for tile in row:
                if isinstance(tile, dict) and tile.get('kind') in ['COOP', 'PASTURE']:
                    animal = tile.get('animal')
                    if animal:
                        kind = animals_dict.get(animal, {'count': 0, 'fed': 0, 'yield': 0})
                        kind['count'] += 1
                        if tile.get('fed_today'):
                            kind['fed'] += 1
                        kind['yield'] += tile.get('yield_units', 0)
                        animals_dict[animal] = kind
        
        shed = private.get('shed', {})
        wheat = shed.get('WHEAT', 0)
        products = {}
        for prod in ['MILK', 'WOOL', 'EGGS']:
            products[prod] = shed.get(prod, 0)
        
        print(f"\n  {agents[player_idx]:20} (P{player_idx}):")
        print(f"    Money: ${money:>7.0f}")
        print(f"    Hands hired: {hands}")
        print(f"    Land unlocked: {unlocked}")
        print(f"    Animals: {animals_dict}")
        print(f"    Wheat in shed: {wheat}")
        print(f"    Products: {products}")

print("\n" + "="*80)
print("ANALYSIS:")
print("="*80)
print("""
If your agent (P1) is losing despite having similar hands and animals, it could be:
1. MARKET PRICE: Did opponent sell at peak prices while you sold in a glut?
2. ANIMAL MIX: Opponent might have better ratio of Cows vs Sheep
3. TIMING: Opponent got animals + hands running earlier in the game
4. EFFICIENCY: Your agent might be wasting actions on unnecessary moves
""")
