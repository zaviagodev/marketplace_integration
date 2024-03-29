import frappe
from marketplace_integration.lazada import Client



@frappe.whitelist(allow_guest=True)
def shopee_token_update():
    partner_id = int(2004610)
    partner_key = "da22ac428afd591add1e4a988eaff7b7981d66980b19323d7d5a5c19116e575a"
    shop_id = int(213497319)
    docSettings = frappe.get_single("Marketplace integration")
    accesstoken = docSettings.get_value('access_token')
    refresh_token = docSettings.get_password('refresh_token_copy')
    shopee  = Client(shop_id, partner_id, partner_key, accesstoken)
    shopee  = shopee.get_access_token(shop_id, partner_id, partner_key, refresh_token)
    access_token = shopee[0]
    refresh_token = shopee[2]
    if access_token:
        doc = frappe.get_doc('Marketplace integration')
        doc.access_token=access_token
        doc.refresh_token_copy=refresh_token
        doc.save(
                ignore_permissions=True,
                ignore_version=True
        )
        frappe.db.commit()