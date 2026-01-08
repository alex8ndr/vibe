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
    page_icon='Vibe Icon.png',
    layout='wide',
    initial_sidebar_state='expanded',
)

# Clean styling and preconnect hints for faster embed loading
st.html("""
<link rel="preconnect" href="https://open.spotify.com">
<link rel="preconnect" href="https://i.scdn.co">
<script src="https://open.spotify.com/embed/iframe-api/v1" async></script>
<script>
    window.onSpotifyIframeApiReady = (IFrameAPI) => {
        window.SpotifyAPI = IFrameAPI;
        window.initPlayers();
    };

    // Preserve state across Streamlit re-runs
    window.artistControllers = window.artistControllers || {};
    window.artistCurrentTracks = window.artistCurrentTracks || {};

    window.initPlayers = function() {
        if (!window.SpotifyAPI) return;

        document.querySelectorAll('.artist-player').forEach((container, index) => {
            if (container.querySelector('iframe') || container.dataset.initializing) return;

            const artistId = container.dataset.artistId;
            const firstTrack = container.dataset.track;
            if (!artistId) return;

            const target = container.querySelector('.player-target');
            if (!target) return;

            container.dataset.initializing = "true";
            container.classList.remove('loaded');

            setTimeout(() => {
                window.SpotifyAPI.createController(target, {
                    width: '100%',
                    height: '80',
                    uri: firstTrack ? 'spotify:track:' + firstTrack : ''
                }, (controller) => {
                    window.artistControllers[artistId] = controller;
                    window.artistCurrentTracks[artistId] = firstTrack;
                    
                    const markLoaded = () => {
                        container.classList.add('loaded');
                        container.classList.remove('loading');
                        delete container.dataset.initializing;
                    };
                    
                    const iframe = container.querySelector('iframe');
                    if (iframe) {
                        iframe.setAttribute('scrolling', 'no');
                        iframe.setAttribute('tabindex', '-1');
                    }
                    
                    controller.addListener('playback_update', markLoaded);
                    controller.addListener('ready', markLoaded);
                    setTimeout(markLoaded, 2000);
                });
            }, index * 100);
        });
    };

    window.markPlayerLoaded = function(artistId) {
        const container = document.querySelector('.artist-player[data-artist-id="' + artistId + '"]');
        if (container) {
            container.classList.add('loaded');
            container.classList.remove('loading');
        }
    };

    setInterval(() => {
        if (window.SpotifyAPI) window.initPlayers();
    }, 1000);

    // Track which players need a full reset (to clear nag screen)
    window.artistNeedsReset = window.artistNeedsReset || {};

    if (!window.vibeClickHandler) {
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.track-btn');
            if (!btn) return;

            const trackId = btn.dataset.trackId;
            const artistId = btn.dataset.artistId;
            const controller = window.artistControllers[artistId];
            const container = document.querySelector('.artist-player[data-artist-id="' + artistId + '"]');

            if (controller && trackId) {
                // Handle previous artist: reset with skeleton overlay masking
                if (window.currentArtistId && window.currentArtistId !== artistId) {
                    const prevArtistId = window.currentArtistId;
                    const prev = window.artistControllers[prevArtistId];
                    const prevContainer = document.querySelector('.artist-player[data-artist-id="' + prevArtistId + '"]');
                    if (prev && prevContainer) {
                        prev.pause();
                        // Show skeleton overlay to mask the reset glitch
                        prevContainer.classList.add('resetting');
                        prevContainer.classList.remove('loaded');
                        
                        // Reset the player to clean state
                        const resetTrack = window.artistCurrentTracks[prevArtistId];
                        if (resetTrack) {
                            prev.loadUri('spotify:track:' + resetTrack);
                        }
                        
                        // Mark as loaded after reset completes
                        setTimeout(() => {
                            prevContainer.classList.remove('resetting');
                            prevContainer.classList.add('loaded');
                        }, 600);
                    }
                }

                const isSameTrack = (window.currentTrackId === trackId && window.currentArtistId === artistId);
                
                if (isSameTrack) {
                    controller.togglePlay();
                    btn.classList.toggle('playing');
                } else {
                    const isTrackAlreadyLoaded = window.artistCurrentTracks[artistId] === trackId;
                    
                    document.querySelectorAll('.track-btn.playing').forEach(el => el.classList.remove('playing'));
                    btn.classList.add('playing');
                    
                    window.currentArtistId = artistId;
                    window.currentTrackId = trackId;
                    
                    if (isTrackAlreadyLoaded) {
                        container.classList.remove('resetting');
                        controller.play();
                    } else {
                        if (container) {
                            container.classList.remove('resetting');
                            container.classList.add('loading');
                            container.classList.remove('loaded');
                        }
                        
                        controller.loadUri('spotify:track:' + trackId);
                        controller.play();
                        
                        window.artistCurrentTracks[artistId] = trackId;
                        
                        setTimeout(() => window.markPlayerLoaded(artistId), 800);
                    }
                }
            }
        });
        window.vibeClickHandler = true;
    }

    new MutationObserver(() => {
        window.initPlayers();
    }).observe(document.body, {childList: true, subtree: true});
</script>
""", unsafe_allow_javascript=True)

st.markdown("""
<link rel="canonical" href="https://vibe.alext.dev">

<style>
    /* Sidebar logo sizing */
    .sidebar-logo {
        width: 100%;
        max-width: 220px;
        margin-bottom: 1.5rem;
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
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
    }

    /* Responsive grid for Auto columns - max 3 */
    .auto-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(365px, 1fr));
        gap: 1rem;
    }
    .auto-grid-card {
        border: 1px solid rgba(49, 51, 63, 0.2);
        background: rgba(255,255,255,0.02);
        border-radius: 0.5rem;
        padding: 0.75rem;
    }
    .auto-grid-card h3 {
        margin: 0 0 0.25rem 0 !important;
        font-size: 1.5rem !important;
    }

    /* Hide anchor links on headings */
    [data-testid="stHeadingWithActionElements"] a {
        display: none !important;
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
    
    /* Inline info with spinner */
    .inline-info.with-spinner {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
    }
    .inline-info.with-spinner::before {
        content: '';
        width: 14px;
        height: 14px;
        border: 2px solid rgba(28, 131, 225, 0.3);
        border-top-color: rgb(28, 131, 225);
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
        flex-shrink: 0;
    }

    /* Header text */
    .header-text {
        display: flex;
        align-items: center;
        height: 38px;
        font-weight: 600;
    }
    
    /* Fixed loading indicator - matches inline-info style */
    .fixed-loading {
        position: fixed;
        top: 10px;
        left: 120px;
        z-index: 999999;
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background-color: rgba(28, 131, 225, 0.1);
        color: rgb(28, 131, 225);
        padding: 0.5rem 1rem;
        border-radius: 0.375rem;
        font-size: 0.875rem;
        font-weight: 500;
        backdrop-filter: blur(80px);
    }
    .fixed-loading::before {
        content: '';
        width: 14px;
        height: 14px;
        border: 2px solid rgba(28, 131, 225, 0.3);
        border-top-color: rgb(28, 131, 225);
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
    }
    @keyframes spin {
        to { transform: rotate(360deg); }
    }

    /* Skeleton loader animation */
    @keyframes shimmer {
        0% { background-position: -200% 0; }
        100% { background-position: 200% 0; }
    }

    /* Artist Stats/Player Container */
    .artist-player {
        margin-bottom: 0.5rem;
        border-radius: 12px;
        overflow: hidden;
        background: #121212;
        min-height: 80px;
        height: 80px;
        isolation: isolate;
        position: relative;
    }
    
    /* Skeleton loader - shown by default */
    .artist-player::before {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: 12px;
        background: linear-gradient(
            90deg,
            #181818 0%,
            #2e2e2e 40%,
            #4a4a4a 50%,
            #2e2e2e 60%,
            #181818 100%
        );
        background-size: 200% 100%;
        animation: shimmer 1.8s ease-in-out infinite;
        z-index: 1;
        opacity: 1;
        transition: opacity 0.3s ease-out;
        pointer-events: none;
    }
    
    /* Hide skeleton when loaded */
    .artist-player.loaded::before {
        opacity: 0;
    }
    
    /* Iframe styling */
    .artist-player iframe {
        border-radius: 12px;
        display: block;
        border: none;
        background: #121212;
        opacity: 0;
        transition: opacity 0.3s ease-out;
        scrollbar-width: none; /* Firefox */
        width: 100% !important;
        height: 80px !important;
        min-height: 80px !important;
        max-height: 80px !important;
    }
    .artist-player iframe::-webkit-scrollbar {
        display: none; /* Chrome/Safari */
    }
    
    .artist-player.loaded iframe {
        opacity: 1;
    }
    
    /* Loading state during track change */
    .artist-player.loading::before {
        opacity: 1;
    }
    .artist-player.loading iframe {
        opacity: 0.3;
    }
    
    /* Resetting state - semi-transparent skeleton to mask glitches during background reset */
    .artist-player.resetting::before {
        opacity: 0.8;
    }
    .artist-player.resetting iframe {
        opacity: 0.3;
    }

    /* Compact Track buttons */
    .track-btn {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        width: 100%;
        padding: 0.5rem 0.75rem; 
        margin: 0.25rem 0;
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 8px;
        background: var(--btn-bg, linear-gradient(145deg, #1e1e24 0%, #16161d 100%));
        color: #e0e0e0;
        font-size: 0.85rem;
        font-weight: 500;
        cursor: pointer;
        transition: transform 0.2s ease, background 0.2s ease;
        text-align: left;
        position: relative;
        overflow: hidden;
    }
    .track-btn::after {
        content: '';
        position: absolute;
        top: 0; left: 0; width: 3px; height: 100%;
        background: var(--accent-color, transparent);
        opacity: 0.8;
    }
    .track-btn:hover {
        background: var(--btn-hover, linear-gradient(145deg, #25252d 0%, #1c1c24 100%));
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        color: #fff;
    }
    .track-btn.playing {
        background: linear-gradient(135deg, #1db954 0%, #169c46 100%);
        color: white;
        box-shadow: 0 4px 15px rgba(29, 185, 84, 0.3);
    }
    .track-btn::before {
        content: '♫';
        font-size: 1rem;
        opacity: 0.5;
        min-width: 24px;
        width: 24px;
        height: 24px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }
    .track-btn:hover::before {
        content: '▶';
        font-size: 1.1rem;
        color: var(--accent-color, #1db954);
        opacity: 1;
        transform: translateY(1px);
    }
    .track-btn.playing::before {
        content: '❚❚';
        color: white;
        opacity: 1;
        font-size: 0.8rem;
        letter-spacing: -1px;
        transform: translateY(1px);
    }
    
    /* Hero/Landing Page Styling */
    .hero-bg {
        position: fixed;
        bottom: 0;
        right: 0;
        width: 1000px;
        height: 100vh;
        background-size: cover;
        background-position: right bottom;
        mask-image: linear-gradient(to right, transparent 0%, black 50%);
        -webkit-mask-image: linear-gradient(to right, transparent 0%, black 50%);
        z-index: 0;
        pointer-events: none;
    }
    
    .landing-content {
        position: relative;
        z-index: 1;
        max-width: 500px;
        padding-top: 15vh;
        pointer-events: none;
    }
    .landing-text-inner {
        position: relative;
        width: fit-content;
        pointer-events: auto;
    }
    .landing-text-inner::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 0%;
        transform: translate(-50%, -50%);
        width: 800px;
        height: 800px;
        z-index: -1;
        border-radius: 50%;
        filter: blur(40px);
        -webkit-filter: blur(40px);
        background: radial-gradient(circle at center, #0e1117 0%, #0e1117 80%, transparent 100%);
        
    }
    .st-theme-light .landing-text-inner::before {
        background: radial-gradient(circle at center, #ffffff 0%, #ffffff 80%, transparent 100%);
    }
    .landing-title {
        font-size: 4.5rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -2px;
        line-height: 1;
        color: #fff;
    }
    .st-theme-light .landing-title { color: #111; }
    .landing-subtitle {
        font-size: 1.35rem;
        margin-top: 1.5rem;
        margin-bottom: 2.5rem;
        font-weight: 400;
        line-height: 1.5;
        color: #999;
    }
    .st-theme-light .landing-subtitle { color: #555; }
    .arrow-hint {
        font-size: 1rem;
        font-weight: 500;
        color: #666;
    }
    .st-theme-light .arrow-hint { color: #888; }
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
def get_artists_list(_df):
    """Get artists sorted by popularity (cached)."""
    artist_popularity = _df.groupby('artist_name')['popularity'].sum().sort_values(ascending=False)
    return artist_popularity.index.tolist()


@st.cache_data
def load_logo():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "Vibe Banner.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        pass
    return None


@st.cache_data
def load_hero_image(theme="dark"):
    """Load hero image for the specified theme (dark/light) with fallback."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Try themed version first
    themed_path = os.path.join(base_dir, f"hero_image_{theme}.png")
    if os.path.exists(themed_path):
        try:
            with open(themed_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            pass
    
    # Fallback to generic hero_image.png
    fallback_path = os.path.join(base_dir, "hero_image.png")
    if os.path.exists(fallback_path):
        try:
            with open(fallback_path, "rb") as f:
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
        artist_tracks = pool[pool['artist_name'] == artist].sort_values('score', ascending=False).head(4)
        # Store both track_id and track_name
        tracks = [(row['track_id'], row['track_name']) for _, row in artist_tracks.iterrows()]
        recommendations[artist] = tracks
    
    return recommendations


def get_artist_colors(artist_name):
    """Generate consistent colors based on artist name hash."""
    import hashlib
    hash_val = int(hashlib.md5(artist_name.encode()).hexdigest(), 16)
    
    # HSL generation for pleasing colors
    hue = hash_val % 360
    hue2 = (hue + 40) % 360
    
    # Generate gradient and accent color
    # Darker gradient for background, brighter for accent
    bg_gradient = f"linear-gradient(135deg, hsl({hue}, 60%, 15%) 0%, hsl({hue2}, 50%, 10%) 100%)"
    hover_gradient = f"linear-gradient(135deg, hsl({hue}, 70%, 20%) 0%, hsl({hue2}, 60%, 15%) 100%)"
    accent_color = f"hsl({hue}, 80%, 60%)"
    
    return bg_gradient, hover_gradient, accent_color

def get_artist_id(artist_name):
    import hashlib
    return hashlib.md5(artist_name.encode()).hexdigest()

def track_button(track_id, track_name, artist_name):
    # Truncate long track names
    display_name = track_name[:35] + '...' if len(track_name) > 35 else track_name
    
    # Get dynamic colors
    bg, hover, accent = get_artist_colors(artist_name)
    artist_id = get_artist_id(artist_name)
    
    # Inject CSS variables into style attribute
    style = f"--btn-bg: {bg}; --btn-hover: {hover}; --accent-color: {accent};"
    
    return f'<button class="track-btn" data-track-id="{track_id}" data-artist-id="{artist_id}" style="{style}">{display_name}</button>'


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
    
    for artist, tracks in recommendations.items():
        html += f'<div class="card"><h2>{artist}</h2>'
        for track_id, track_name in tracks:
            html += f'<iframe src="https://open.spotify.com/embed/track/{track_id}" width="100%" height="80" frameborder="0"></iframe>'
        html += '</div>'
    
    html += '</div></body></html>'
    return html


def main():
    if 'recommendations' not in st.session_state:
        st.session_state.recommendations = {}
    if 'last_params' not in st.session_state:
        st.session_state.last_params = None
    
    # Load settings from query params (lightweight persistence)
    if 'settings_loaded' not in st.session_state:
        st.session_state.settings_loaded = True
        params = st.query_params
        if 'max' in params:
            try:
                st.session_state.setting_max_results = int(params['max'])
            except:
                pass
        if 'div' in params:
            try:
                st.session_state.setting_diversity = int(params['div'])
            except:
                pass
        if 'cols' in params:
            st.session_state.setting_columns = params['cols']

    with st.sidebar:
        if os.path.exists("alext_dev_logo.svg"):
            st.logo("alext_dev_logo.svg", size="large", link="https://alext.dev", icon_image="Vibe Banner.png")
            
        logo = load_logo()
        if logo:
            st.markdown(f'<img src="data:image/png;base64,{logo}" class="sidebar-logo">', unsafe_allow_html=True)
        else:
            st.title("Vibe")

    # Get current state
    current_selection = st.session_state.get("selected_artists", [])
    recs = st.session_state.get('recommendations', {})
    
    # Show hero page if no recommendations yet
    if not recs:
        theme = "dark"
        try:
            theme = st.context.theme.type
        except:
            pass
        
        hero_b64 = load_hero_image(theme)
        theme_class = f"st-theme-{theme}"
        
        if current_selection:
            hint_html = '<div class="inline-info">Click <b>Find Music</b> for recommendations</div>'
        else:
            hint_html = '<div class="arrow-hint"><span>←</span> Select artists to start</div>'
        
        st.markdown(f"""
        <div class="hero-bg" style="background-image: url('data:image/png;base64,{hero_b64}');"></div>
        
        <div class="landing-content {theme_class}">
            <div class="landing-text-inner">
                <h1 class="landing-title">Vibe</h1>
                <p class="landing-subtitle">
                    Discover new music based on<br>
                    the artists you already love.
                </p>
                {hint_html}
            </div>
        </div>
        """, unsafe_allow_html=True)

    df = load_data()
    artists_list = get_artists_list(df)

    with st.sidebar:
        
        # Settings at top, collapsed by default
        with st.expander("Settings", expanded=False):
            default_max_results = st.session_state.get('setting_max_results', 6)
            default_diversity = st.session_state.get('setting_diversity', 2)
            default_columns = st.session_state.get('setting_columns', "Auto")
            
            max_results = st.slider("Max recommended artists", 3, 9, default_max_results, key="slider_max_results")
            diversity = st.slider("Diversity", 1, 5, default_diversity, help="Higher = more variety", key="slider_diversity")
            columns = st.pills("Columns", ["Auto", "1", "2", "3"], default=default_columns, key="pills_columns")
            
            # Track if settings changed for later persistence
            if max_results != st.session_state.get('setting_max_results'):
                st.session_state.setting_max_results = max_results
                st.session_state.settings_changed = True
            if diversity != st.session_state.get('setting_diversity'):
                st.session_state.setting_diversity = diversity
                st.session_state.settings_changed = True
            if columns != st.session_state.get('setting_columns'):
                st.session_state.setting_columns = columns
                st.session_state.settings_changed = True
        
        # Placeholder for the search button so it visually appears at the top
        search_placeholder = st.empty()
        search_placeholder.button("Find Music", type="primary", use_container_width=True, disabled=True, key="find_music_placeholder")

        st.markdown("#### Select Artists")
        st.caption("Select up to 5 artists")
        selected_artists = st.multiselect(
            "Search and select",
            artists_list,
            max_selections=5,
            placeholder="Type to search...",
            label_visibility="collapsed",
            key="selected_artists"
        )
        
        # Render button in the placeholder (now we have the selected_artists state)
        search = search_placeholder.button("Find Music", type="primary", use_container_width=True, disabled=not selected_artists)
        
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


    # Main content
    recs = st.session_state.recommendations
    
    # Persist settings to query params when changed (lightweight, no overhead)
    if st.session_state.get('settings_changed'):
        st.query_params['max'] = str(st.session_state.get('setting_max_results', 6))
        st.query_params['div'] = str(st.session_state.get('setting_diversity', 2))
        st.query_params['cols'] = st.session_state.get('setting_columns', 'Auto')
        st.session_state.settings_changed = False
    
    # Build params and generate recommendations if artists selected
    params = None
    params_changed = False
    
    if current_selection:
        params = {
            'artists': tuple(sorted(selected_artists)),
            'tracks': tuple(sorted(selected_tracks)),
            'diversity': diversity,
            'max': max_results
        }
        params_changed = st.session_state.last_params != params
        
        # Generate new recommendations if search clicked
        if search:
            # Boost diversity for repeat searches with same params
            effective_diversity = diversity
            if not params_changed:
                effective_diversity = min(diversity + 2, 5)
            
            st.session_state.pending_generation = {
                'artists': selected_artists,
                'tracks': selected_tracks,
                'diversity': effective_diversity,
                'max_results': max_results,
                'selection_dict': selection_dict
            }
            st.session_state.is_generating = True
            st.rerun()
    
    pending = st.session_state.get('pending_generation')
    is_generating = st.session_state.get('is_generating', False)
    
    # First search with no existing recs - show loading and execute
    if is_generating and not recs:
        st.markdown('<div class="fixed-loading">Generating</div>', unsafe_allow_html=True)
        if pending:
            features = get_combined_features(df, pending['artists'], pending['tracks'])
            if features is not None:
                new_recs = generate_recommendations(df, pending['artists'], features, pending['diversity'], pending['max_results'])
                st.session_state.recommendations = new_recs
                st.session_state.last_params = {
                    'artists': tuple(sorted(pending['artists'])),
                    'tracks': tuple(sorted(pending['tracks'])),
                    'diversity': pending['diversity'],
                    'max': pending['max_results']
                }
                save_input_artists(pending['selection_dict'])
            st.session_state.pending_generation = None
            st.session_state.is_generating = False
            st.rerun()
    
    if not recs:
        return
    
    # Results header
    col1, col2 = st.columns([3, 1])
    with col1:
        if is_generating:
            st.markdown('<div class="inline-info with-spinner">Generating recommendations</div>', unsafe_allow_html=True)
        elif current_selection and params_changed:
            st.markdown('<div class="inline-info">Click <b>Find Music</b> to update results</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="header-text">Click on a track to play</div>', unsafe_allow_html=True)
    with col2:
        if recs:
            input_artists = st.session_state.last_params['artists'] if st.session_state.last_params else selected_artists
            st.download_button(
                "Download",
                data=lambda: generate_html(input_artists, recs),
                file_name=f"vibe_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                mime="text/html",
                use_container_width=True,
                key="download_results"
            )
    
    # Display results with track buttons and artist players
    if columns == "Auto":
        grid_items = ""
        for artist, tracks in recs.items():
            aid = get_artist_id(artist)
            first_track = tracks[0][0] if tracks else ""
            player_div = f'<div class="artist-player" data-artist-id="{aid}" data-track="{first_track}"><div class="player-target"></div></div>'
            buttons = "".join([track_button(tid, tname, artist) for tid, tname in tracks])
            grid_items += f'<div class="auto-grid-card"><h3>{artist}</h3>{player_div}{buttons}</div>'
        st.markdown(f'<div class="auto-grid">{grid_items}</div>', unsafe_allow_html=True)
    elif columns == "1":
        for artist, tracks in recs.items():
            with st.container(border=True):
                st.markdown(f"### {artist}")
                aid = get_artist_id(artist)
                first_track = tracks[0][0] if tracks else ""
                st.markdown(f'<div class="artist-player" data-artist-id="{aid}" data-track="{first_track}"><div class="player-target"></div></div>', unsafe_allow_html=True)
                buttons = "".join([track_button(tid, tname, artist) for tid, tname in tracks])
                st.markdown(buttons, unsafe_allow_html=True)
    else:
        num_cols = min(int(columns), 3)
        cols = st.columns(num_cols, gap="medium")
        for i, (artist, tracks) in enumerate(recs.items()):
            with cols[i % num_cols]:
                with st.container(border=True):
                    st.markdown(f"### {artist}")
                    aid = get_artist_id(artist)
                    first_track = tracks[0][0] if tracks else ""
                    st.markdown(f'<div class="artist-player" data-artist-id="{aid}" data-track="{first_track}"><div class="player-target"></div></div>', unsafe_allow_html=True)
                    buttons = "".join([track_button(tid, tname, artist) for tid, tname in tracks])
                    st.markdown(buttons, unsafe_allow_html=True)
    
    # Execute pending generation after page is rendered
    if pending and is_generating:
        features = get_combined_features(df, pending['artists'], pending['tracks'])
        if features is not None:
            new_recs = generate_recommendations(df, pending['artists'], features, pending['diversity'], pending['max_results'])
            st.session_state.recommendations = new_recs
            st.session_state.last_params = {
                'artists': tuple(sorted(pending['artists'])),
                'tracks': tuple(sorted(pending['tracks'])),
                'diversity': pending['diversity'],
                'max': pending['max_results']
            }
            save_input_artists(pending['selection_dict'])
        st.session_state.pending_generation = None
        st.session_state.is_generating = False
        st.rerun()


if __name__ == "__main__":
    main()
