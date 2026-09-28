import sys
sys.path.insert(0, r'C:\Users\Dell\SIH26\backend')

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

df = pd.read_csv(r'C:\Users\Dell\SIH26\data\raw\MPLADS_Sentinel_FINAL-1.csv', dtype=str, encoding='utf-8-sig')
df = df.reset_index(drop=True)

# Map new column names to expected names
df = df.rename(columns={'work': 'Work Description'})

# Filter out empty descriptions
valid_mask = df['Work Description'].fillna('').str.strip() != ''
valid_df = df[valid_mask]

print(f"Total records: {len(df)}")
print(f"Valid descriptions: {len(valid_df)}")

# TF-IDF vectorization
descriptions = valid_df['Work Description'].fillna('').values

vectorizer = TfidfVectorizer(
    max_features=1000,
    stop_words='english',
    ngram_range=(1, 2),
    min_df=1
)
tfidf_matrix = vectorizer.fit_transform(descriptions)

# Compute cosine similarity
sim = cosine_similarity(tfidf_matrix)

# Count similarity distribution
above_90 = (sim > 0.90).sum() // 2
above_93 = (sim > 0.93).sum() // 2
above_95 = (sim > 0.95).sum() // 2
above_97 = (sim > 0.97).sum() // 2
above_99 = (sim > 0.99).sum() // 2

print(f"\nSimilarity distribution:")
print(f"  > 0.90: {above_90} pairs")
print(f"  > 0.93: {above_93} pairs")
print(f"  > 0.95: {above_95} pairs")
print(f"  > 0.97: {above_97} pairs")
print(f"  > 0.99: {above_99} pairs")

# Show some high similarity pairs
print("\nSample high similarity pairs:")
count = 0
for i in range(sim.shape[0]):
    for j in range(i+1, sim.shape[1]):
        if sim[i, j] > 0.95:
            desc_i = valid_df.iloc[i]['Work Description']
            desc_j = valid_df.iloc[j]['Work Description']
            print(f"  {sim[i,j]:.3f}: {desc_i[:50]}... | {desc_j[:50]}...")
            count += 1
            if count >= 10:
                break
    if count >= 10:
        break
