import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import sparse
from tqdm import tqdm
import os

data_dir = Path('/workspace/Kaggle/AI4Code')
# data_dir = Path('..//input/')
if not os.path.exists(data_dir / "data"):
    os.mkdir(data_dir / "data")


def read_notebook(path):
    return (
        pd.read_json(
            path,
            dtype={'cell_type': 'category', 'source': 'str'})
        .assign(id=path.stem)
        .rename_axis('cell_id')
    )


paths_train = list((data_dir / 'train').glob('*.json'))
notebooks_train = [
    read_notebook(path) for path in tqdm(paths_train, desc='Train NBs')
]
df = (
    pd.concat(notebooks_train)
    .set_index('id', append=True)
    .swaplevel()
    .sort_index(level='id', sort_remaining=False)
)

df_orders = pd.read_csv(
    data_dir / 'train_orders.csv',
    index_col='id',
    squeeze=True,
).str.split()  # Split the string representation of cell_ids into a list


def get_ranks(base, derived):
    return [base.index(d) for d in derived]


df_orders_ = df_orders.to_frame().join(
    df.reset_index('cell_id').groupby('id')['cell_id'].apply(list),
    how='right',
)

ranks = {}
for id_, cell_order, cell_id in df_orders_.itertuples():
    ranks[id_] = {'cell_id': cell_id, 'rank': get_ranks(cell_order, cell_id)}
df_ranks = (
    pd.DataFrame
    .from_dict(ranks, orient='index')
    .rename_axis('id')
    .apply(pd.Series.explode)
    .set_index('cell_id', append=True)
)

df_ancestors = pd.read_csv(data_dir / 'train_ancestors.csv', index_col='id')
df = df.reset_index().merge(
    df_ranks, on=["id", "cell_id"]).merge(df_ancestors, on=["id"])
df["pct_rank"] = df["rank"] / df.groupby("id")["cell_id"].transform("count")

# Load external dataset
df_external = pd.read_csv(data_dir / 'ai4code-custom-data/data.csv')
print("ai4code-custom-data:", df_external.shape)
df_external = df_external.rename(columns={'notebook_id': 'id'})
df_external["id"] = df_external["id"].astype(str)
df_external["cell_id"] = df_external["id"].astype(
    str) + "_" + df_external["rank"].astype(str)
df_external["ancestor_id"] = df_external["id"].astype(str)
df_external["parent_id"] = np.nan
df_external = df_external[[
    'id', 'cell_id', 'cell_type', 'source', 'rank', 'ancestor_id', 'parent_id',
    'pct_rank'
]]

from sklearn.model_selection import GroupShuffleSplit

NVALID = 0.1  # size of validation set
splitter = GroupShuffleSplit(n_splits=1, test_size=NVALID, random_state=0)
train_ind, val_ind = next(splitter.split(df, groups=df["ancestor_id"]))
train_df = df.loc[train_ind].reset_index(drop=True)
val_df = df.loc[val_ind].reset_index(drop=True)

# Merge with training set
train_df = pd.concat((train_df, df_external), axis=0).reset_index(drop=True)
print("Merged training dataset:", train_df.shape)
print("Valid dataset:", val_df.shape)

# Base markdown dataframes
train_df_mark = train_df[train_df["cell_type"]
                         == "markdown"].reset_index(drop=True)
val_df_mark = val_df[val_df["cell_type"] == "markdown"].reset_index(drop=True)
train_df_mark.to_csv(data_dir / "data/train_mark_ext.csv", index=False)
val_df_mark.to_csv(data_dir / "data/val_mark.csv", index=False)
val_df.to_csv(data_dir / "data/val.csv", index=False)
train_df.to_csv(data_dir / "data/train_ext.csv", index=False)
# train_df_mark.to_csv(data_dir / "data/train_mark.csv", index=False)
# val_df_mark.to_csv(data_dir / "data/val_mark.csv", index=False)
# val_df.to_csv(data_dir / "data/val.csv", index=False)
# train_df.to_csv(data_dir / "data/train.csv", index=False)


# Additional code cells
def clean_code(cell):
    return str(cell).replace("\\n", "\n")


def sample_cells(cells, n):
    cells = [clean_code(cell) for cell in cells]
    if n >= len(cells):
        return [" ".join(cell.split()[:50]) for cell in cells]
        # return [cell[:200] for cell in cells]
    else:
        results = []
        step = len(cells) / n
        idx = 0
        while int(np.round(idx)) < len(cells):
            results.append(cells[int(np.round(idx))])
            idx += step
        assert cells[0] in results
        if cells[-1] not in results:
            results[-1] = cells[-1]
        return results


def get_features(df):
    features = dict()
    df = df.sort_values("rank").reset_index(drop=True)
    for idx, sub_df in tqdm(df.groupby("id")):
        features[idx] = dict()
        total_md = sub_df[sub_df.cell_type == "markdown"].shape[0]
        code_sub_df = sub_df[sub_df.cell_type == "code"]
        total_code = code_sub_df.shape[0]
        codes = sample_cells(code_sub_df.source.values, 20)
        features[idx]["total_code"] = total_code
        features[idx]["total_md"] = total_md
        features[idx]["codes"] = codes
    return features

val_fts = get_features(val_df)
json.dump(val_fts, open(data_dir / "data/val_fts.json", "wt"))
train_fts = get_features(train_df)
json.dump(train_fts, open(data_dir / "data/train_fts_ext.json", "wt"))
# val_fts = get_features(val_df)
# json.dump(val_fts, open(data_dir / "data/val_fts.json", "wt"))
# train_fts = get_features(train_df)
# json.dump(train_fts, open(data_dir / "data/train_fts.json", "wt"))
