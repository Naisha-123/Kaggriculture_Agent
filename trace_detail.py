import json

# Analyze game 7 in extreme detail - worst performance
with open(r"c:\Users\Admin\Desktop\Kaggriculture_Agent\replays\Version1\102458048.json") as f:
    data = json.load(f)

steps = data['steps']
player_idx = 1  # Your agent (AchyutKishore123)

print("="*80)
print("EXTREME DETAIL: Game 102458048 (You: $10,925 vs Opponent: $23,187)")
print("="*80)
print("\nTRACING YOUR AGENT (Player 1):\n")

for step_num in range(0, min(100, len(steps)), 4):  # Every 4 turns (every 6 hours)
    step = steps[step_num]
    if player_idx >= len(step):
        continue
    
    obs = step[player_idx].get('observation', {})
    act = step[player_idx].get('action', {})
    
    if not obs or not obs.get('farms'):
        continue
    
    farm = obs['farms'][player_idx]
    private = obs.get('private', {})
    day = obs.get('day', 0)
    hour = obs.get('hour', 0)
    
    money = farm.get('money', 0)
    hands_count = len(farm.get('hands', []))
    hires_today = farm.get('hires_today', 0)
    
    # Count animals
    animals = 0
    for row in farm.get('tiles', []):
        for tile in row:
            if isinstance(tile, dict) and tile.get('kind') in ['COOP', 'PASTURE']:
                if tile.get('animal'):
                    animals += 1
    
    # Parse market actions
    market_acts = []
    if 'market' in act:
        for m in act['market']:
            if m and len(m) > 0:
                market_acts.append(m[0])  # Just the action name
    
    print(f"Turn {step_num:3d} (Day {day}, Hour {hour:2d}): Money ${money:>7.0f} | Animals {animals} | Hands {hands_count} | Hires today: {hires_today}")
    if market_acts:
        print(f"                    Market actions: {market_acts}")
    if hands_count > 0:
        print(f"                    ✓ HANDS PRESENT!")

# Check final state
final_step = steps[-1]
if player_idx < len(final_step):
    obs = final_step[player_idx].get('observation', {})
    if obs and obs.get('farms'):
        farm = obs['farms'][player_idx]
        print(f"\nFINAL STATE:")
        print(f"  Final money: ${farm.get('money', 0):.0f}")
        print(f"  Final hands: {len(farm.get('hands', []))}")
        
        animals = 0
        for row in farm.get('tiles', []):
            for tile in row:
                if isinstance(tile, dict) and tile.get('kind') in ['COOP', 'PASTURE']:
                    if tile.get('animal'):
                        animals += 1
        print(f"  Final animals: {animals}")
        print(f"  REASON FOR LOW SCORE: No hands hired = No parallelization = slow operations")
