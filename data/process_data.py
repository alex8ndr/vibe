#!/usr/bin/env python3
"""
Process raw Spotify data into a cleaned, encoded parquet file.

Usage:
    python process_data.py                          # Use all defaults
    python process_data.py --max-songs 100          # Limit to 100 songs per artist
    python process_data.py -i raw.csv -o out.parquet --min-songs 5
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.preprocessing import MinMaxScaler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process and encode Spotify song data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=Path("data.csv.zip"),
        help="Path to input CSV file",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("data_encoded.parquet"),
        help="Path to output parquet file",
    )
    parser.add_argument(
        "--min-songs",
        type=int,
        default=2,
        help="Minimum songs an artist must have to be included",
    )
    parser.add_argument(
        "--max-songs",
        type=int,
        default=50,
        help="Maximum songs per artist (keeps most popular)",
    )
    parser.add_argument(
        "--keep-remixes",
        action="store_true",
        default=False,
        help="Keep remix tracks (by default they are removed)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print detailed processing info",
    )
    return parser.parse_args()


def log(msg: str, verbose: bool) -> None:
    if verbose:
        print(msg)


def process_data(
    input_path: Path,
    output_path: Path,
    min_songs: int,
    max_songs: int,
    keep_remixes: bool,
    verbose: bool,
) -> None:
    """Main processing pipeline."""
    
    # Load data
    log(f"Loading data from {input_path}...", verbose)
    df = pd.read_csv(input_path, low_memory=False)
    
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])
    
    n_initial = len(df)
    log(f"Loaded {n_initial:,} songs", verbose)
    log(f"Memory usage (before): {df.memory_usage(index=True).sum():,} bytes", verbose)

    # Remove remixes
    if not keep_remixes and "track_name" in df.columns:
        remix_mask = df["track_name"].astype(str).str.contains(" remix", case=False, na=False)
        remix_count = remix_mask.sum()
        df = df[~remix_mask].copy()
        log(f"Removed {remix_count:,} remixes, {len(df):,} songs remaining", verbose)

    # Scale numeric columns
    num_cols = [
        "year", "key", "popularity", "acousticness", "danceability", "duration_ms",
        "energy", "instrumentalness", "liveness", "loudness", "speechiness", "tempo",
        "valence", "time_signature"
    ]
    num_cols = [c for c in num_cols if c in df.columns]
    
    if num_cols:
        log(f"Scaling {len(num_cols)} numeric columns", verbose)
        scaler = MinMaxScaler()
        df[num_cols] = scaler.fit_transform(df[num_cols]).astype("float32")
    # Convert string columns to categorical
    for col in df.select_dtypes("object").columns:
        if col in ["artist_name", "album_name", "track_name"]:
            df[col] = df[col].astype("category")

    # Validate required columns
    if "artist_name" not in df.columns or "popularity" not in df.columns:
        print("Error: Required columns 'artist_name' and 'popularity' are missing.", file=sys.stderr)
        sys.exit(1)

    # Filter by minimum songs per artist
    artist_counts = df["artist_name"].value_counts()
    artists_with_enough = (artist_counts >= min_songs).sum()
    artists_without_enough = (artist_counts < min_songs).sum()
    
    log(f"Artists with >= {min_songs} songs: {artists_with_enough:,}", verbose)
    log(f"Artists with < {min_songs} songs: {artists_without_enough:,}", verbose)
    
    keep_artists = artist_counts[artist_counts >= min_songs].index
    df = df[df["artist_name"].isin(keep_artists)].copy()

    # Cap songs per artist (keep most popular)
    df = df.groupby("artist_name", group_keys=True, observed=True).apply(
        lambda x: x.nlargest(max_songs, "popularity"),
        include_groups=False
    ).reset_index(level=0)
    
    removed = n_initial - len(df)
    log(f"Capped to {max_songs} songs per artist", verbose)
    log(f"Removed {removed:,} songs total, {len(df):,} remaining", verbose)

    # Core Metadata
    meta_cols = ["artist_name", "track_name", "track_id"]
    
    # Audio Features (Scaled 0-1)
    feature_cols = [
        "popularity", "year", "duration_ms",
        "acousticness", "danceability", "energy", "instrumentalness",
        "liveness", "loudness", "speechiness", "tempo", "valence"
    ]
    
    # Process genre column if present
    genre_cols = []
    if "genre" in df.columns:
        log("One-hot encoding genres...", verbose)
        # Use int8 to ensure compatibility with numeric selection in app
        genre_dummies = pd.get_dummies(df["genre"], dtype="int8")
        df = pd.concat([df, genre_dummies], axis=1)
        genre_cols = list(genre_dummies.columns)

    final_cols = meta_cols + [c for c in feature_cols if c in df.columns] + genre_cols
    
    # Only keep columns that actually exist
    final_cols = [c for c in final_cols if c in df.columns]
    
    # Check for missing functional columns
    if not all(c in final_cols for c in meta_cols):
        print("Warning: Missing core columns (artist/track/id). App implementation relies on these being present.", file=sys.stderr)

    df = df[final_cols].copy()
    log(f"Pruned columns. Keeping {len(genre_cols)} genre columns.", verbose)

    # Downcast integers
    for col in df.select_dtypes("integer").columns:
        df[col] = pd.to_numeric(df[col], downcast="integer")
    
    # Use float16 for audio features
    float_cols = df.select_dtypes("floating").columns
    for c in float_cols:
        df[c] = df[c].astype("float16")
        
    log(f"Memory usage (after optimization): {df.memory_usage(index=True).sum():,} bytes", verbose)
    if verbose:
        print("\nFinal Data Types:")
        print(df.dtypes.value_counts())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use max compression (zstd level 22) and byte stream split for floats
    df.to_parquet(
        output_path,
        engine="pyarrow",
        compression="zstd",
        compression_level=22,
        index=False,
        use_byte_stream_split=True,
    )
    log(f"Saved to {output_path}", verbose)

    # Summary
    print(f"Processed {n_initial:,} -> {len(df):,} songs")
    print(f"Artists: {df['artist_name'].nunique():,}")
    print(f"Output: {output_path}")


def main() -> None:
    args = parse_args()
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    process_data(
        input_path=args.input,
        output_path=args.output,
        min_songs=args.min_songs,
        max_songs=args.max_songs,
        keep_remixes=args.keep_remixes,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()