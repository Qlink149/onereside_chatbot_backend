from onereside_chatbot.database.database import db

idac = db["users"]
git_app = db["git_bookings"]
appoinments = db["bookings"]

pims_calls = db["pims_calls"]

pims_systems = db["pims_systems"]


company = db["company"]
product = db["product"]
idac = db["users"]

payments = db["payments"]
orders = db["orders"]
orders.create_index("order_id", unique=True, sparse=True)
refunds = db["refunds"]
enquiries = db["enquiries"]