import stripe
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import csv

# Set the secret key to authenticate with the Stripe API
load_dotenv()
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
global debug
debug = False

def get_filename(start_date: str, end_date: str):
    return f'orders_{start_date.replace("/", "-")}_{end_date.replace("/", "-")}.csv'

def is_valid_date(date: str):
    try:
        datetime.strptime(date, '%m/%d/%Y')
    except ValueError:
        return False
    return True

def calculate_date_range(start_date, end_date):
    if not start_date or not end_date:
        return None
    if not is_valid_date(start_date) or not is_valid_date(end_date):
        return None
    start_date_unix = int(datetime.strptime(start_date, '%m/%d/%Y').timestamp())
    end_date_unix = int(datetime.strptime(end_date, '%m/%d/%Y').timestamp())
    return {'gte': start_date_unix, 'lte': end_date_unix}


def check_for_tip(session):
    session_id = session['id']
    line_items = stripe.checkout.Session.list_line_items(session_id, limit=100)
    for item in line_items.auto_paging_iter():
        if item['description'] and "tip" in item['description'].lower():
            return item['amount_subtotal']/100
        continue
    return 0

def check_for_tip_invoice(invoice):
    line_items = invoice.lines.data
    for item in line_items:
        if item['description'] and "tip" in item['description'].lower():
            return item['amount_subtotal']/100
        continue
    return 0

def parse_invoice_data(invoices):
    invoice_data = []
    for invoice in invoices.auto_paging_iter():
        # Check for required conditions: invoice is paid, and includes a tip or delivery fee
        if not invoice.paid or 'amount_shipping' not in invoice or invoice.amount_shipping < 1:
            continue
        
        # Assuming delivery fee is represented by `amount_shipping` and tips need to be extracted from metadata or line items
        delivery_fee = invoice.amount_shipping / 100  # Convert to dollars
        tip = check_for_tip_invoice(invoice)  # Tip extraction logic goes here, based on your invoice structure
        
        invoice_data.append({
            'name': invoice.customer_name,
            'date': format_stripe_date(invoice.created),
            'shipping': define_shipping_options(invoice.shipping_cost.shipping_rate),
            'amount': delivery_fee,  # Convert total amount to dollars
            'tip': tip,
            'payment_intent': invoice.payment_intent,
            'stripe_link': f'https://dashboard.stripe.com/payments/{invoice.payment_intent}',
            'id': invoice.id
        })
    return invoice_data

def parse_session_data(sessions):
    session_data = []
    for session in sessions.auto_paging_iter():
        if not'shipping_options' in session or not session['payment_intent'] or len(session['shipping_options']) < 1:
            continue
        option = session['shipping_options'][0]
        if not 'shipping_amount' in option or option['shipping_amount'] < 1 or session['payment_status'] != 'paid':
            continue
        payment_intent = session['payment_intent']
        session_data.append({
                'name': session['customer_details']['name'],
                'date': format_stripe_date(session['created']),
                'shipping': define_shipping_options(option['shipping_rate']),
                'amount': option['shipping_amount'] / 100,
                'tip': check_for_tip(session),
                'payment_intent': session['payment_intent'],
                'id': session['id'],
                'stripe_link': f"https://dashboard.stripe.com/payments/{payment_intent}"
            })
    return session_data

def define_shipping_options(id):
    if id == os.getenv('EASTIE_SHIPPING'):
        return "Eastie Shipping"
    if id == os.getenv('OUTSIDE_SHIPPING'):
        return "Outside Shipping"
    return "Other Shipping"

def format_stripe_date(timestamp):
    return datetime.utcfromtimestamp(timestamp).strftime('%m-%d-%Y')

# Get total revenue for the Delivery Fee
def get_total_delivery_fee_revenue(orders_data):
    total_revenue = 0
    for order in orders_data:
        total_revenue += (order['amount'] + order['tip'])
    return total_revenue

def create_csv_file(data, filename):
    with open(filename, 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=data[0].keys())
        writer.writeheader()
        for row in data:
            writer.writerow(row)

def get_line_data_if_nonzero(date_range:dict={'gte': datetime.now() - timedelta(days=30)}):
    line_data = []
    sessions = stripe.checkout.Session.list(created=date_range, limit=100)
    invoices = stripe.Invoice.list(created=date_range, limit=100)
    line_data = parse_session_data(sessions)
    line_data += parse_invoice_data(invoices)
    return line_data

def write_line_data_to_csv(start_date: str, end_date:str):
    date_range = calculate_date_range(start_date, end_date)
    line_data = get_line_data_if_nonzero(date_range)
    create_csv_file(line_data, get_filename(start_date, end_date))
    return line_data

if __name__ == '__main__' and not debug:
    start_date = "11/01/2023"
    end_date = "02/29/2024"
    orders_data = write_line_data_to_csv(start_date, end_date)
    total_revenue = get_total_delivery_fee_revenue(orders_data)
    print(f'Total Delivery Fee Revenue: {total_revenue}')

if __name__ == '__main__' and debug:
    # Get a single session to test by payment_intent
    session_id = os.getenv('SESSION_ID')
    session = stripe.checkout.Session.retrieve(session_id)
    print("Done")