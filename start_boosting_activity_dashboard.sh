#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
pip install -q -r requirements.txt
echo "Boosting activity dashboard (WBP or campaign 2206666) → http://localhost:8501"
exec streamlit run creator_boosting_activity_dash.py
