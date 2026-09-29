# Priya General Store AI

Browser-based retail assistant built from the existing `retail_bot.py` logic.

## Features

- Top products
- Monthly sales
- 30/60/90-day sales velocity
- Product-specific history
- Inventory/restocking analysis
- Hindsight historical memory
- Gemini AI assistant
- Streamlit browser interface

## Local setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Put these data files beside `app.py`:

- `restocking_sales_history.xlsx` (or CSV)
- `inventory.csv`

Set secrets as environment variables; never commit them to GitHub:

- `GEMINI_API_KEY`
- `HINDSIGHT_API_KEY`
- optional `HINDSIGHT_BANK_ID`

The app can still show the dashboard and deterministic analytics without AI credentials.
