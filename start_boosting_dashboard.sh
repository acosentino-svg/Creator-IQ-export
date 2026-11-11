#!/usr/bin/env bash
# Start the Wayfair Boosting Program dashboard (boosting only — not the activation Command Center).
# Usage: bash start_boosting_dashboard.sh
set -e
cd "$(dirname "$0")"
pip install -q -r requirements.txt
echo ""
echo "Starting Boosting Program dashboard... open http://localhost:8501"
echo "Press Ctrl+C to stop."
echo ""
streamlit run app/boosting_standalone/streamlit_app.py
