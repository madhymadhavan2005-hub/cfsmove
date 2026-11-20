import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="CFS Liner Movement Analytics", layout="wide")

# Custom Dark & Amber-Gold Styling
st.markdown("""
<style>
    .stApp { background-color: #0f1115; color: #f3f4f6; }
    .winner-card {
        background: linear-gradient(135deg, #1b1f27 0%, #262014 100%);
        border: 1px solid #f59e0b;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
    }
    .winner-title { color: #f59e0b; font-size: 14px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; }
    .winner-brand { color: #ffffff; font-size: 32px; font-weight: 800; margin: 4px 0; }
    .winner-sub { color: #d1d5db; font-size: 15px; }
</style>
""", unsafe_allow_html=True)

# ISO-6346 BIC Prefix -> Shipping Line Lookup
BIC_PREFIX_MAP = {
    "MSKU": "Maersk", "MRKU": "Maersk", "SEGU": "Maersk",
    "MSCU": "MSC", "MEDU": "MSC", "TRLU": "MSC",
    "CMAU": "CMA CGM", "CGMU": "CMA CGM", "APZU": "CMA CGM",
    "HLCU": "Hapag-Lloyd", "HLXU": "Hapag-Lloyd",
    "COSU": "COSCO", "CBHU": "COSCO", "OOCU": "OOCL",
    "ONEY": "ONE", "KKFU": "ONE", "NYKU": "ONE",
    "EISU": "Evergreen", "EGHU": "Evergreen", "EMCU": "Evergreen",
    "YMLU": "Yang Ming", "ZIMU": "ZIM", "HDMU": "HMM"
}

def infer_brand(row):
    if "shipping_line" in row and pd.notna(row["shipping_line"]) and str(row["shipping_line"]).strip():
        return str(row["shipping_line"]).strip()
    cid = str(row.get("container_id", "")).strip().upper()
    prefix = cid[:4]
    return BIC_PREFIX_MAP.get(prefix, f"Other ({prefix})" if prefix else "Unknown")

def calculate_teu(size_val):
    s = str(size_val).upper()
    return 2.0 if ("40" in s or "45" in s) else 1.0

def generate_sample_csv():
    data = """container_id,shipping_line,size_type,move_type,timestamp,dwell_hours,cfs_name
MSKU9042184,Maersk,40HC,Import Gate-In,2026-11-01 08:15,38,Chennai CFS Hub
MSKU4412098,Maersk,20GP,Destuffing,2026-11-02 10:30,34,Chennai CFS Hub
MRKU7812345,,40GP,Export Gate-Out,2026-11-03 14:10,29,Chennai CFS Hub
MSCU7731920,MSC,40HC,Import Gate-In,2026-11-02 09:00,52,Chennai CFS Hub
MEDU6510923,,20GP,Destuffing,2026-11-04 11:45,49,Chennai CFS Hub
CMAU5520193,CMA CGM,40GP,Stuffing,2026-11-03 16:20,41,Chennai CFS Hub
HLCU3391024,Hapag-Lloyd,20GP,Empty Return,2026-11-05 13:05,26,Chennai CFS Hub
COSU8821044,COSCO,40HC,Import Gate-In,2026-11-06 15:40,61,Chennai CFS Hub
"""
    return data

# Header
st.title("CFS Container Brand Movement Analyzer")
st.caption("Upload container movement logs (CSV) to identify the top-performing shipping line in your CFS.")

# Sidebar Controls
with st.sidebar:
    st.header("1. Upload Movement CSV")
    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
    st.download_button(
        label="Download Sample CSV Template",
        data=generate_sample_csv(),
        file_name="sample_cfs_movements.csv",
        mime="text/csv"
    )
    st.divider()
    st.header("2. Ranking Criteria")
    ranking_mode = st.radio(
        "Define 'Best Movement' by:",
        ["Total TEU Volume", "Composite Score (Volume + Fast Dwell)", "Total Container Moves"]
    )
    metric_unit = st.radio("Display Metric:", ["TEUs", "Container Count"])

# Load Data (Uploaded or Sample Fallback)
if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    st.success(f"Loaded `{uploaded_file.name}` ({len(df)} records)")
else:
    df = pd.read_csv(io.StringIO(generate_sample_csv()))
    st.info("Showing built-in sample CFS dataset. Upload your own CSV in the left sidebar.")

# Normalize Column Names
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

# Clean & Enrich Columns
df["brand"] = df.apply(infer_brand, axis=1)
df["teu"] = df["size_type"].apply(calculate_teu) if "size_type" in df.columns else 1.0
df["dwell_hours"] = pd.to_numeric(df["dwell_hours"], errors="coerce").fillna(48.0) if "dwell_hours" in df.columns else 48.0

# Optional CFS Filter if multiple terminals exist in CSV
if "cfs_name" in df.columns and df["cfs_name"].nunique() > 1:
    selected_cfs = st.selectbox("Filter by CFS Station:", ["All CFS Stations"] + sorted(df["cfs_name"].dropna().unique().tolist()))
    if selected_cfs != "All CFS Stations":
        df = df[df["cfs_name"] == selected_cfs]

# Aggregate by Brand
summary = df.groupby("brand", as_index=False).agg(
    containers=("brand", "count"),
    total_teu=("teu", "sum"),
    avg_dwell_hrs=("dwell_hours", "mean")
)

# Calculate Composite Velocity-Volume Score (Higher volume + lower dwell = higher score)
max_teu = summary["total_teu"].max() or 1
min_dwell = summary["avg_dwell_hrs"].min() or 1
summary["composite_score"] = (
    (summary["total_teu"] / max_teu) * 70 +
    (min_dwell / summary["avg_dwell_hrs"].clip(lower=1)) * 30
).round(1)

# Sort based on selected Ranking Mode
if ranking_mode == "Total TEU Volume":
    summary = summary.sort_values(by="total_teu", ascending=False)
elif ranking_mode == "Composite Score (Volume + Fast Dwell)":
    summary = summary.sort_values(by="composite_score", ascending=False)
else:
    summary = summary.sort_values(by="containers", ascending=False)

summary = summary.reset_index(drop=True)
winner = summary.iloc[0]
share_pct = (winner["total_teu"] / summary["total_teu"].sum() * 100) if summary["total_teu"].sum() > 0 else 0

# Best Movement Spotlight Banner
st.markdown(f"""
<div class="winner-card">
    <div class="winner-title">🏆 Best Container Movement Brand ({ranking_mode})</div>
    <div class="winner-brand">{winner['brand']}</div>
    <div class="winner-sub">
        Leads this CFS with <b>{int(winner['total_teu'])} TEUs</b> ({int(winner['containers'])} containers, <b>{share_pct:.1f}%</b> share)
        and an average yard dwell time of <b>{winner['avg_dwell_hrs']:.1f} hrs</b>.
    </div>
</div>
""", unsafe_allow_html=True)

# KPI Row
k1, k2, k3, k4 = st.columns(4)
k1.metric("#1 Top Liner", winner["brand"], f"{share_pct:.1f}% TEU Share")
k2.metric("Total CFS TEUs", f"{int(summary['total_teu'].sum()):,}")
k3.metric("Total Container Moves", f"{int(summary['containers'].sum()):,}")
k4.metric("Avg CFS Dwell Time", f"{df['dwell_hours'].mean():.1f} hrs")

# Charts Row
c1, c2 = st.columns(2)
y_col = "total_teu" if metric_unit == "TEUs" else "containers"

with c1:
    st.subheader(f"Liner Movement Leaderboard ({metric_unit})")
    fig_bar = px.bar(
        summary, x="brand", y=y_col, color="brand",
        color_discrete_sequence=["#f59e0b", "#38bdf8", "#10b981", "#a78bfa", "#fb7185", "#94a3b8"],
        template="plotly_dark"
    )
    fig_bar.update_layout(showlegend=False, paper_bgcolor="#161920", plot_bgcolor="#161920")
    st.plotly_chart(fig_bar, use_container_width=True)

with c2:
    st.subheader("Volume vs. Yard Dwell Speed")
    fig_scatter = px.scatter(
        summary, x="avg_dwell_hrs", y="total_teu", size="containers", color="brand",
        hover_name="brand", labels={"avg_dwell_hrs": "Avg Dwell Time (Hours)", "total_teu": "Total TEUs"},
        template="plotly_dark"
    )
    fig_scatter.update_layout(paper_bgcolor="#161920", plot_bgcolor="#161920")
    st.plotly_chart(fig_scatter, use_container_width=True)

# Data Table & Preview
st.subheader("Shipping Line Performance Breakdown")
st.dataframe(summary, use_container_width=True)

with st.expander("Preview Uploaded CSV Records"):
    st.dataframe(df, use_container_width=True)