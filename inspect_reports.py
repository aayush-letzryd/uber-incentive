import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
from pathlib import Path

rdir = Path(r'C:\Users\anura\.gemini\antigravity\scratch\letzryd-uber-incentives\uber_reports')

print("=" * 70)
print("LETZRYD - REPORT FILE INSPECTOR")
print("=" * 70)

for f in sorted(rdir.glob("20260831*")):
    try:
        if f.suffix == ".xlsx":
            df = pd.read_excel(f)
        elif f.suffix == ".csv":
            df = pd.read_csv(f)
        else:
            continue
        size_kb = f.stat().st_size // 1024
        print(f"\nFILE: {f.name}  ({size_kb:,} KB)")
        print(f"  Rows: {len(df):,}  |  Columns: {len(df.columns)}")
        print(f"  Columns: {list(df.columns[:8])}")
        if "City" in df.columns:
            print(f"  City breakdown: {dict(df['City'].value_counts())}")
        if "Number plate" in df.columns:
            print(f"  Sample plates: {df['Number plate'].head(5).tolist()}")
        if "Start date" in df.columns and "End date" in df.columns:
            print(f"  Date range: {df['Start date'].min()} -> {df['End date'].max()}")
    except Exception as e:
        print(f"  ERROR reading {f.name}: {e}")

print("\n" + "=" * 70)
print("INSPECTION COMPLETE")
print("=" * 70)
