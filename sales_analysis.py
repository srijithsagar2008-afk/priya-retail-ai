import pandas as pd

CSV_FILE = r"C:\Users\admin\Downloads\restocking_sales_history.csv"


def load_sales():
    df = pd.read_csv(CSV_FILE)
    df["date"] = pd.to_datetime(df["date"])
    return df


def top_products():
    df = load_sales()

    return (
        df.groupby(["sku", "product_name"])["units_sold"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
    )


def sales_by_month():
    df = load_sales()

    df["month"] = df["date"].dt.to_period("M")

    return (
        df.groupby("month")["units_sold"]
        .sum()
        .sort_index()
    )


def recent_sales_velocity(days=30):
    df = load_sales()

    latest_date = df["date"].max()
    start_date = latest_date - pd.Timedelta(days=days - 1)

    recent = df[
        (df["date"] >= start_date) &
        (df["date"] <= latest_date)
    ]

    result = (
        recent.groupby(["sku", "product_name"])["units_sold"]
        .sum()
        .to_frame("units_sold")
    )

    result["units_per_day"] = result["units_sold"] / days

    return result.sort_values("units_per_day", ascending=False)


if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("TOP PRODUCTS")
    print("=" * 60)
    print(top_products())

    print("\n" + "=" * 60)
    print("SALES BY MONTH")
    print("=" * 60)
    print(sales_by_month())

    for days in [30, 60, 90]:
        print("\n" + "=" * 60)
        print(f"RECENT SALES VELOCITY - LAST {days} DAYS")
        print("=" * 60)
        print(recent_sales_velocity(days))