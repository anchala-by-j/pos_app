import streamlit as st
import pandas as pd
import os
from datetime import datetime
from sqlalchemy import create_engine

st.image("logo.png", use_column_width=True)  # adjust width as needed
# Load credentials from environment variables
DB_USERNAME = st.secrets["connections.postgres"]["DB_USERNAME"]
DB_PASSWORD = st.secrets["connections.postgres"]["DB_PASSWORD"]
DB_HOST = st.secrets["connections.postgres"]["DB_HOST"]
DB_NAME = st.secrets["connections.postgres"]["DB_NAME"]
DB_PORT = st.secrets["connections.postgres"]["DB_PORT"]

# Create database engine
@st.cache_resource
def get_engine():
    return create_engine(f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

engine = get_engine()

#Load data functions
@st.cache_data(ttl=600) # Cache for 10 minutes
def load_inventory():
    df = pd.read_sql('SELECT * FROM "mainDB".purchase_audit' , con=engine)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    return df

def load_sales():
    return pd.read_sql('SELECT * FROM "mainDB".sales', con=engine)

def load_billbook():
    return pd.read_sql('SELECT * FROM "mainDB".billbook', con=engine)

def save_sales(df):
    df.to_sql("sales", con=engine, if_exists="append", index=False, schema="mainDB")

def save_billbook(df):
    df.to_sql("billbook", con=engine, if_exists="append", index=False, schema="mainDB")

# Initialize session state
if 'bill_items' not in st.session_state:
    st.session_state.bill_items = []

# UI Header
st.title("Anchala")
st.markdown("Scan or enter the barcode below to add items to a bill.")

# Barcode input
barcode = st.text_input("Scan Barcode (Product Code)")

if barcode:
    inventory_df = load_inventory()
    barcode_cleaned = str(barcode).strip().lower()
    inventory_df['product_code'] = inventory_df['product_code'].astype(str).str.strip().str.lower()

    product = inventory_df[inventory_df['product_code'] == barcode_cleaned]

    if not product.empty:
        item = product.iloc[0]
        st.success(f"Product Found: {item['product_name']}")
        st.write(f"Price: ₹{item['price']}")

        quantity = st.number_input("Enter Quantity", min_value=1, value=1)
        selling_price = st.number_input("Selling Price", min_value=0.0, value=float(item['price']))

        if st.button("Add to Bill", key=f"add_{barcode}"):
            st.session_state.bill_items.append({
                'product_code': barcode,
                'product_name': item['product_name'],
                'qty': quantity,
                'cost': item['cost'],
                'price': selling_price,
                'total_price': selling_price * quantity,
                'margin': (selling_price - item['cost']) * quantity
            })
            st.success("Item added to bill.")
    else:
        st.error("Product not found in inventory.")

# Show current bill items
if st.session_state.bill_items:
    st.subheader("Current Bill Items")

    display_df = pd.DataFrame(st.session_state.bill_items).drop(columns=["cost", "margin"])

    total_row = pd.DataFrame([{
        'product_code': '',
        'product_name': 'Total',
        'qty': '',
        'price': '',
        'total_price': display_df['total_price'].sum()
    }])

    display_df_with_total = pd.concat([display_df, total_row], ignore_index=True)
    st.dataframe(display_df_with_total)

    bill_no = st.text_input("Bill Number")
    customer = st.text_input("Customer Name")
    paid = st.number_input("Paid Amount", min_value=0.0, value=0.0)
    returns = st.number_input("Returns", min_value=0.0, value=0.0)

    if st.button("Confirm Sale", disabled=not st.session_state.bill_items):
        if bill_no.strip() and customer.strip() and paid > 0:
            total_amount = sum([item['total_price'] for item in st.session_state.bill_items])

            sales_df = pd.DataFrame([{
                'bill_no': bill_no,
                'date': datetime.today().date(),
                'customer': customer,
                'items': len(st.session_state.bill_items),
                'amount': total_amount,
                'paid': paid,
                'bal_paid': 0,
                # 'returns': returns,
                'balance': total_amount - paid
            }])
            save_sales(sales_df)

            billbook_df = pd.DataFrame(st.session_state.bill_items)
            billbook_df['bill_no'] = bill_no
            save_billbook(billbook_df)

            st.success("Sale recorded and bill updated.")
            st.session_state.bill_items.clear()
        else:
            st.warning("Fill Bill Number, Customer Name, and Paid Amount before confirming.")
