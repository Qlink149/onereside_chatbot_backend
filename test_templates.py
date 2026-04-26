from onereside_chatbot.whatsapp_functions.template.send_product_enquiry_template import send_product_enquiry_template
from onereside_chatbot.whatsapp_functions.template.send_customer_support_template import send_customer_support_template

PHONE = "918432563408"

print("--- Sending product enquiry template ---")
send_product_enquiry_template(
    phone_number=PHONE,
    product_name="Tirupati Balaji – Marodi Brass Plate",
    customer_name="Pratham",
    customer_phone="+91 84325 63408",
)
print("Done.\n")

print("--- Sending customer support template ---")
send_customer_support_template(
    phone_number=PHONE,
    customer_name="Pratham",
    customer_phone="+91 84325 63408",
)
print("Done.")
