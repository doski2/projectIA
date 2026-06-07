import os
import glob

log_dir = r"C:\Users\doski\projectIA\PCARS2-AI\logs\formula_rookie__sugo"

try:
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
except ImportError:
    print("tensorboard not installed in venv")
    exit(1)

# Collect all runs
runs = sorted(glob.glob(os.path.join(log_dir, "PPO_*")))
print(f"Runs encontrados: {len(runs)}")

all_data = {}
for run_path in runs:
    run_name = os.path.basename(run_path)
    ea = EventAccumulator(run_path)
    ea.Reload()
    tags = ea.Tags().get('scalars', [])
    for tag in tags:
        events = ea.Scalars(tag)
        if tag not in all_data:
            all_data[tag] = []
        all_data[tag].extend([(e.step, e.value, run_name) for e in events])

# Sort by step for each tag
for tag in all_data:
    all_data[tag].sort(key=lambda x: x[0])

# Print summary for key metrics
key_metrics = ['rollout/ep_rew_mean', 'rollout/ep_len_mean', 'train/value_loss', 
               'train/explained_variance', 'train/entropy_loss', 'train/std']

print(f"\nTotal tags disponibles: {sorted(all_data.keys())}\n")

for metric in key_metrics:
    if metric in all_data:
        data = all_data[metric]
        values = [v for _, v, _ in data]
        steps = [s for s, _, _ in data]
        print(f"\n--- {metric} ---")
        print(f"  Puntos de datos: {len(data)}")
        print(f"  Steps: {steps[0]:,} -> {steps[-1]:,}")
        print(f"  Valor: {values[0]:.3f} -> {values[-1]:.3f}")
        print(f"  Min: {min(values):.3f}  Max: {max(values):.3f}")
        # Last 5 values
        print(f"  Últimos 5: {[round(v,2) for v in values[-5:]]}")
