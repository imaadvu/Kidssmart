# app.py — KidsSmart+ Educational Finder (Online scraping with SerpAPI + country & region aware validation)

import csv
import io

import requests
import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from serpapi import GoogleSearch

from database import create_database, save_result, get_results

# ---------- SETUP ----------
st.set_page_config(page_title="KidsSmart+ Educational Database", layout="wide")
create_database()

# Single logo (your company)
LOGO = "logo2.png"   # make sure logo2.png is in the same folder as app.py

# ⚠️ Put YOUR real SerpAPI key here
API_KEY = st.secrets["SERPAPI_API_KEY"]

# Country → Region options
COUNTRY_REGIONS = {
    "Any": ["Any"],
    "Australia": ["Any", "Melbourne", "Sydney", "Brisbane", "Perth", "Adelaide"],
    "United States": ["Any", "New York", "Los Angeles", "Chicago", "San Francisco"],
    "United Kingdom": ["Any", "London", "Manchester", "Birmingham"],
    "Canada": ["Any", "Toronto", "Vancouver", "Montreal"],
    "India": ["Any", "Mumbai", "Delhi", "Bengaluru", "Chennai"],
}

# ---------- VALIDATION HELPERS ----------

EDU_KEYWORDS = [
    "course", "class", "workshop", "training", "tutorial",
    "webinar", "lecture", "program", "degree", "diploma",
    "certificate", "bootcamp", "seminar", "learn", "education", "study"
]

def is_educational(text: str) -> bool:
    t = text.lower()
    return any(word in t for word in EDU_KEYWORDS)

def classify_type(text: str) -> str:
    t = text.lower()
    if "webinar" in t or "seminar" in t or "workshop" in t:
        return "Seminar / Workshop"
    if "video" in t or "youtube" in t or "lecture" in t:
        return "Video / Lecture"
    if "course" in t or "short course" in t or "bootcamp" in t or "mooc" in t:
        return "Course"
    return "Article / Other"

def classify_mode(text: str) -> str:
    t = text.lower()
    if "online" in t or "virtual" in t or "remote" in t or "self-paced" in t:
        return "Online"
    if "campus" in t or "in-person" in t or "on campus" in t or "classroom" in t or "venue" in t:
        return "In-person"
    return "Unknown"

def classify_cost(text: str) -> str:
    t = text.lower()
    if "free" in t or "no cost" in t:
        return "Free"
    if "$" in t or "aud" in t or "fee" in t or "per month" in t or "per year" in t:
        return "Paid / Unknown"
    return "Unknown"

def matches_location(combined_text: str, country: str, region: str) -> bool:
    """
    Check if the page text mentions the chosen country/region.
    Rules:
    - If country == Any → always True.
    - If country != Any and region == Any → require country in text.
    - If both set → require country OR region in text.
    """
    text = combined_text.lower()
    if country == "Any":
        return True

    c = country.lower()
    r = region.lower()

    if region == "Any":
        return c in text

    # both set: either is okay
    return (c in text) or (r in text)

# ---------- ONLINE SEARCH (GOOGLE VIA SERPAPI) ----------

def _run_serpapi_query(query: str, max_results: int):
    params = {
        "engine": "google",
        "q": query,
        "num": max_results,
        "api_key": API_KEY,
    }
    search = GoogleSearch(params)
    data = search.get_dict()
    organic = data.get("organic_results", [])[:max_results]
    results = []
    for r in organic:
        title = r.get("title", "")
        link = r.get("link", "")
        snippet = r.get("snippet", "")
        if link:
            results.append({"title": title, "link": link, "snippet": snippet})
    return results

def search_web(topic: str, filters: dict, max_results: int = 8):
    """
    Use SerpAPI to search Google and return a list of {title, link, snippet}.
    Tries:
      1) topic + type/mode/cost + country + region
      2) topic + type/mode/cost + country
      3) topic + type/mode/cost (no location)
    """
    if API_KEY == "YOUR_SERPAPI_KEY_HERE":
        st.error("Set your SerpAPI key in app.py (API_KEY).")
        return []

    base_parts = [topic, "education", "course OR workshop OR webinar OR training"]

    # Type
    if filters["type"] == "Course":
        base_parts.append("course")
    elif filters["type"] == "Seminar / Workshop":
        base_parts.append("seminar OR workshop")
    elif filters["type"] == "Video / Lecture":
        base_parts.append("video OR lecture")

    # Mode
    if filters["mode"] == "Online":
        base_parts.append("online")
    elif filters["mode"] == "In-person":
        base_parts.append("in person OR on campus")

    # Cost
    if filters["cost"] == "Free":
        base_parts.append("free")
    elif filters["cost"] == "Paid / Unknown":
        base_parts.append("fee OR $")

    country = filters["country"]
    region = filters["region"]

    # 1) country + region
    tries = []
    if country != "Any" and region != "Any":
        tries.append(base_parts + [country, region])
    # 2) country only
    if country != "Any":
        tries.append(base_parts + [country])
    # 3) no location
    tries.append(base_parts)

    for parts in tries:
        query = " ".join(parts)
        try:
            results = _run_serpapi_query(query, max_results)
        except Exception as e:
            st.error(f"Search error: {e}")
            results = []

        if results:
            return results

    # nothing worked
    return []

# ---------- SCRAPING EACH PAGE (ONLINE) ----------

def scrape_page(url: str, max_chars: int = 1500) -> str:
    """
    Scrape page text with requests + BeautifulSoup.
    """
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for s in soup(["script", "style", "noscript"]):
            s.decompose()
        text = " ".join(soup.get_text(" ").split())
        return text[:max_chars]
    except Exception as e:
        return f"(scrape error: {e})"

# ---------- UI LAYOUT ----------

# Sidebar: just your logo, a bit bigger
try:
    st.sidebar.image(LOGO, width=200)
except Exception:
    pass

page = st.sidebar.radio("Navigate", ["Find Programs", "Saved Results"])

# ---------- PAGE: FIND PROGRAMS ----------

if page == "Find Programs":
    # Custom heading
    st.markdown(
        "<h1 style='font-size:32px; font-weight:bold; margin-bottom:0;'>KidsSmart+</h1>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='font-size:18px; margin-top:4px;'>The one-stop place to find Educational Programs, Courses & Videos</p>",
        unsafe_allow_html=True
    )

    col_topic, col_num = st.columns([3, 1])
    with col_topic:
        topic = st.text_input(
            "What do you want to learn?",
            placeholder="e.g. Early childhood literacy, Python for beginners, VCE maths prep"
        )
    with col_num:
        num_results = st.slider("Max results from Google", 3, 15, 8)

    # Type/mode/cost row
    col_type, col_mode, col_cost = st.columns(3)
    with col_type:
        type_filter = st.selectbox(
            "Resource type",
            ["Any", "Course", "Seminar / Workshop", "Video / Lecture", "Article / Other"]
        )
    with col_mode:
        mode_filter = st.selectbox(
            "Delivery mode",
            ["Any", "Online", "In-person"]
        )
    with col_cost:
        cost_filter = st.selectbox(
            "Cost",
            ["Any", "Free", "Paid / Unknown"]
        )

    # Country + region row
    col_country, col_region = st.columns(2)
    with col_country:
        country = st.selectbox(
            "Country",
            list(COUNTRY_REGIONS.keys()),
            index=0,
            help="Start typing to search the list of countries."
        )
    with col_region:
        region = st.selectbox(
            "Region / City",
            COUNTRY_REGIONS[country],
            index=0,
            help="Start typing to search regions for the selected country."
        )

    filters = {
        "type": type_filter,
        "mode": mode_filter,
        "cost": cost_filter,
        "country": country,
        "region": region,
    }

    if st.button("Search"):
        if not topic.strip():
            st.warning("Please enter a topic.")
        else:
            # 1) Search Google (via SerpAPI) with fallback strategies
            with st.spinner("Searching Google for educational resources…"):
                search_results = search_web(topic, filters, max_results=num_results)

            if not search_results:
                st.error("Online search returned 0 results, even after relaxing location. Try changing the topic or filters.")
            else:
                # 2) Scrape each result page
                st.info(f"Found {len(search_results)} results. Scraping pages for validation…")
                prog = st.progress(0.0)
                items = []

                for i, r in enumerate(search_results, start=1):
                    page_text = scrape_page(r["link"])
                    combined = f"{r['title']} {r.get('snippet','')} {page_text}"

                    # Must be educational
                    if not is_educational(combined):
                        prog.progress(i / len(search_results))
                        continue

                    # Must match location preference
                    if not matches_location(combined, country, region):
                        prog.progress(i / len(search_results))
                        continue

                    r_type = classify_type(combined)
                    r_mode = classify_mode(combined)
                    r_cost = classify_cost(combined)

                    # Apply chosen filters
                    if filters["type"] != "Any" and r_type != filters["type"]:
                        prog.progress(i / len(search_results))
                        continue
                    if filters["mode"] != "Any" and r_mode != filters["mode"]:
                        prog.progress(i / len(search_results))
                        continue
                    if filters["cost"] != "Any" and r_cost != filters["cost"]:
                        prog.progress(i / len(search_results))
                        continue

                    snippet = r.get("snippet") or page_text[:300]
                    items.append({
                        "title": r["title"],
                        "link": r["link"],
                        "snippet": snippet,
                        "type": r_type,
                        "mode": r_mode,
                        "cost": r_cost,
                        "country": country,
                        "region": region,
                        "raw_text": combined[:2000],
                    })
                    prog.progress(i / len(search_results))

                if not items:
                    st.warning("Search worked, but no pages matched all filters (including location). Try relaxing filters or region.")
                else:
                    st.success(f"Showing {len(items)} validated educational resources (live web scraping) ✅")

                    # Save to DB (include tags for country/region too)
                    for item in items:
                        save_result(
                            topic,
                            item["title"],
                            item["link"],
                            f"[TYPE:{item['type']}][MODE:{item['mode']}][COST:{item['cost']}][COUNTRY:{item['country']}][REGION:{item['region']}]\n{item['raw_text']}"
                        )

                    # Show as cards (grid)
                    st.markdown("### 📋 Results")
                    cards_per_row = 3
                    for i in range(0, len(items), cards_per_row):
                        row_items = items[i:i + cards_per_row]
                        cols = st.columns(len(row_items))
                        for col, item in zip(cols, row_items):
                            with col:
                                st.markdown(f"**[{item['title']}]({item['link']})**")
                                st.caption(
                                    f"Type: {item['type']} | Mode: {item['mode']} | Cost: {item['cost']} "
                                    f"| {item['country']}{' - ' + item['region'] if item['region'] != 'Any' else ''}"
                                )
                                st.write((item["snippet"] or "")[:220] + "…")
                                st.markdown("---")

# ---------- PAGE: SAVED RESULTS ----------

elif page == "Saved Results":
    st.markdown("## 💾 Saved Results")

    rows = get_results()
    if not rows:
        st.info("No data saved yet. Run a search on 'Find Programs' first.")
    else:
        df = pd.DataFrame(rows, columns=["ID", "Query", "Title", "Link", "Content"])
        st.dataframe(df[["ID", "Query", "Title", "Link"]], use_container_width=True)

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(df.columns)
        writer.writerows(df.values.tolist())
        st.download_button(
            "📥 Download CSV",
            buf.getvalue(),
            "kidsmart_results_all.csv",
            "text/csv"
        )

# ---------- FOOTER ----------

st.markdown("""
<div style="position:fixed;bottom:0;left:0;width:100%;background:#000;color:#fff;text-align:center;font-size:14px;padding:10px;z-index:999%;">
Created by <b>Mohamed Imaad Muhinudeen (s8078260)</b> & <b>Kavin Nanthakumar (s8049341)</b> | All Rights Reserved | KidsSmart+
</div>
""", unsafe_allow_html=True)

