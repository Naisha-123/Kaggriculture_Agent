import json
import os
from collections import defaultdict, Counter

replay_dir = r"c:\Users\Admin\Desktop\Kaggriculture_Agent\replays\Version1"

def analyze_replay(filepath):
    """Extract key insights from a single replay."""
    with open(filepath) as f:
        data = json.load(f)
    
    rewards = data['rewards']
    agents = [a['Name'] for a in data['info']['Agents']]
    winner_idx = 0 if rewards[0] > rewards[1] else 1
    winner_name = agents[winner_idx]
    winner_reward = rewards[winner_idx]
    loser_reward = rewards[1 - winner_idx]
    
    steps = data['steps']
    
    # Track actions by both players (index 0 and 1)
    player0_actions = defaultdict(int)
    player1_actions = defaultdict(int)
    
    player0_money_end = 0
    player1_money_end = 0
    
    player0_animals = 0
    player1_animals = 0
    
    # Analyze final state
    if len(steps) > 0:
        final_step = steps[-1]
        
        # Player 0 final money
        if len(final_step) > 0 and 'observation' in final_step[0]:
            obs0 = final_step[0]['observation']
            if obs0 and 'farms' in obs0 and len(obs0['farms']) > 0:
                player0_money_end = obs0['farms'][0]['money']
                # Count animals on player 0's farm
                tiles = obs0['farms'][0].get('tiles', [])
                for row in tiles:
                    for tile in row:
                        if isinstance(tile, dict) and tile.get('kind') in ['COOP', 'PASTURE']:
                            if 'animal' in tile and tile['animal']:
                                player0_animals += 1
        
        # Player 1 final money
        if len(final_step) > 1 and 'observation' in final_step[1]:
            obs1 = final_step[1]['observation']
            if obs1 and 'farms' in obs1 and len(obs1['farms']) > 1:
                player1_money_end = obs1['farms'][1]['money']
                # Count animals on player 1's farm
                tiles = obs1['farms'][1].get('tiles', [])
                for row in tiles:
                    for tile in row:
                        if isinstance(tile, dict) and tile.get('kind') in ['COOP', 'PASTURE']:
                            if 'animal' in tile and tile['animal']:
                                player1_animals += 1
    
    return {
        'file': os.path.basename(filepath),
        'player0': agents[0],
        'player1': agents[1],
        'player0_reward': rewards[0],
        'player1_reward': rewards[1],
        'player0_animals': player0_animals,
        'player1_animals': player1_animals,
        'winner': agents[winner_idx],
        'winner_reward': winner_reward,
        'loser_reward': loser_reward,
        'margin': winner_reward - loser_reward,
        'total_steps': len(steps),
    }

# Analyze all replays
print("=" * 80)
print("KAGGRICULTURE VERSION 1 SUBMISSION ANALYSIS")
print("=" * 80)

all_results = []
for fname in sorted(os.listdir(replay_dir)):
    if fname.endswith('.json'):
        fpath = os.path.join(replay_dir, fname)
        result = analyze_replay(fpath)
        all_results.append(result)

# Group by player
your_agent_games = [r for r in all_results if r['player0'] == 'your-username' or 'Kaggriculture' in r['player0']]
if not your_agent_games:
    # Try to find your agent by looking at patterns
    your_agent_games = all_results

print(f"\nTotal games analyzed: {len(all_results)}\n")

for result in all_results:
    print(f"📊 {result['file']}")
    print(f"  {result['player0']:20} (${result['player0_reward']:>8.0f})  vs  {result['player1']:20} (${result['player1_reward']:>8.0f})")
    print(f"  Winner: {result['winner']:20} [Margin: ${result['margin']:>8.0f}]")
    print(f"  Animals: P0={result['player0_animals']}, P1={result['player1_animals']}")
    print()

# Summary statistics
print("=" * 80)
print("SUMMARY STATISTICS")
print("=" * 80)

scores_0 = [r['player0_reward'] for r in all_results]
scores_1 = [r['player1_reward'] for r in all_results]

print(f"\nPlayer 0 (index 0):")
print(f"  Average: ${sum(scores_0)/len(scores_0):.0f}")
print(f"  Min: ${min(scores_0):.0f}")
print(f"  Max: ${max(scores_0):.0f}")
print(f"  Scores: {sorted([f'{s:.0f}' for s in scores_0])}")

print(f"\nPlayer 1 (index 1):")
print(f"  Average: ${sum(scores_1)/len(scores_1):.0f}")
print(f"  Min: ${min(scores_1):.0f}")
print(f"  Max: ${max(scores_1):.0f}")
print(f"  Scores: {sorted([f'{s:.0f}' for s in scores_1])}")

# Find which player is YOUR agent
p0_avg = sum(scores_0) / len(scores_0)
p1_avg = sum(scores_1) / len(scores_1)

print(f"\n⚠️  CRITICAL FINDING:")
print(f"  Player at index 0 averages: ${p0_avg:.0f}")
print(f"  Player at index 1 averages: ${p1_avg:.0f}")

if p0_avg < p1_avg:
    print(f"  ❌ Your agent (player 0) is LOSING badly!")
    print(f"     Your avg: ${p0_avg:.0f}")
    print(f"     Opponent avg: ${p1_avg:.0f}")
    print(f"     Deficit: ${p1_avg - p0_avg:.0f} per game")
else:
    print(f"  ✓ Your agent (player 0) is performing OK")

# Analyze animal strategy
p0_animals = [r['player0_animals'] for r in all_results]
p1_animals = [r['player1_animals'] for r in all_results]

print(f"\nAnimal Strategy Analysis:")
print(f"  Your animals (P0): avg={sum(p0_animals)/len(p0_animals):.1f}, min={min(p0_animals)}, max={max(p0_animals)}")
print(f"  Opponent animals (P1): avg={sum(p1_animals)/len(p1_animals):.1f}, min={min(p1_animals)}, max={max(p1_animals)}")

if sum(p0_animals) < sum(p1_animals):
    print(f"  ⚠️  Your agent is setting up FEWER animals!")
    print(f"     This reduces recurring daily revenue")
