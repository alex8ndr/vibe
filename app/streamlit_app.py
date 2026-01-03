import streamlit as st
import pandas as pd
import numpy as np
from scipy.spatial.distance import cdist
from datetime import datetime
import base64
import os

try:
    from streamlit_gsheets import GSheetsConnection
    GSHEETS_AVAILABLE = True
except ImportError:
    GSHEETS_AVAILABLE = False

st.set_page_config(
    page_title='Vibe',
    page_icon='🎵',
    layout='wide',
    initial_sidebar_state='expanded',
)

# Clean styling and preconnect hints for faster embed loading
st.markdown("""
<link rel="preconnect" href="https://open.spotify.com">
<link rel="preconnect" href="https://i.scdn.co">
<link rel="dns-prefetch" href="https://open.spotify.com">
<link rel="dns-prefetch" href="https://i.scdn.co">
<style>
    /* Sidebar logo sizing */
    .sidebar-logo {
        width: 100%;
        max-width: 220px;
        margin-bottom: 1.5rem;
    }
    
    /* Spotify embeds */
    .spotify-embed iframe {
        border-radius: 12px;
        margin: 0px;
    }
    
    /* Tighter sidebar spacing */
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem;
    }

    /* Remove sidebar header margin */
    [data-testid="stSidebarHeader"] {
        margin-bottom: 0px;
    }

    /* Main block container padding */
    [data-testid="stMainBlockContainer"] {
        padding-top: 3rem !important;
        padding-bottom: 3rem !important;
    }

    /* Responsive grid for Auto columns - max 3 */
    .auto-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
        gap: 1rem;
    }
    /* Cap at 3 columns max */
    @supports (grid-template-columns: repeat(auto-fill, minmax(min(350px, 100%), 1fr))) {
        .auto-grid {
            grid-template-columns: repeat(auto-fill, minmax(min(350px, 100%), 1fr));
        }
    }
    .auto-grid-card:nth-child(3n+4) {
        grid-column: auto;
    }
    .auto-grid-card {
        border: 1px solid rgba(49, 51, 63, 0.2);
        border-radius: 0.5rem;
        padding: 0.75rem;
    }
    .auto-grid-card h3 {
        margin: 0 0 0.5rem 0 !important;
        font-size: 1.25rem !important;
    }

    /* Hide anchor links on headings */
    a.st-emotion-cache-1aehpvj,
    .stMarkdown h3 a,
    [data-testid="stHeadingWithActionElements"] a {
        display: none !important;
        visibility: hidden !important;
    }

    /* Tighter container padding for results */
    [data-testid="stVerticalBlock"] > [data-testid="element-container"] [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.75rem !important;
    }

    /* Inline info banner */
    .inline-info {
        display: inline-block;
        background-color: rgba(28, 131, 225, 0.1);
        color: rgb(28, 131, 225);
        padding: 0.4rem 0.75rem;
        border-radius: 0.375rem;
        font-size: 0.875rem;
    }

    /* Vertically center header row content */
    .header-text {
        display: flex;
        align-items: center;
        height: 38px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Loading...")
def load_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base_dir, '..', 'data', 'data_encoded.parquet')
    if not os.path.exists(data_path):
        data_path = os.path.join(base_dir, 'data', 'data_encoded.parquet')
    
    df = pd.read_parquet(data_path)
    required = ['artist_name', 'track_name', 'track_id']
    if not all(col in df.columns for col in required):
        st.error("Invalid data file")
        st.stop()
    return df


@st.cache_data
def load_logo():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "Vibe Wide Cropped.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        pass
    return None


def save_input_artists(artists_songs):
    if not GSHEETS_AVAILABLE:
        return
    try:
        conn = st.connection("gsheets", type=GSheetsConnection, ttl=0)
        sheet = conn.read(worksheet="Data", usecols=list(range(21)), ttl=0)
        
        new_row = [datetime.now().strftime("%Y%m%d-%H%M%S")]
        for artist, songs in artists_songs.items():
            new_row += [artist] + songs + [None] * (3 - len(songs))
        new_row += [None] * (len(sheet.columns) - len(new_row))
        
        new_row_df = pd.DataFrame([new_row], columns=sheet.columns)
        sheet = sheet.dropna(how="all")
        sheet = pd.concat([sheet, new_row_df], ignore_index=True)
        conn.update(worksheet="Data", data=sheet)
    except Exception:
        pass


def get_combined_features(df, artists, track_ids):
    all_features = []
    
    if artists:
        artist_features = df[df["artist_name"].isin(artists)].iloc[:, 3:].values
        if artist_features.size > 0:
            all_features.append(artist_features)
    
    if track_ids:
        track_features = df[df["track_id"].isin(track_ids)].iloc[:, 3:].values
        if track_features.size > 0:
            all_features.append(track_features)
    
    if not all_features:
        return None
    
    combined = np.concatenate(all_features, axis=0)
    return np.mean(combined, axis=0).reshape(1, -1)


def generate_recommendations(df, input_artists, features, diversity, max_artists):
    n = 100 * diversity
    
    numeric_cols = df.select_dtypes(include=np.number)
    distances = cdist(features, numeric_cols.values, metric="euclidean")[0]
    similar_indices = distances.argsort()[:n]
    
    similar_songs = df.iloc[similar_indices].copy()
    similar_songs['score'] = np.arange(n, 0, -1)
    
    if diversity > 1:
        similar_songs['score'] = np.random.permutation(similar_songs['score'])
    
    # Exclude input artists
    pool = similar_songs[~similar_songs['artist_name'].isin(input_artists)]
    
    artist_scores = pool.groupby('artist_name')['score'].sum()
    artist_counts = pool.groupby('artist_name')['track_id'].count()
    
    # Require at least 2 songs in pool
    qualified = artist_scores[artist_counts >= 2].sort_values(ascending=False)
    
    recommendations = {}
    for artist in qualified.head(max_artists).index:
        top_songs = (
            pool[pool['artist_name'] == artist]
            .sort_values('score', ascending=False)
            .head(4)['track_id']
            .tolist()
        )
        recommendations[artist] = top_songs
    
    return recommendations


def spotify_embed(track_id):
    return f'''<div class="spotify-embed">
        <iframe src="https://open.spotify.com/embed/track/{track_id}"
            width="100%" height="80" frameborder="0"
            allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
            loading="eager"></iframe>
    </div>'''


def generate_html(input_artists, recommendations):
    """Generate standalone HTML file with recommendations."""
    html = '''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vibe Recommendations</title>
<style>
:root { --accent: #4A6FA5; --navy: #1E2A4A; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
       max-width: 1200px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: var(--navy); }
h1 { color: var(--navy); border-bottom: 3px solid var(--accent); padding-bottom: 10px; }
.input { background: #EEF2F7; padding: 15px; border-radius: 8px; 
         margin-bottom: 20px; border-left: 4px solid var(--accent); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
.card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 12px rgba(30,42,74,0.08); 
        border-top: 3px solid var(--accent); }
.card h2 { color: var(--navy); margin-top: 0; font-size: 1.2rem; }
iframe { border-radius: 12px; margin: 8px 0; }
</style>
</head><body>
<h1>Vibe Recommendations</h1>'''
    
    html += f'<div class="input"><strong>Based on:</strong> {" • ".join(input_artists)}</div>'
    html += '<div class="grid">'
    
    for artist, songs in recommendations.items():
        html += f'<div class="card"><h2>{artist}</h2>'
        for track_id in songs:
            html += f'<iframe src="https://open.spotify.com/embed/track/{track_id}" width="100%" height="80" frameborder="0"></iframe>'
        html += '</div>'
    
    html += '</div></body></html>'
    return html


def main():
    if 'recommendations' not in st.session_state:
        st.session_state.recommendations = {}
    if 'last_params' not in st.session_state:
        st.session_state.last_params = None

    df = load_data()
    # Sort artists by popularity (most popular first)
    artist_popularity = df.groupby('artist_name')['popularity'].sum().sort_values(ascending=False)
    artists_list = artist_popularity.index.tolist()

    # Sidebar
    with st.sidebar:
        logo = load_logo()
        if logo:
            st.markdown(f'<img src="data:image/png;base64,{logo}" class="sidebar-logo">', unsafe_allow_html=True)
        else:
            st.title("Vibe")
        
        # Settings at top, collapsed by default
        with st.expander("Settings", expanded=False):
            max_results = st.slider("Max artists", 1, 8, 4)
            diversity = st.slider("Diversity", 1, 5, 2, help="Higher = more variety")
            columns = st.pills("Columns", ["Auto", "1", "2", "3"], default="Auto")
        
        st.markdown("#### Select Artists")
        selected_artists = st.multiselect(
            "Search and select",
            artists_list,
            max_selections=5,
            placeholder="Type to search...",
            label_visibility="collapsed"
        )
        
        # Song selection for fine-tuning
        selected_tracks = []
        selection_dict = {}
        
        if selected_artists:
            st.markdown("#### Fine-tune")
            st.caption("Optional: pick specific songs")
            for artist in selected_artists:
                selection_dict[artist] = []
                tracks = sorted(df[df['artist_name'] == artist]['track_name'].unique())
                with st.expander(artist):
                    chosen = st.multiselect(
                        f"Songs by {artist}",
                        tracks,
                        key=f"tracks_{artist}",
                        max_selections=3,
                        label_visibility="collapsed"
                    )
                    if chosen:
                        selection_dict[artist] = chosen
                        ids = df[(df['artist_name'] == artist) & (df['track_name'].isin(chosen))]['track_id'].tolist()
                        selected_tracks.extend(ids)
        
        st.markdown("")  # Spacing
        search = st.button("Find Music", type="primary", use_container_width=True, disabled=not selected_artists)

    # Main content
    if not selected_artists:
        # Clear results when all artists are removed
        st.session_state.recommendations = {}
        st.session_state.last_params = None
        st.title("Vibe")
        st.markdown("**Discover new music based on artists you love.**")
        st.markdown("Select artists in the sidebar to get started.")
        return
    
    params = {
        'artists': tuple(sorted(selected_artists)),
        'tracks': tuple(sorted(selected_tracks)),
        'diversity': diversity,
        'max': max_results
    }
    
    if search and st.session_state.last_params != params:
        with st.spinner("Finding recommendations..."):
            features = get_combined_features(df, selected_artists, selected_tracks)
            if features is not None:
                recs = generate_recommendations(df, selected_artists, features, diversity, max_results)
                st.session_state.recommendations = recs
                st.session_state.last_params = params
                save_input_artists(selection_dict)
    
    recs = st.session_state.recommendations
    
    if not recs:
        if search:
            st.warning("No recommendations found. Try different artists.")
        else:
            st.info("Click **Find Music** to get recommendations.")
        return
    
    # Check if current params differ from last search
    params_changed = st.session_state.last_params != params
    
    # Results header with download
    col1, col2 = st.columns([3, 1])
    with col1:
        if params_changed:
            st.markdown('<div class="inline-info">Click <b>Find Music</b> to update results</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="header-text">{len(recs)} artists based on your selection</div>', unsafe_allow_html=True)
    with col2:
        input_artists = st.session_state.last_params['artists'] if st.session_state.last_params else selected_artists
        st.download_button(
            "Download",
            data=lambda: generate_html(input_artists, recs),
            file_name=f"vibe_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
            mime="text/html",
            use_container_width=True,
            key="download_results"
        )
    
    # Display results
    if columns == "Auto":
        # Use CSS Grid for responsive width-based columns (max 3)
        grid_items = ""
        for artist, songs in recs.items():
            embeds = "".join([spotify_embed(track_id) for track_id in songs])
            grid_items += f'<div class="auto-grid-card"><h3>{artist}</h3>{embeds}</div>'
        st.markdown(f'<div class="auto-grid">{grid_items}</div>', unsafe_allow_html=True)
    elif columns == "1":
        for artist, songs in recs.items():
            with st.container(border=True):
                st.markdown(f"### {artist}")
                for track_id in songs:
                    st.markdown(spotify_embed(track_id), unsafe_allow_html=True)
    else:
        num_cols = min(int(columns), 3)
        cols = st.columns(num_cols, gap="medium")
        for i, (artist, songs) in enumerate(recs.items()):
            with cols[i % num_cols]:
                with st.container(border=True):
                    st.markdown(f"### {artist}")
                    for track_id in songs:
                        st.markdown(spotify_embed(track_id), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
