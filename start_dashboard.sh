#!/usr/bin/env bash
# Start the internal activation dashboard on your computer.
# Usage: bash start_dashboard.sh
set -e
cd "$(dirname "$0")"
pip install -q -r requirements.txt
pip install -q -e .
echo ""
echo "Starting dashboard... open http://localhost:8501 in your browser"
echo "Press Ctrl+C to stop."
echo ""
streamlit run app/streamlit_app.py
