"""Load the FAF5.7.1 regional CSV, check it, and save a typed parquet copy for fast EDA."""
import sys

import pandas as pd

src, dst = sys.argv[1], sys.argv[2]
codes = ["fr_orig", "dms_orig", "dms_dest", "fr_dest", "fr_inmode", "dms_mode", "fr_outmode", "sctg2",
         "trade_type", "dist_band"]
df = pd.read_csv(src, dtype={c: "string" for c in codes})
for c in codes:
    df[c] = df[c].astype("category")
num = df.columns.difference(codes)
df[num] = df[num].astype("float32")
print("rows", len(df), "cols", df.shape[1])
print("nulls in numeric cols:", int(df[num].isna().sum().sum()))
print("negative values:", int((df[num] < 0).sum().sum()))
print("modes:", df["dms_mode"].value_counts().sort_index().to_dict())
print("trade types:", df["trade_type"].value_counts().sort_index().to_dict())
print("tons 2017-2024 (million):", (df[[f"tons_{y}" for y in range(2017, 2025)]].sum() / 1000).round(1).to_dict())
df.to_parquet(dst, index=False)
