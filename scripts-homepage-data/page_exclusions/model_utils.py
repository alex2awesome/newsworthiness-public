import pandas as pd
import numpy as np


bins = np.arange(0, 1.05, step=.05)
def transform_input_for_clustering(bb_df):
    normed_widths = (
        bb_df
        .pipe(lambda df: df['width'] / df['page_width'])
        .apply(lambda x: min(x, 1))
        .pipe(lambda s: pd.cut(s, bins=bins, right=False))
    )

    bin_counts = (
        normed_widths
        .apply(lambda x: x.left)
        .astype(float)
        .value_counts()
        .reindex(bins)
        .fillna(0)
        .astype(int)
    )
    return bin_counts

class ClusterAssignment():
    def __init__(self, kmeans, desired_cluster):
        self.desired_cluster = desired_cluster
        self.kmeans = kmeans

    def predict(self, X):
        bin_counts = transform_input_for_clustering(X)
        cluster = self.kmeans.predict(bin_counts.to_frame().T)[0]
        return cluster == self.desired_cluster
