import streamlit as st
import pandas as pd
import os
from datetime import datetime
from sqlalchemy import create_engine, text
import tempfile
from fpdf import FPDF
from streamlit_qrcode_scanner import qrcode_scanner

st.image("logo.png", use_container_width=True)

# Load credentials from environment variables
DB_USERNAME = st.secrets["connections.postgres"]["DB_USERNAME"]
DB_PASSWORD = st.secrets["connections.postgres"]["DB_PASSWORD"]
DB_HOST = st.secrets["connections.postgres"]["DB_HOST"]
DB_NAME = st.secrets["connections.postgres"]["DB_NAME"]
DB_PORT = st.secrets["connections.postgres"]["DB_PORT"]

@st.cache_resource
def get_engine():
    cert_path = os.path.join(os.path.dirname(__file__), "prod-ca-2021.crt")
    return create_engine(
        f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        connect_args={"sslmode": "verify-full", "sslrootcert": cert_path}
    )

engine = get_engine()

@st.cache_data(ttl=600)
def load_inventory():
    df = pd.read_sql('SELECT * FROM "mainDB".purchase_audit', con=engine)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    return df

def load_sales():
    return pd.read_sql('SELECT * FROM "mainDB".sales', con=engine)

def save_sales(df):
    df.to_sql("sales", con=engine, if_exists="append", index=False, schema="mainDB")

def save_billbook(df):
    df.to_sql("billbook", con=engine, if_exists="append", index=False, schema="mainDB")

def save_return(df):
    df.to_sql("returns", con=engine, if_exists="append", index=False, schema="mainDB")

def save_balance_payment(df):
    df.to_sql("balance_payments", con=engine, if_exists="append", index=False, schema="mainDB")

def update_balance(bill_no, amount):
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE "mainDB".sales
            SET paid = paid + :amount,
                balance = GREATEST(balance - :amount, 0)
            WHERE bill_no = :bill_no
        '''), {'amount': amount, 'bill_no': bill_no})

def generate_invoice_pdf(bill_no, customer, bill_items, total_amount, paid, balance):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=80, y=10, w=50)
        pdf.ln(30)
    else:
        pdf.ln(10)

    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Anchala Sarees - Invoice", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Arial", size=12)
    pdf.cell(100, 10, txt=f"Bill No: {bill_no}", ln=True)
    pdf.cell(100, 10, txt=f"Customer: {customer}", ln=True)
    pdf.cell(100, 10, txt=f"Date: {datetime.today().strftime('%d-%m-%Y')}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(80, 10, "Product", border=1, fill=True)
    pdf.cell(30, 10, "Qty", border=1, fill=True, align="C")
    pdf.cell(40, 10, "Price", border=1, fill=True, align="C")
    pdf.cell(40, 10, "Total", border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Arial", size=12)
    for item in bill_items:
        pdf.cell(80, 10, str(item.get('product_name', '')), border=1)
        pdf.cell(30, 10, str(item.get('qty', 0)), border=1, align="C")
        pdf.cell(40, 10, f"Rs.{item.get('price', 0.0):.2f}", border=1, align="R")
        pdf.cell(40, 10, f"Rs.{item.get('total_price', 0.0):.2f}", border=1, align="R")
        pdf.ln()

    pdf.ln(5)
    pdf.cell(150, 10, "Total Amount", border=1)
    pdf.cell(40, 10, f"Rs.{total_amount:.2f}", border=1, align="R")
    pdf.ln()
    pdf.cell(150, 10, "Paid", border=1)
    pdf.cell(40, 10, f"Rs.{paid:.2f}", border=1, align="R")
    pdf.ln()
    pdf.cell(150, 10, "Balance", border=1)
    pdf.cell(40, 10, f"Rs.{balance:.2f}", border=1, align="R")

    pdf.ln(15)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(200, 10, txt="Thank you for shopping at Anchala Sarees!", ln=True, align="C")

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp_file.name)
    return tmp_file.name

if 'bill_items' not in st.session_state:
    st.session_state.bill_items = []

page = st.sidebar.radio("Select Module", ["POS", "Returns", "Balances"])

if page == "POS":
    st.title("Anchala POS")
    st.markdown("""
        <style>
            .stApp {
                background-color: #fabec0;
            }
        </style>
    """, unsafe_allow_html=True)
    st.markdown("### 📸 Scan or enter the barcode below")

    scanned_code = qrcode_scanner("Scan Product Barcode")
    barcode = st.text_input("Or enter barcode manually", value=scanned_code or "", key="manual_barcode")

    if barcode:
        inventory_df = load_inventory()
        barcode_cleaned = str(barcode).strip().lower()
        inventory_df['product_code'] = inventory_df['product_code'].astype(str).str.strip().str.lower()

        product = inventory_df[inventory_df['product_code'] == barcode_cleaned]

        if not product.empty:
            item = product.iloc[0]
            st.success(f" {item['product_name']}")
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

        def get_next_bill_no():
            try:
                result = pd.read_sql('SELECT MAX(bill_no) AS max_bill FROM "mainDB".sales', con=engine)
                max_bill = result['max_bill'].iloc[0]
                return int(max_bill) + 1 if pd.notna(max_bill) else 1
            except Exception as e:
                st.error(f"Error fetching last bill number: {e}")
                return 1

        bill_no = str(get_next_bill_no())
        st.markdown(f"### 🧾 Bill Number: `{bill_no}`")
        customer = st.text_input("Customer Name")
        paid = st.number_input("Paid Amount", min_value=0.0, value=0.0)

        if st.button("Confirm Sale", disabled=not st.session_state.bill_items):
            if bill_no.strip() and customer.strip():
                total_amount = sum([item['total_price'] for item in st.session_state.bill_items])

                sales_df = pd.DataFrame([{
                    'bill_no': bill_no,
                    'date': datetime.today().date(),
                    'customer': customer,
                    'items': len(st.session_state.bill_items),
                    'amount': total_amount,
                    'paid': paid,
                    'bal_paid': 0,
                    'balance': total_amount - paid
                }])
                save_sales(sales_df)

                billbook_df = pd.DataFrame(st.session_state.bill_items)
                billbook_df['bill_no'] = bill_no
                save_billbook(billbook_df)

                invoice_path = generate_invoice_pdf(bill_no, customer, st.session_state.bill_items, total_amount, paid, total_amount - paid)
                st.success("Sale recorded and bill updated.")
                st.download_button("📄 Download Invoice", open(invoice_path, "rb"), file_name=f"Invoice_{bill_no}.pdf", mime="application/pdf")
                st.session_state.bill_items.clear()
            else:
                st.warning("Fill Customer Name and Paid Amount before confirming.")

elif page == "Returns":
    st.title("Returns")
    bill_no = st.text_input("Bill Number")
    product_code = st.text_input("Product Code")
    qty = st.number_input("Quantity Returned", min_value=1, value=1)
    refund_amount = st.number_input("Refund/Adjustment Amount", min_value=0.0, value=0.0)
    remarks = st.text_input("Remarks")

    if st.button("Process Return"):
        if bill_no and product_code:
            try:
                return_data = pd.DataFrame([{
                    'bill_no': bill_no,
                    'product_code': product_code,
                    'product_name': '',
                    'qty': qty,
                    'return_date': datetime.today().date(),
                    'refund_amount': refund_amount,
                    'remarks': remarks
                }])
                save_return(return_data)
                update_balance(bill_no, refund_amount)
                st.success("Return processed successfully.")
            except Exception as e:
                st.error(f"Error processing return: {e}")
        else:
            st.warning("Please enter Bill Number and Product Code.")

elif page == "Balances":
    st.title("Update Balance Payment")
    sales_df = load_sales()
    pending_df = sales_df[sales_df['balance'] > 0]

    if pending_df.empty:
        st.info("All customers are fully paid.")
    else:
        customers = pending_df['customer'].dropna().unique().tolist()
        selected_customer = st.selectbox("Select Customer with Pending Balance", customers)

        if selected_customer:
            customer_bills = pending_df[pending_df['customer'] == selected_customer]
            bill_no = st.selectbox("Select Bill Number", customer_bills['bill_no'].astype(str).tolist())

            if bill_no:
                bill = customer_bills[customer_bills['bill_no'].astype(str) == bill_no].iloc[0]
                pending_balance = bill['balance']

                st.markdown(f"**Pending Balance:** ₹{pending_balance:.2f}")
                amount = st.number_input("Amount Paid", min_value=0.0, max_value=float(pending_balance), value=0.0)
                remarks = st.text_input("Remarks (optional)")

                if st.button("Update Balance"):
                    if amount <= 0:
                        st.warning("Amount must be greater than zero.")
                    else:
                        try:
                            update_balance(bill_no, amount)
                            payment_df = pd.DataFrame([{
                                'bill_no': bill_no,
                                'customer': selected_customer,
                                'payment_date': datetime.today().date(),
                                'amount_paid': amount,
                                'remarks': remarks
                            }])
                            save_balance_payment(payment_df)
                            st.success(f"₹{amount:.2f} received from {selected_customer}. Balance updated.")
                        except Exception as e:
                            st.error(f"Error updating balance: {e}")