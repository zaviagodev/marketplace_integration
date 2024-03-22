import frappe
import requests
from frappe import _
from frappe.utils import cint, cstr, get_datetime
import json

@frappe.whitelist(allow_guest=True)
def push_shopee_webhook(ordersn,shop_id,status):
    try:
        existing_record = frappe.get_doc("Marketplace Logs", {"order_id": ordersn, "status": status})
    except frappe.DoesNotExistError:
        existing_record = None
    
    if not existing_record:
        contact = frappe.new_doc("Marketplace Logs")
        contact.order_id = ordersn
        contact.status = status
        contact.shope_id = shop_id
        contact.insert(ignore_permissions=True)
        return 'fff'
            
            
            
class CreateMarketplaceClient:
    def create_sales_order_shopee( self, ordersn,shop_id,status):
        return
    
    