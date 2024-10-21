import frappe
from marketplace_integration.marketplace.lazada_api import LazadaClient


def insert_categories(category, parent_category_id = None):

    new_parent_category = frappe.get_doc({
        "doctype": "Lazada Category",
        "is_group": not category.get("leaf"),
        "category_name": category.get("name"),
        "category_id": category.get("category_id"),
        "parent_lazada_category": parent_category_id
    })
    
    new_parent_category.insert(ignore_permissions=True)

    for c in category.get("children", []):
        insert_categories(c, new_parent_category.category_id)

    
def fetch_lazada_category_tree():
    client = LazadaClient("https://api.lazada.co.th/rest")
    
    response = client.get_category_tree()
    categories = response.get("data")
    
    for category in categories:
        insert_categories(category)

    frappe.db.commit()
