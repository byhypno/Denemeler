import pandas as pd
import plotly.express as px
import streamlit as st

from data import REQUIRED, prepare, sample_data

st.set_page_config(page_title="Satış Dashboard", page_icon="📊", layout="wide")
st.title("📊 Satış Dashboard")


@st.cache_data
def load_sample() -> pd.DataFrame:
    return prepare(sample_data())


# --- Veri kaynağı ---
with st.sidebar:
    st.header("Veri")
    up = st.file_uploader("CSV yükle", type="csv",
                          help="Sütunlar: " + ", ".join(REQUIRED))
try:
    df = prepare(pd.read_csv(up)) if up else load_sample()
except Exception as e:
    st.error(f"Veri okunamadı: {e}")
    st.stop()
if not up:
    st.caption("Örnek veri gösteriliyor. Kendi CSV'ni soldan yükleyebilirsin.")

# --- Filtreler ---
with st.sidebar:
    st.header("Filtreler")
    dmin, dmax = df["tarih"].min().date(), df["tarih"].max().date()
    aralik = st.date_input("Tarih aralığı", (dmin, dmax), dmin, dmax)
    kats = st.multiselect("Kategori", sorted(df["kategori"].unique()),
                          default=sorted(df["kategori"].unique()))
    bolge = st.multiselect("Bölge", sorted(df["bolge"].unique()),
                           default=sorted(df["bolge"].unique()))

if len(aralik) != 2:
    st.info("Lütfen bitiş tarihini de seç.")
    st.stop()
f = df[df["tarih"].dt.date.between(*aralik)
       & df["kategori"].isin(kats) & df["bolge"].isin(bolge)]
if f.empty:
    st.warning("Seçilen filtrelerle veri yok.")
    st.stop()

# --- KPI'lar ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam ciro", f"₺{f['ciro'].sum():,.0f}")
c2.metric("Satılan adet", f"{f['adet'].sum():,}")
c3.metric("İşlem sayısı", f"{len(f):,}")
c4.metric("Ortalama sepet", f"₺{f['ciro'].mean():,.0f}")

# --- Grafikler ---
aylik = f.set_index("tarih").resample("MS")["ciro"].sum().reset_index()
st.plotly_chart(px.line(aylik, x="tarih", y="ciro", markers=True,
                        title="Aylık ciro"), width="stretch")

l, r = st.columns(2)
l.plotly_chart(px.bar(f.groupby("urun", as_index=False)["ciro"].sum()
                      .sort_values("ciro"), x="ciro", y="urun",
                      orientation="h", title="Ürüne göre ciro"),
               width="stretch")
r.plotly_chart(px.pie(f.groupby("bolge", as_index=False)["ciro"].sum(),
                      names="bolge", values="ciro", title="Bölge payı"),
               width="stretch")

with st.expander("Ham veri"):
    st.dataframe(f, width="stretch")
    st.download_button("Filtrelenmiş CSV indir",
                       f.to_csv(index=False).encode("utf-8"),
                       "filtrelenmis.csv", "text/csv")
